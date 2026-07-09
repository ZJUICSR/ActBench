"""qwenpaw backend adapter for ActBench.

The adapter keeps qwenpaw-specific imports and transcript normalization isolated so the
runner, task loader, mock services, and graders remain backend-neutral.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from lib_tasks import Task

from benchmark.backends.base import (
    BackendInitializationError,
    BackendRunContext,
    augment_execution_result,
    default_agent_id,
    default_slugify_model,
)
from benchmark.backends.common import (
    backend_task_workspace,
    begin_task_artifacts,
    elapsed_since,
    enable_workspace_skills_manifest,
    execution_error_result,
    finish_task_artifacts,
    materialize_task_workspace,
    session_prompts,
    start_declared_api_services,
    stdout_transcript_fallback,
    zero_usage,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class QwenPawRuntime:
    load_agent_config: Any
    model_slot_config: Any
    agent_class: Any
    message_class: Any


class QwenPawBackend:
    """ActBench backend that drives qwenpaw in-process when available."""

    name = "qwenpaw"
    uses_gateway_lock = False

    def __init__(self) -> None:
        self._runtime: Optional[QwenPawRuntime] = None

    def slugify_model(self, model_id: str) -> str:
        return default_slugify_model(model_id)

    def make_agent_id(self, model_id: str) -> str:
        return default_agent_id(model_id)

    def initialize_run(self, context: BackendRunContext) -> None:
        context.agent_workspace.mkdir(parents=True, exist_ok=True)
        self._runtime = self._load_runtime()

    def finalize_run(self, context: BackendRunContext) -> None:
        return None

    def execute_task(
        self,
        *,
        task: Task,
        context: BackendRunContext,
        attempt_run_id: str,
    ) -> Dict[str, Any]:
        runtime = self._runtime or self._load_runtime()
        logger.info("🤖 qwenpaw backend [%s] starting task: %s", context.agent_id, task.task_id)
        start_time = time.time()
        session_id = f"{task.task_id}_{int(start_time * 1000)}"
        workspace = backend_task_workspace(context=context, attempt_run_id=attempt_run_id, task=task)
        api_group = None
        api_endpoints: Dict[str, Any] = {}
        api_audit: Dict[str, Any] = {}
        stdout = ""
        stderr = ""
        exit_code = 0
        transcript: List[Dict[str, Any]] = []
        usage: Dict[str, Any] = {}
        status = "success"
        timed_out = False

        try:
            materialize_task_workspace(workspace=workspace, skill_dir=context.skill_dir, task=task)
            enable_workspace_skills_manifest(workspace)
        except Exception as exc:  # noqa: BLE001 - convert setup issues to execution result
            return execution_error_result(
                context=context,
                task=task,
                workspace=workspace,
                stderr=f"qwenpaw workspace setup failed: {exc}",
                execution_time=elapsed_since(start_time),
            )

        artifact_key, recorder = begin_task_artifacts(
            context=context,
            task=task,
            attempt_run_id=attempt_run_id,
            session_id=session_id,
            workspace=workspace,
        )

        try:
            try:
                api_group, api_endpoints = start_declared_api_services(
                    task=task,
                    attempt_run_id=attempt_run_id,
                    workspace=workspace,
                )
                if api_endpoints:
                    logger.info("   Mock API services started: %s", ", ".join(api_endpoints))
            except Exception as exc:  # noqa: BLE001
                stderr = f"mock API service startup failed: {exc}"
                return execution_error_result(
                    context=context,
                    task=task,
                    workspace=workspace,
                    stderr=stderr,
                    execution_time=elapsed_since(start_time),
                    api_endpoints=api_endpoints,
                    training_artifact_key=artifact_key,
                )

            try:
                run_result = _run_coro(
                    self._run_qwenpaw_task_async(
                        runtime=runtime,
                        task=task,
                        context=context,
                        workspace=workspace,
                        timeout_seconds=task.timeout_seconds * context.timeout_multiplier,
                        start_time=start_time,
                        session_id=session_id,
                    )
                )
                transcript = run_result.get("transcript", []) or []
                usage = run_result.get("usage", {}) or {}
                status = run_result.get("status", "success")
                timed_out = bool(run_result.get("timed_out"))
                stderr = run_result.get("stderr", "") or ""
            except Exception as exc:  # noqa: BLE001 - surface qwenpaw failures as task errors
                status = "error"
                exit_code = -1
                stderr = f"qwenpaw execution failed: {exc}"
                logger.warning("   %s", stderr)

            if not transcript:
                fallback_prompt = "\n\n".join(session_prompts(task))
                transcript = stdout_transcript_fallback(fallback_prompt, stdout)
            if not transcript and status == "success":
                status = "error"

            if api_group:
                api_audit = api_group.collect_audit()

            execution_time = elapsed_since(start_time)
            result = {
                "agent_id": context.agent_id,
                "task_id": task.task_id,
                "status": status,
                "transcript": transcript,
                "usage": usage,
                "workspace": str(workspace),
                "exit_code": exit_code,
                "timed_out": timed_out,
                "execution_time": execution_time,
                "stdout": stdout,
                "stderr": stderr,
                "api_audit": api_audit,
                "api_endpoints": api_endpoints,
                "training_artifact_key": artifact_key,
            }
            return augment_execution_result(result, context=context, transcript_source="qwenpaw_memory")
        finally:
            if api_group:
                api_group.stop()
            finish_task_artifacts(
                recorder=recorder,
                artifact_key=artifact_key,
                task=task,
                workspace=workspace,
                api_endpoints=api_endpoints,
                api_audit=api_audit,
            )

    def _load_runtime(self) -> QwenPawRuntime:
        try:
            from agentscope.message import Msg
            from qwenpaw.agents.react_agent import QwenPawAgent
            from qwenpaw.config.config import ModelSlotConfig, load_agent_config
        except ImportError as exc:
            raise BackendInitializationError(
                "qwenpaw backend requires a Python environment where qwenpaw and "
                "agentscope are importable. Install/configure qwenpaw, or run with "
                "--backend openclaw."
            ) from exc
        return QwenPawRuntime(
            load_agent_config=load_agent_config,
            model_slot_config=ModelSlotConfig,
            agent_class=QwenPawAgent,
            message_class=Msg,
        )

    def _load_agent_config(
        self,
        *,
        runtime: QwenPawRuntime,
        model_id: str,
        workspace: Any,
    ) -> tuple[Any, str]:
        profile_id = os.environ.get("ACTBENCH_QWENPAW_AGENT_ID", "default")
        cfg = runtime.load_agent_config(profile_id)

        provider_id, _, model = model_id.partition("/")
        if not model:
            provider_id, model = "", model_id
        cfg.active_model = runtime.model_slot_config(provider_id=provider_id, model=model)
        cfg.workspace_dir = str(workspace)
        max_iters = os.environ.get("ACTBENCH_QWENPAW_MAX_ITERS")
        if max_iters:
            try:
                cfg.running.max_iters = int(max_iters)
            except (AttributeError, TypeError, ValueError):
                logger.warning("Ignoring invalid ACTBENCH_QWENPAW_MAX_ITERS=%r", max_iters)
        return cfg, profile_id

    async def _run_qwenpaw_task_async(
        self,
        *,
        runtime: QwenPawRuntime,
        task: Task,
        context: BackendRunContext,
        workspace: Any,
        timeout_seconds: float,
        start_time: float,
        session_id: str,
    ) -> Dict[str, Any]:
        agent_config, profile_id = self._load_agent_config(
            runtime=runtime,
            model_id=context.model,
            workspace=workspace,
        )
        request_context = {
            "session_id": session_id,
            "user_id": "actbench",
            "channel": "console",
            "agent_id": profile_id,
        }
        headless_guard = os.environ.get("ACTBENCH_QWENPAW_HEADLESS_TOOL_GUARD")
        if headless_guard is not None:
            request_context["_headless_tool_guard"] = headless_guard

        agent = runtime.agent_class(
            agent_config=agent_config,
            request_context=request_context,
            workspace_dir=workspace,
        )

        prompts = session_prompts(task)
        timed_out = False
        status = "success"
        stderr = ""
        if len(prompts) > 1:
            logger.info("📋 Multi-session task with %d sessions", len(prompts))

        for index, prompt in enumerate(prompts, 1):
            if len(prompts) > 1:
                logger.info("   Session %d/%d", index, len(prompts))
            remaining = timeout_seconds - (time.time() - start_time)
            if remaining <= 0:
                timed_out = True
                break
            try:
                message = runtime.message_class(name="user", role="user", content=prompt)
                await asyncio.wait_for(agent.reply([message]), timeout=remaining)
            except (asyncio.TimeoutError, TimeoutError):
                timed_out = True
                break
            except Exception as exc:  # noqa: BLE001
                status = "error"
                stderr = f"qwenpaw agent error: {exc}"
                logger.warning("   %s", stderr)
                break

        transcript = await _extract_transcript_async(agent)
        usage = _extract_usage(agent, request_count=max(1, len(prompts)))
        if timed_out:
            status = "timeout"
        elif not transcript and status != "error":
            status = "error"
        return {
            "transcript": transcript,
            "usage": usage,
            "status": status,
            "timed_out": timed_out,
            "stderr": stderr,
        }


def _run_coro(coro):
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    raise RuntimeError("qwenpaw backend cannot run inside an existing asyncio event loop")


def _json_sanitize(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    for method in ("model_dump", "dict"):
        fn = getattr(value, method, None)
        if callable(fn):
            try:
                return _json_sanitize(fn())
            except Exception:  # noqa: BLE001
                break
    if isinstance(value, dict):
        return {str(key): _json_sanitize(val) for key, val in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_sanitize(item) for item in value]
    return str(value)


def _msg_to_transcript_entry(msg: Any) -> Optional[Dict[str, Any]]:
    to_dict = getattr(msg, "to_dict", None)
    raw = None
    if callable(to_dict):
        try:
            raw = to_dict()
        except Exception:  # noqa: BLE001
            raw = None
    if not isinstance(raw, dict):
        raw = _json_sanitize(msg)
    if not isinstance(raw, dict):
        raw = {"role": "assistant", "content": [{"type": "text", "text": str(msg)}]}

    message = _json_sanitize(raw)
    content = message.get("content", [])
    if content is None:
        content = []
    elif isinstance(content, (str, dict)):
        content = [content]
    elif not isinstance(content, list):
        content = [content]
    message["content"] = content

    role = message.get("role")
    if role in ("tool", "tool_result"):
        message["role"] = "toolResult"
    return {"type": "message", "message": message}


async def _extract_transcript_async(agent: Any) -> List[Dict[str, Any]]:
    memory = getattr(agent, "memory", None)
    if memory is None:
        return []

    msgs: Any = None
    getter = getattr(memory, "get_memory", None)
    if callable(getter):
        try:
            result = getter()
            msgs = await result if asyncio.iscoroutine(result) else result
        except Exception as exc:  # noqa: BLE001
            logger.warning("qwenpaw memory get_memory() failed: %s", exc)
            msgs = None
    if msgs is None:
        msgs = getattr(memory, "content", None)
    if not isinstance(msgs, list):
        return []

    transcript: List[Dict[str, Any]] = []
    for item in msgs:
        msg = item[0] if isinstance(item, (list, tuple)) and item else item
        entry = _msg_to_transcript_entry(msg)
        if entry is not None:
            transcript.append(entry)
    return transcript


def _extract_usage(agent: Any, *, request_count: int) -> Dict[str, Any]:
    totals = zero_usage(request_count=request_count)
    try:
        model = getattr(agent, "model", None)
        monitor = getattr(model, "monitor", None) if model is not None else None
        get_metrics = getattr(monitor, "get_metrics", None) if monitor is not None else None
        metrics = get_metrics() if callable(get_metrics) else {}
        if isinstance(metrics, dict):
            input_tokens = metrics.get("prompt_tokens", metrics.get("input_tokens", 0)) or 0
            output_tokens = metrics.get("completion_tokens", metrics.get("output_tokens", 0)) or 0
            total_tokens = metrics.get("total_tokens", input_tokens + output_tokens) or 0
            totals["input_tokens"] = int(input_tokens)
            totals["output_tokens"] = int(output_tokens)
            totals["total_tokens"] = int(total_tokens)
            cost = metrics.get("cost_usd", metrics.get("cost", 0.0))
            totals["cost_usd"] = float(cost) if isinstance(cost, (int, float)) else 0.0
    except Exception:  # noqa: BLE001
        logger.debug("Failed to extract qwenpaw usage", exc_info=True)
    return totals
