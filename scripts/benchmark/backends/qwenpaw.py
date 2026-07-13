"""qwenpaw service backend adapter for ActBench.

The adapter talks to an already-running QwenPaw HTTP service. ActBench owns
workspace materialization, mock API startup, and result shaping; QwenPaw owns
agent execution through its service API.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import re
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
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
    safe_path_component,
    session_prompts,
    start_declared_api_services,
    stdout_transcript_fallback,
    zero_usage,
)

logger = logging.getLogger(__name__)

DEFAULT_QWENPAW_BASE_URL = "http://127.0.0.1:8088"
DEFAULT_QWENPAW_AGENT_PREFIX = "actbench"
QWENPAW_HEALTH_TIMEOUT_SECONDS = 15.0
QWENPAW_USER_ID = "actbench"
QWENPAW_CHANNEL = "console"
_TOKEN_USAGE_ENDPOINTS = ("/api/token-usage/details", "/api/token-usage")
_AGENT_ID_MAX_LENGTH = 64
_SSE_EVENTS_KEY = "_qwenpaw_sse_events"
_SSE_AGGREGATED_TEXT_KEY = "_qwenpaw_aggregated_text"
_SSE_AGGREGATED_USAGE_KEY = "_qwenpaw_aggregated_usage"


@dataclass(frozen=True)
class QwenPawConfig:
    base_url: str
    api_key: str | None
    timeout_seconds: float | None
    agent_prefix: str
    delete_agent: bool
    headless_tool_guard: str | None
    usage_delta_enabled: bool


@dataclass(frozen=True)
class QwenPawChatScope:
    user_id: str
    channel: str


class QwenPawRequestError(RuntimeError):
    """Raised when the QwenPaw service returns an unexpected response."""


class QwenPawTimeoutError(QwenPawRequestError):
    """Raised when a QwenPaw service request times out."""


class QwenPawBackend:
    """ActBench backend that drives qwenpaw through its HTTP service API."""

    name = "qwenpaw"
    uses_gateway_lock = False
    supports_parallel_runs = True

    def __init__(self) -> None:
        self._config: QwenPawConfig | None = None

    def slugify_model(self, model_id: str) -> str:
        return default_slugify_model(model_id)

    def make_agent_id(self, model_id: str) -> str:
        return default_agent_id(model_id)

    def initialize_run(self, context: BackendRunContext) -> None:
        context.agent_workspace.mkdir(parents=True, exist_ok=True)
        config = self._load_config()
        self._check_health(config)
        self._config = config

    def finalize_run(self, context: BackendRunContext) -> None:
        return None

    def execute_task(
        self,
        *,
        task: Task,
        context: BackendRunContext,
        attempt_run_id: str,
    ) -> Dict[str, Any]:
        config = self._config
        if config is None:
            config = self._load_config()
            self._check_health(config)
        logger.info("🤖 qwenpaw backend [%s] starting task: %s", context.agent_id, task.task_id)
        start_time = time.time()
        session_id = f"{safe_path_component(attempt_run_id)}_{safe_path_component(task.task_id)}_{int(start_time * 1000)}"
        chat_scope = _qwenpaw_chat_scope(
            context=context,
            task=task,
            attempt_run_id=attempt_run_id,
        )
        workspace = backend_task_workspace(
            context=context, attempt_run_id=attempt_run_id, task=task
        )
        api_group = None
        api_endpoints: Dict[str, Any] = {}
        api_audit: Dict[str, Any] = {}
        stdout = ""
        stderr = ""
        exit_code = 0
        transcript: List[Dict[str, Any]] = []
        transcript_source = "qwenpaw_service_no_transcript"
        usage = zero_usage(request_count=0)
        usage_source = "unavailable"
        usage_delta_contamination_risk = False
        usage_delta_disabled_reason: str | None = None
        run_workers = max(_safe_int(context.metadata.get("run_workers", 1)), 1)
        usage_delta_allowed = config.usage_delta_enabled
        if run_workers > 1:
            usage_delta_allowed = False
            if config.usage_delta_enabled:
                usage_delta_disabled_reason = "parallel_run_workers"
        status = "success"
        timed_out = False
        service_agent_id: str | None = None
        created_service_agent_id: str | None = None

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

            prompts = session_prompts(task)
            request_count = max(1, len(prompts))
            usage = zero_usage(request_count=request_count)
            if len(prompts) > 1:
                logger.info("📋 Multi-session task with %d sessions", len(prompts))

            timeout_budget = task.timeout_seconds * context.timeout_multiplier
            process_outputs: List[str] = []
            event_usage_total = zero_usage(request_count=0)
            model_slot = _parse_model_slot(context.model)
            usage_before: Dict[str, Any] | None = None

            remaining = timeout_budget - (time.time() - start_time)
            if remaining <= 0:
                timed_out = True
                status = "timeout"
                exit_code = -1
                stderr = "qwenpaw execution timed out before creating service agent"
            else:
                try:
                    service_agent_id = self._create_task_agent(
                        config=config,
                        context=context,
                        task=task,
                        attempt_run_id=attempt_run_id,
                        session_id=session_id,
                        workspace=workspace,
                        timeout_seconds=_request_timeout(config=config, remaining=remaining),
                    )
                    created_service_agent_id = service_agent_id
                    _suppress_workspace_bootstrap(workspace)
                except QwenPawTimeoutError as exc:
                    timed_out = True
                    status = "timeout"
                    exit_code = -1
                    stderr = f"qwenpaw service agent creation timed out: {exc}"
                except QwenPawRequestError as exc:
                    status = "error"
                    exit_code = -1
                    stderr = f"qwenpaw service agent creation failed: {exc}"
                except Exception as exc:  # noqa: BLE001
                    status = "error"
                    exit_code = -1
                    stderr = f"qwenpaw service agent creation failed: {exc}"

            if status == "success" and service_agent_id and usage_delta_allowed:
                remaining = timeout_budget - (time.time() - start_time)
                if remaining > 0:
                    try:
                        usage_before = _fetch_token_usage_snapshot(
                            config=config,
                            provider_id=model_slot["provider_id"],
                            model=model_slot["model"],
                            timeout_seconds=_usage_snapshot_timeout(
                                config=config, remaining=remaining
                            ),
                        )
                    except QwenPawRequestError as exc:
                        logger.debug("qwenpaw token usage pre-snapshot unavailable: %s", exc)
                    except Exception as exc:  # noqa: BLE001 - usage is best-effort
                        logger.debug("qwenpaw token usage pre-snapshot failed: %s", exc)

            if status == "success" and service_agent_id:
                for prompt in prompts:
                    remaining = timeout_budget - (time.time() - start_time)
                    if remaining <= 0:
                        timed_out = True
                        status = "timeout"
                        exit_code = -1
                        stderr = _append_stderr(
                            stderr, "qwenpaw execution timed out before completing all prompts"
                        )
                        break
                    try:
                        event = self._post_agent_process(
                            config=config,
                            agent_id=service_agent_id,
                            task=task,
                            session_id=session_id,
                            chat_scope=chat_scope,
                            prompt=prompt,
                            timeout_seconds=_request_timeout(config=config, remaining=remaining),
                        )
                        output_text = _extract_output_text(event).strip()
                        process_outputs.append(output_text)
                        raw_usage = _event_usage(event)
                        if raw_usage is not None:
                            prompt_usage = _normalize_qwenpaw_usage(raw_usage, request_count=1)
                            if _safe_int(prompt_usage.get("request_count")) == 0:
                                prompt_usage["request_count"] = 1
                            if _usage_has_tokens_or_cost(prompt_usage):
                                event_usage_total = _add_usage(event_usage_total, prompt_usage)
                                usage = dict(event_usage_total)
                                usage_source = "qwenpaw_event"
                    except QwenPawTimeoutError as exc:
                        timed_out = True
                        status = "timeout"
                        exit_code = -1
                        stderr = _append_stderr(stderr, f"qwenpaw service request timed out: {exc}")
                        break
                    except QwenPawRequestError as exc:
                        status = "error"
                        exit_code = -1
                        stderr = _append_stderr(stderr, f"qwenpaw service request failed: {exc}")
                        break
                    except (
                        Exception
                    ) as exc:  # noqa: BLE001 - surface service failures as task errors
                        status = "error"
                        exit_code = -1
                        stderr = _append_stderr(stderr, f"qwenpaw service execution failed: {exc}")
                        logger.warning("   %s", stderr)
                        break

            stdout = "\n\n".join(output for output in process_outputs if output)

            if status == "success" and service_agent_id:
                remaining = timeout_budget - (time.time() - start_time)
                if remaining <= 0:
                    timed_out = True
                    status = "timeout"
                    exit_code = -1
                    stderr = _append_stderr(
                        stderr, "qwenpaw execution timed out before fetching chat history"
                    )
                else:
                    try:
                        raw_messages = self._fetch_chat_history_messages(
                            config=config,
                            agent_id=service_agent_id,
                            session_id=session_id,
                            chat_scope=chat_scope,
                            timeout_seconds=_request_timeout(config=config, remaining=remaining),
                        )
                        transcript = _raw_messages_to_transcript(raw_messages)
                        if transcript:
                            transcript_source = "qwenpaw_service_chat_history"
                    except QwenPawRequestError as exc:
                        logger.warning("qwenpaw chat history fetch failed: %s", exc)
                    except Exception as exc:  # noqa: BLE001 - history is best-effort
                        logger.warning("qwenpaw chat history fetch failed: %s", exc)

            if not transcript:
                transcript = _process_outputs_transcript_fallback(prompts, process_outputs)
                if transcript:
                    transcript_source = "qwenpaw_service_process_fallback"
            if not transcript:
                fallback_prompt = "\n\n".join(prompts)
                transcript = stdout_transcript_fallback(fallback_prompt, stdout)
                if transcript:
                    transcript_source = "qwenpaw_service_stdout_fallback"
            if not transcript and status == "success":
                status = "error"
                exit_code = -1
                stderr = _append_stderr(stderr, "qwenpaw service produced no transcript")

            if usage_delta_allowed and not _usage_has_tokens_or_cost(usage):
                remaining = timeout_budget - (time.time() - start_time)
                if remaining > 0:
                    try:
                        usage_after = _fetch_token_usage_snapshot(
                            config=config,
                            provider_id=model_slot["provider_id"],
                            model=model_slot["model"],
                            timeout_seconds=_usage_snapshot_timeout(
                                config=config, remaining=remaining
                            ),
                        )
                        delta_usage = _usage_delta(
                            usage_before,
                            usage_after,
                            request_count=request_count,
                        )
                        if delta_usage is not None:
                            usage = delta_usage
                            usage_source = "qwenpaw_token_usage_delta"
                            usage_delta_contamination_risk = True
                    except QwenPawRequestError as exc:
                        logger.debug("qwenpaw token usage post-snapshot unavailable: %s", exc)
                    except Exception as exc:  # noqa: BLE001 - usage is best-effort
                        logger.debug("qwenpaw token usage post-snapshot failed: %s", exc)

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
            return augment_execution_result(
                result,
                context=context,
                transcript_source=transcript_source,
                base_url=config.base_url,
                service_agent_id=service_agent_id,
                delete_agent=config.delete_agent,
                usage_source=usage_source,
                usage_delta_contamination_risk=usage_delta_contamination_risk,
                usage_delta_disabled_reason=usage_delta_disabled_reason,
                qwenpaw_user_id=chat_scope.user_id,
                qwenpaw_channel=chat_scope.channel,
            )
        finally:
            if created_service_agent_id and config.delete_agent:
                try:
                    self._delete_task_agent(config=config, agent_id=created_service_agent_id)
                except Exception as exc:  # noqa: BLE001 - cleanup should not mask task result
                    logger.warning(
                        "failed to delete qwenpaw service agent %s: %s",
                        created_service_agent_id,
                        exc,
                    )
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

    def _load_config(self) -> QwenPawConfig:
        base_url = os.environ.get("ACTBENCH_QWENPAW_BASE_URL", DEFAULT_QWENPAW_BASE_URL).strip()
        if not base_url:
            base_url = DEFAULT_QWENPAW_BASE_URL
        agent_prefix = os.environ.get(
            "ACTBENCH_QWENPAW_AGENT_PREFIX", DEFAULT_QWENPAW_AGENT_PREFIX
        ).strip()
        if not agent_prefix:
            agent_prefix = DEFAULT_QWENPAW_AGENT_PREFIX
        return QwenPawConfig(
            base_url=base_url.rstrip("/"),
            api_key=os.environ.get("ACTBENCH_QWENPAW_API_KEY") or None,
            timeout_seconds=_load_timeout_seconds(),
            agent_prefix=agent_prefix,
            delete_agent=_env_flag("ACTBENCH_QWENPAW_DELETE_AGENT", default=True),
            headless_tool_guard=os.environ.get("ACTBENCH_QWENPAW_HEADLESS_TOOL_GUARD"),
            usage_delta_enabled=_env_flag("ACTBENCH_QWENPAW_USAGE_DELTA", default=True),
        )

    def _check_health(self, config: QwenPawConfig) -> None:
        url = _join_url(config.base_url, "/api/version")
        try:
            response = _request_json(
                url,
                method="GET",
                api_key=config.api_key,
                timeout_seconds=config.timeout_seconds or QWENPAW_HEALTH_TIMEOUT_SECONDS,
            )
        except QwenPawRequestError as exc:
            raise BackendInitializationError(
                f"qwenpaw backend could not reach QwenPaw service at {url}: {exc}. "
                "Start QwenPaw first or set ACTBENCH_QWENPAW_BASE_URL."
            ) from exc
        if not isinstance(response, dict):
            raise BackendInitializationError(
                f"qwenpaw backend received unexpected health response from {url}: "
                f"{type(response).__name__}"
            )

    def _create_task_agent(
        self,
        *,
        config: QwenPawConfig,
        context: BackendRunContext,
        task: Task,
        attempt_run_id: str,
        session_id: str,
        workspace: Path,
        timeout_seconds: float,
    ) -> str:
        requested_agent_id = _service_agent_id(
            config=config,
            context=context,
            task=task,
            attempt_run_id=attempt_run_id,
            session_id=session_id,
        )
        payload: Dict[str, Any] = {
            "id": requested_agent_id,
            "name": f"ActBench {task.task_id}",
            "description": f"ActBench task {task.task_id} attempt {attempt_run_id}",
            "workspace_dir": str(workspace),
            "skill_names": _enabled_skill_names(workspace),
            "active_model": _parse_model_slot(context.model),
        }
        response = _request_json(
            _join_url(config.base_url, "/api/agents"),
            method="POST",
            api_key=config.api_key,
            payload=payload,
            timeout_seconds=timeout_seconds,
        )
        if not isinstance(response, dict):
            raise QwenPawRequestError(
                f"unexpected agent create response type: {type(response).__name__}"
            )
        agent_id = response.get("id") or requested_agent_id
        if not isinstance(agent_id, str) or not agent_id.strip():
            raise QwenPawRequestError("agent create response did not include a valid id")
        return agent_id.strip()

    def _post_agent_process(
        self,
        *,
        config: QwenPawConfig,
        agent_id: str,
        task: Task,
        session_id: str,
        chat_scope: QwenPawChatScope,
        prompt: str,
        timeout_seconds: float,
    ) -> Dict[str, Any]:
        request_context: Dict[str, Any] = {
            "source": "actbench",
            "task_id": task.task_id,
            "session_id": session_id,
            "user_id": chat_scope.user_id,
            "channel": chat_scope.channel,
        }
        if config.headless_tool_guard is not None:
            request_context["_headless_tool_guard"] = config.headless_tool_guard
        payload = {
            "session_id": session_id,
            "user_id": chat_scope.user_id,
            "channel": chat_scope.channel,
            "input": [
                {
                    "role": "user",
                    "content": [{"type": "text", "text": prompt}],
                }
            ],
            "request_context": request_context,
        }
        return _post_sse_json(
            _join_url(config.base_url, "/api/agent/process"),
            api_key=config.api_key,
            payload=payload,
            timeout_seconds=timeout_seconds,
            headers={"X-Agent-Id": agent_id},
        )

    def _fetch_chat_history_messages(
        self,
        *,
        config: QwenPawConfig,
        agent_id: str,
        session_id: str,
        chat_scope: QwenPawChatScope,
        timeout_seconds: float | None = None,
    ) -> List[Any]:
        request_timeout = (
            timeout_seconds or config.timeout_seconds or QWENPAW_HEALTH_TIMEOUT_SECONDS
        )
        errors: List[str] = []
        scoped_agent_id = urllib.parse.quote(agent_id, safe="")
        scoped_user_id = urllib.parse.quote(chat_scope.user_id, safe="")
        scoped_channel = urllib.parse.quote(chat_scope.channel, safe="")
        routes = [
            (
                f"/api/agents/{scoped_agent_id}/chats"
                f"?user_id={scoped_user_id}"
                f"&channel={scoped_channel}",
                f"/api/agents/{scoped_agent_id}/chats/{{chat_id}}",
            ),
            (
                f"/api/chats?user_id={scoped_user_id}"
                f"&channel={scoped_channel}",
                "/api/chats/{chat_id}",
            ),
        ]
        for list_path, detail_template in routes:
            try:
                chats = _request_json(
                    _join_url(config.base_url, list_path),
                    method="GET",
                    api_key=config.api_key,
                    timeout_seconds=request_timeout,
                )
                chat_id = _matching_chat_id(chats, session_id=session_id)
                if not chat_id:
                    continue
                detail_path = detail_template.format(chat_id=urllib.parse.quote(chat_id, safe=""))
                history = _request_json(
                    _join_url(config.base_url, detail_path),
                    method="GET",
                    api_key=config.api_key,
                    timeout_seconds=request_timeout,
                )
                if not isinstance(history, dict):
                    return []
                messages = history.get("messages")
                return messages if isinstance(messages, list) else []
            except QwenPawRequestError as exc:
                errors.append(str(exc))
        if errors:
            raise QwenPawRequestError("unable to fetch qwenpaw chat history: " + "; ".join(errors))
        return []

    def _delete_task_agent(self, *, config: QwenPawConfig, agent_id: str) -> None:
        if not agent_id or agent_id == "default":
            return
        _request_json(
            _join_url(config.base_url, f"/api/agents/{urllib.parse.quote(agent_id, safe='')}"),
            method="DELETE",
            api_key=config.api_key,
            timeout_seconds=config.timeout_seconds or QWENPAW_HEALTH_TIMEOUT_SECONDS,
        )


def _join_url(base_url: str, path: str) -> str:
    if path.startswith("http://") or path.startswith("https://"):
        return path
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"


def _request_text(
    url: str,
    *,
    method: str,
    timeout_seconds: float,
    api_key: str | None = None,
    payload: Any | None = None,
    headers: Dict[str, str] | None = None,
) -> str:
    request_headers = {"Accept": "application/json"}
    if headers:
        request_headers.update(headers)
    data = None
    if api_key:
        request_headers["Authorization"] = f"Bearer {api_key}"
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        request_headers["Content-Type"] = "application/json"

    request = urllib.request.Request(url, data=data, headers=request_headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            return response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        if exc.code in {408, 504}:
            raise QwenPawTimeoutError(
                f"request to {url} timed out with HTTP {exc.code}: {_summarize_body(body)}"
            ) from exc
        raise QwenPawRequestError(f"HTTP {exc.code} {exc.reason}: {_summarize_body(body)}") from exc
    except urllib.error.URLError as exc:
        reason = getattr(exc, "reason", exc)
        if isinstance(reason, (TimeoutError, socket.timeout)):
            raise QwenPawTimeoutError(f"request to {url} timed out") from exc
        raise QwenPawRequestError(f"request to {url} failed: {reason}") from exc
    except (TimeoutError, socket.timeout) as exc:
        raise QwenPawTimeoutError(f"request to {url} timed out") from exc


def _request_json(
    url: str,
    *,
    method: str,
    timeout_seconds: float,
    api_key: str | None = None,
    payload: Any | None = None,
    headers: Dict[str, str] | None = None,
) -> Any:
    body = _request_text(
        url,
        method=method,
        timeout_seconds=timeout_seconds,
        api_key=api_key,
        payload=payload,
        headers=headers,
    )
    if not body.strip():
        return {}
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError as exc:
        raise QwenPawRequestError(f"invalid JSON response: {_summarize_body(body)}") from exc
    if isinstance(parsed, dict):
        if parsed.get("error"):
            raise QwenPawRequestError(str(parsed["error"]))
        if parsed.get("status") == "error":
            raise QwenPawRequestError(str(parsed.get("msg") or parsed.get("data") or parsed))
    return parsed


def _post_sse_json(
    url: str,
    *,
    timeout_seconds: float,
    api_key: str | None,
    payload: Dict[str, Any],
    headers: Dict[str, str] | None = None,
) -> Dict[str, Any]:
    request_headers = {"Accept": "text/event-stream, application/json"}
    if headers:
        request_headers.update(headers)
    if api_key:
        request_headers["Authorization"] = f"Bearer {api_key}"
    request_headers["Content-Type"] = "application/json"
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=request_headers,
        method="POST",
    )
    deadline = time.monotonic() + max(timeout_seconds, 0.001)
    events: List[Dict[str, Any]] = []
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            for raw_line in response:
                if time.monotonic() > deadline:
                    raise QwenPawTimeoutError(f"request to {url} timed out")
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line or line.startswith(":"):
                    continue
                if not line.startswith("data:"):
                    continue
                data = line[len("data:") :].strip()
                if not data or data == "[DONE]":
                    continue
                try:
                    event = json.loads(data)
                except json.JSONDecodeError as exc:
                    raise QwenPawRequestError(
                        f"invalid SSE JSON event from {url}: {_summarize_body(data)}"
                    ) from exc
                if not isinstance(event, dict):
                    continue
                if event.get("error"):
                    raise QwenPawRequestError(str(event.get("error")))
                events.append(event)
                if time.monotonic() > deadline:
                    raise QwenPawTimeoutError(f"request to {url} timed out")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        if exc.code in {408, 504}:
            raise QwenPawTimeoutError(
                f"request to {url} timed out with HTTP {exc.code}: {_summarize_body(body)}"
            ) from exc
        raise QwenPawRequestError(f"HTTP {exc.code} {exc.reason}: {_summarize_body(body)}") from exc
    except urllib.error.URLError as exc:
        reason = getattr(exc, "reason", exc)
        if isinstance(reason, (TimeoutError, socket.timeout)):
            raise QwenPawTimeoutError(f"request to {url} timed out") from exc
        raise QwenPawRequestError(f"request to {url} failed: {reason}") from exc
    except (TimeoutError, socket.timeout) as exc:
        raise QwenPawTimeoutError(f"request to {url} timed out") from exc
    return _merge_sse_events(events)


def _merge_sse_events(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not events:
        return {}
    merged = dict(events[-1])
    text_parts: List[str] = []
    usage_total = zero_usage(request_count=0)
    for event in events:
        text = _extract_output_text(event)
        if text:
            text_parts.append(text)
        raw_usage = _usage_from_candidate(event)
        if raw_usage is not None:
            usage = _normalize_qwenpaw_usage(raw_usage, request_count=0)
            if _usage_has_tokens_or_cost(usage) or _safe_int(usage.get("request_count")) > 0:
                usage_total = _add_usage(usage_total, usage)
    merged[_SSE_EVENTS_KEY] = events
    if text_parts:
        merged[_SSE_AGGREGATED_TEXT_KEY] = "".join(text_parts)
    if _usage_has_tokens_or_cost(usage_total) or _safe_int(usage_total.get("request_count")) > 0:
        merged[_SSE_AGGREGATED_USAGE_KEY] = usage_total
    return merged


def _raw_messages_to_transcript(raw_messages: Any) -> List[Dict[str, Any]]:
    if not isinstance(raw_messages, list):
        return []
    transcript: List[Dict[str, Any]] = []
    for item in raw_messages:
        msg = item[0] if isinstance(item, (list, tuple)) and item else item
        entry = _msg_to_transcript_entry(msg)
        if entry is not None:
            transcript.append(entry)
    return transcript


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
    if not isinstance(message, dict):
        message = {"role": "assistant", "content": [{"type": "text", "text": str(message)}]}
    return _normalize_qwenpaw_message(message)


def _normalize_qwenpaw_message(message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if isinstance(message.get("message"), dict):
        message = message["message"]
    message_type = str(message.get("type") or "").strip()
    if message_type == "plugin_call":
        content_blocks = []
        for item in _content_data_items(message.get("content")):
            block = _tool_call_to_content_block(item)
            if block is not None:
                content_blocks.append(block)
        if not content_blocks:
            return None
        return {"type": "message", "message": {"role": "assistant", "content": content_blocks}}
    if message_type == "plugin_call_output":
        content_blocks = []
        for item in _content_data_items(message.get("content")):
            block = {
                "type": "toolResult",
                "text": _content_to_text(item.get("output")),
            }
            tool_call_id = item.get("call_id") or item.get("id") or item.get("tool_call_id")
            tool_name = item.get("name") or item.get("tool_name")
            if tool_call_id:
                block["tool_call_id"] = str(tool_call_id)
            if tool_name:
                block["name"] = str(tool_name)
            content_blocks.append(block)
        if not content_blocks:
            return None
        return {"type": "message", "message": {"role": "toolResult", "content": content_blocks}}

    role = str(message.get("role") or "").strip()
    if role in {"system", "developer"}:
        return None
    if role in {"tool", "tool_result", "toolResult"}:
        block: Dict[str, Any] = {
            "type": "toolResult",
            "text": _content_to_text(message.get("content")),
        }
        tool_call_id = message.get("tool_call_id") or message.get("id")
        tool_name = message.get("tool_name") or message.get("name")
        if tool_call_id:
            block["tool_call_id"] = str(tool_call_id)
        if tool_name:
            block["name"] = str(tool_name)
        return {"type": "message", "message": {"role": "toolResult", "content": [block]}}

    if role == "user":
        content = _normalize_user_content(message.get("content"))
        if not content:
            return None
        return {"type": "message", "message": {"role": "user", "content": content}}

    if role != "assistant":
        return None

    content_blocks = _normalize_assistant_content(message.get("content"))
    for tool_call in _coerce_tool_calls(message.get("tool_calls")):
        block = _tool_call_to_content_block(tool_call)
        if block is not None:
            content_blocks.append(block)
    if isinstance(message.get("function_call"), dict):
        block = _tool_call_to_content_block(message["function_call"])
        if block is not None:
            content_blocks.append(block)
    if not content_blocks:
        return None
    return {"type": "message", "message": {"role": "assistant", "content": content_blocks}}


def _content_data_items(content: Any) -> List[Dict[str, Any]]:
    if isinstance(content, dict):
        data = content.get("data")
        return [data] if isinstance(data, dict) else [content]
    if not isinstance(content, list):
        return []
    items: List[Dict[str, Any]] = []
    for item in content:
        if not isinstance(item, dict):
            continue
        data = item.get("data")
        if isinstance(data, dict):
            items.append(data)
        else:
            items.append(item)
    return items


def _normalize_user_content(content: Any) -> List[Any]:
    if content is None:
        return []
    if isinstance(content, str):
        return [content] if content.strip() else []
    if isinstance(content, list):
        normalized: List[Any] = []
        for item in content:
            if isinstance(item, str):
                if item.strip():
                    normalized.append(item)
            elif isinstance(item, dict):
                text = item.get("text") or item.get("content")
                normalized.append(
                    str(text) if text is not None else json.dumps(item, ensure_ascii=False)
                )
            else:
                normalized.append(str(item))
        return normalized
    return [str(content)]


def _normalize_assistant_content(content: Any) -> List[Dict[str, Any]]:
    blocks: List[Dict[str, Any]] = []
    if content is None:
        return blocks
    if isinstance(content, str):
        if content.strip():
            blocks.append({"type": "text", "text": content})
        return blocks
    if isinstance(content, dict):
        block = _assistant_content_item_to_block(content)
        return [block] if block is not None else []
    if isinstance(content, list):
        for item in content:
            if isinstance(item, str):
                if item.strip():
                    blocks.append({"type": "text", "text": item})
                continue
            if isinstance(item, dict):
                block = _assistant_content_item_to_block(item)
                if block is not None:
                    blocks.append(block)
        return blocks
    return [{"type": "text", "text": str(content)}]


def _assistant_content_item_to_block(item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    item_type = str(item.get("type") or "")
    if item_type in {"toolCall", "tool_use", "function"} or "function" in item:
        return _tool_call_to_content_block(item)
    if item.get("name") and ("arguments" in item or "input" in item):
        return _tool_call_to_content_block(item)
    text = item.get("text") or item.get("content")
    if text is not None:
        text_value = _content_to_text(text)
        if text_value.strip():
            return {"type": "text", "text": text_value}
    return None


def _coerce_tool_calls(value: Any) -> List[Dict[str, Any]]:
    if value is None or value == "":
        return []
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return []
        return _coerce_tool_calls(parsed)
    if isinstance(value, dict):
        return [value]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    return []


def _tool_call_to_content_block(call: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    function = call.get("function") if isinstance(call.get("function"), dict) else {}
    name = call.get("name") or function.get("name")
    if not name:
        return None
    raw_arguments = call.get("arguments")
    if raw_arguments is None:
        raw_arguments = call.get("input")
    if raw_arguments is None:
        raw_arguments = function.get("arguments")
    block: Dict[str, Any] = {
        "type": "toolCall",
        "name": str(name),
        "arguments": _coerce_tool_arguments(raw_arguments),
    }
    call_id = call.get("id") or call.get("call_id") or call.get("tool_call_id")
    if call_id:
        block["id"] = str(call_id)
    return block


def _coerce_tool_arguments(value: Any) -> Any:
    if value is None or value == "":
        return {}
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return {"raw": value}
    return {"raw": str(value)}


def _content_to_text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text") or item.get("content")
                parts.append(
                    str(text) if text is not None else json.dumps(item, ensure_ascii=False)
                )
            else:
                parts.append(str(item))
        return "".join(parts)
    if isinstance(content, dict):
        text = content.get("text") or content.get("content")
        return str(text) if text is not None else json.dumps(content, ensure_ascii=False)
    return str(content)


def _normalize_qwenpaw_usage(raw_usage: Any, *, request_count: int) -> Dict[str, Any]:
    usage = zero_usage(request_count=request_count)
    if not isinstance(raw_usage, dict):
        return usage
    input_tokens = _first_present(
        raw_usage,
        "input_tokens",
        "prompt_tokens",
        "inputTokens",
        "promptTokens",
        "total_prompt_tokens",
        "input",
        "prompt",
        default=0,
    )
    output_tokens = _first_present(
        raw_usage,
        "output_tokens",
        "completion_tokens",
        "outputTokens",
        "completionTokens",
        "total_completion_tokens",
        "output",
        "completion",
        default=0,
    )
    total_tokens = _first_present(
        raw_usage,
        "total_tokens",
        "totalTokens",
        "total",
        default=None,
    )
    if total_tokens is None:
        total_tokens = _safe_int(input_tokens) + _safe_int(output_tokens)
    cost = _first_present(
        raw_usage,
        "cost_usd",
        "estimated_cost_usd",
        "total_cost_usd",
        "totalCostUsd",
        "total_cost",
        "totalCost",
        "cost",
        default=0.0,
    )
    if isinstance(cost, dict):
        cost = _first_present(cost, "total", "usd", "cost_usd", default=0.0)
    usage["input_tokens"] = _safe_int(input_tokens)
    usage["output_tokens"] = _safe_int(output_tokens)
    usage["cache_read_tokens"] = _safe_int(
        _first_present(
            raw_usage, "cache_read_tokens", "cacheReadTokens", "cacheRead", "cache_read", default=0
        )
    )
    usage["cache_write_tokens"] = _safe_int(
        _first_present(
            raw_usage,
            "cache_write_tokens",
            "cacheWriteTokens",
            "cacheWrite",
            "cache_write",
            default=0,
        )
    )
    usage["total_tokens"] = _safe_int(total_tokens)
    usage["cost_usd"] = _safe_float(cost)
    usage["request_count"] = _safe_int(
        _first_present(
            raw_usage,
            "request_count",
            "requestCount",
            "call_count",
            "callCount",
            "total_calls",
            "calls",
            "requests",
            default=request_count,
        )
    )
    return usage


def _request_timeout(*, config: QwenPawConfig, remaining: float) -> float:
    if config.timeout_seconds is None:
        return max(remaining, 0.001)
    return max(min(config.timeout_seconds, remaining), 0.001)


def _load_timeout_seconds() -> float | None:
    timeout_raw = os.environ.get("ACTBENCH_QWENPAW_TIMEOUT_SECONDS")
    if timeout_raw is None or not timeout_raw.strip():
        return None
    try:
        timeout_seconds = float(timeout_raw)
    except ValueError as exc:
        raise BackendInitializationError(
            f"ACTBENCH_QWENPAW_TIMEOUT_SECONDS must be numeric, got {timeout_raw!r}"
        ) from exc
    if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
        raise BackendInitializationError(
            "ACTBENCH_QWENPAW_TIMEOUT_SECONDS must be a finite positive number"
        )
    return timeout_seconds


def _env_flag(name: str, *, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off"}


def _qwenpaw_chat_scope(
    *,
    context: BackendRunContext,
    task: Task,
    attempt_run_id: str,
) -> QwenPawChatScope:
    raw_parts = [
        context.backend,
        context.run_id,
        context.agent_id,
        attempt_run_id,
        task.task_id,
        str(context.metadata.get("run_worker_label", "")),
    ]
    digest = hashlib.sha1("|".join(raw_parts).encode("utf-8")).hexdigest()[:10]
    attempt_slug = _agent_id_slug(attempt_run_id)
    task_slug = _agent_id_slug(task.task_id)
    return QwenPawChatScope(
        user_id=_bounded_qwenpaw_scope_value(
            f"{QWENPAW_USER_ID}-{attempt_slug}-{task_slug}", digest=digest
        ),
        channel=_bounded_qwenpaw_scope_value(
            f"{QWENPAW_CHANNEL}-{attempt_slug}",
            digest=digest,
            fallback=QWENPAW_CHANNEL,
        ),
    )


def _bounded_qwenpaw_scope_value(
    value: str,
    *,
    digest: str,
    fallback: str = QWENPAW_USER_ID,
    max_length: int = 96,
) -> str:
    slug = _agent_id_slug(value)
    suffix = f"-{digest}"
    max_base = max(max_length - len(suffix), 1)
    base = slug[:max_base].strip("-_") or fallback
    return f"{base}{suffix}"[:max_length].strip("-_")


def _service_agent_id(
    *,
    config: QwenPawConfig,
    context: BackendRunContext,
    task: Task,
    attempt_run_id: str,
    session_id: str,
) -> str:
    raw_parts = [config.agent_prefix, context.agent_id, attempt_run_id, task.task_id, session_id]
    digest = hashlib.sha1("|".join(str(part) for part in raw_parts).encode("utf-8")).hexdigest()[:8]
    base = "-".join(_agent_id_slug(part) for part in raw_parts[:-1])
    base = base.strip("-_") or DEFAULT_QWENPAW_AGENT_PREFIX
    max_base_length = _AGENT_ID_MAX_LENGTH - len(digest) - 1
    base = base[:max_base_length].strip("-_") or DEFAULT_QWENPAW_AGENT_PREFIX
    candidate = f"{base}-{digest}".strip("-_")
    if len(candidate) < 2:
        candidate = f"qp-{digest}"
    if candidate == "default":
        candidate = f"actbench-{digest}"
    return candidate[:_AGENT_ID_MAX_LENGTH].strip("-_")


def _agent_id_slug(value: Any) -> str:
    slug = re.sub(r"[^A-Za-z0-9_-]+", "-", str(safe_path_component(str(value))))
    slug = re.sub(r"[-_]+", "-", slug).strip("-_")
    return slug or "x"


def _parse_model_slot(model_id: str) -> Dict[str, str]:
    provider_id, separator, model = str(model_id).partition("/")
    if not separator:
        provider_id = ""
        model = str(model_id)
    return {"provider_id": provider_id, "model": model}


def _usage_snapshot_timeout(*, config: QwenPawConfig, remaining: float) -> float:
    cap = config.timeout_seconds or QWENPAW_HEALTH_TIMEOUT_SECONDS
    return max(min(cap, remaining), 0.001)


def _fetch_token_usage_snapshot(
    *,
    config: QwenPawConfig,
    provider_id: str,
    model: str,
    timeout_seconds: float,
) -> Dict[str, Any] | None:
    query = urllib.parse.urlencode(
        {key: value for key, value in {"provider": provider_id, "model": model}.items() if value}
    )
    errors: List[str] = []
    for endpoint in _TOKEN_USAGE_ENDPOINTS:
        path = f"{endpoint}?{query}" if query else endpoint
        try:
            payload = _request_json(
                _join_url(config.base_url, path),
                method="GET",
                api_key=config.api_key,
                timeout_seconds=timeout_seconds,
            )
        except QwenPawRequestError as exc:
            errors.append(str(exc))
            continue
        rows = [
            row
            for row in _qwenpaw_usage_rows(payload)
            if _usage_row_matches_model(row, provider_id=provider_id, model=model)
        ]
        if rows:
            return _sum_usage_rows(rows)
    if errors:
        raise QwenPawRequestError("unable to fetch qwenpaw token usage: " + "; ".join(errors))
    return None


def _qwenpaw_usage_rows(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, list):
        rows: List[Dict[str, Any]] = []
        for item in payload:
            rows.extend(_qwenpaw_usage_rows(item))
        return rows
    if not isinstance(payload, dict):
        return []

    rows: List[Dict[str, Any]] = []
    by_model = payload.get("by_model")
    if isinstance(by_model, dict):
        for key, value in by_model.items():
            if isinstance(value, dict):
                row = dict(value)
                row.setdefault("model_key", key)
                rows.append(row)

    for key in ("data", "details", "items", "rows", "records", "usage"):
        nested = payload.get(key)
        if isinstance(nested, (dict, list)):
            rows.extend(_qwenpaw_usage_rows(nested))

    if not rows and _looks_like_usage(payload):
        rows.append(payload)
    return rows


def _usage_row_matches_model(row: Dict[str, Any], *, provider_id: str, model: str) -> bool:
    row_model = _coerce_text(
        _first_present(row, "model", "model_id", "model_name", "modelName", default="")
    )
    row_provider = _coerce_text(
        _first_present(row, "provider", "provider_id", "provider_name", "providerId", default="")
    )
    model_key = _coerce_text(row.get("model_key") or "")
    if row_model and model and row_model != model:
        return False
    if row_provider and provider_id and row_provider != provider_id:
        return False
    if model_key and not row_model and not row_provider:
        return _model_key_matches(model_key, provider_id=provider_id, model=model)
    return True


def _model_key_matches(model_key: str, *, provider_id: str, model: str) -> bool:
    key = model_key.strip()
    if not key:
        return True
    candidates = {model}
    if provider_id and model:
        candidates.add(f"{provider_id}/{model}")
        candidates.add(f"{provider_id}:{model}")
    return key in candidates


def _sum_usage_rows(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    total = zero_usage(request_count=0)
    for row in rows:
        total = _add_usage(total, _normalize_qwenpaw_usage(row, request_count=0))
    return total


def _usage_delta(
    before: Dict[str, Any] | None,
    after: Dict[str, Any] | None,
    *,
    request_count: int,
) -> Dict[str, Any] | None:
    if before is None or after is None:
        return None
    before_usage = _normalize_qwenpaw_usage(before, request_count=0)
    after_usage = _normalize_qwenpaw_usage(after, request_count=0)
    delta = zero_usage(request_count=0)
    for key in (
        "input_tokens",
        "output_tokens",
        "cache_read_tokens",
        "cache_write_tokens",
        "total_tokens",
    ):
        delta[key] = max(_safe_int(after_usage.get(key)) - _safe_int(before_usage.get(key)), 0)
    delta["cost_usd"] = max(
        _safe_float(after_usage.get("cost_usd")) - _safe_float(before_usage.get("cost_usd")),
        0.0,
    )
    request_delta = max(
        _safe_int(after_usage.get("request_count")) - _safe_int(before_usage.get("request_count")),
        0,
    )
    delta["request_count"] = request_delta or request_count
    if delta["total_tokens"] == 0:
        delta["total_tokens"] = delta["input_tokens"] + delta["output_tokens"]
    return delta if _usage_has_tokens_or_cost(delta) else None


def _add_usage(total: Dict[str, Any], increment: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(total)
    for key in (
        "input_tokens",
        "output_tokens",
        "cache_read_tokens",
        "cache_write_tokens",
        "total_tokens",
        "request_count",
    ):
        merged[key] = _safe_int(merged.get(key)) + _safe_int(increment.get(key))
    merged["cost_usd"] = _safe_float(merged.get("cost_usd")) + _safe_float(
        increment.get("cost_usd")
    )
    return merged


def _usage_has_tokens_or_cost(usage: Dict[str, Any]) -> bool:
    return (
        any(
            _safe_int(usage.get(key)) > 0
            for key in (
                "input_tokens",
                "output_tokens",
                "cache_read_tokens",
                "cache_write_tokens",
                "total_tokens",
            )
        )
        or _safe_float(usage.get("cost_usd")) > 0.0
    )


def _first_present(mapping: Dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if key in mapping and mapping[key] is not None:
            return mapping[key]
    return default


def _looks_like_usage(value: Dict[str, Any]) -> bool:
    usage_keys = {
        "input_tokens",
        "output_tokens",
        "prompt_tokens",
        "completion_tokens",
        "inputTokens",
        "outputTokens",
        "promptTokens",
        "completionTokens",
        "total_tokens",
        "totalTokens",
        "total_prompt_tokens",
        "total_completion_tokens",
        "request_count",
        "requestCount",
        "call_count",
        "callCount",
        "total_calls",
    }
    return any(key in value for key in usage_keys)


def _suppress_workspace_bootstrap(workspace: Path) -> None:
    """Prevent QwenPaw's first-message bootstrap hook from rewriting benchmark prompts."""

    bootstrap_marker = workspace / ".bootstrap_completed"
    bootstrap_marker.touch(exist_ok=True)
    bootstrap_path = workspace / "BOOTSTRAP.md"
    if bootstrap_path.exists():
        try:
            bootstrap_path.unlink()
        except OSError as exc:
            logger.warning("failed to remove QwenPaw bootstrap file %s: %s", bootstrap_path, exc)


def _enabled_skill_names(workspace: Path) -> List[str]:
    manifest_path = workspace / "skill.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    skills = manifest.get("skills") if isinstance(manifest, dict) else None
    if not isinstance(skills, dict):
        return []
    names = []
    for name, spec in skills.items():
        if isinstance(spec, dict) and spec.get("enabled") is False:
            continue
        names.append(str(name))
    return sorted(names)


def _matching_chat_id(chats: Any, *, session_id: str) -> str | None:
    if not isinstance(chats, list):
        return None
    for chat in chats:
        if not isinstance(chat, dict):
            continue
        if chat.get("session_id") != session_id:
            continue
        chat_id = chat.get("id")
        if chat_id:
            return str(chat_id)
    return None


def _extract_output_text(event: Dict[str, Any]) -> str:
    output = event.get("output")
    if isinstance(output, list):
        parts: List[str] = []
        for item in output:
            if isinstance(item, dict):
                content = item.get("content")
                if isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get("text") is not None:
                            parts.append(str(block["text"]))
                        elif isinstance(block, str):
                            parts.append(block)
                elif content is not None:
                    parts.append(_content_to_text(content))
                elif item.get("text") is not None:
                    parts.append(str(item["text"]))
            elif isinstance(item, str):
                parts.append(item)
        text = "".join(parts)
        if text:
            return text
    if event.get("text") is not None:
        return str(event["text"])
    if event.get("content") is not None:
        return _content_to_text(event["content"])
    aggregated_text = event.get(_SSE_AGGREGATED_TEXT_KEY)
    return str(aggregated_text) if aggregated_text is not None else ""


def _event_usage(event: Dict[str, Any]) -> Dict[str, Any] | None:
    aggregated_usage = event.get(_SSE_AGGREGATED_USAGE_KEY)
    if isinstance(aggregated_usage, dict):
        return aggregated_usage
    return _usage_from_candidate(event)


def _combine_usage_candidates(candidates: List[Dict[str, Any]]) -> Dict[str, Any] | None:
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]
    total = zero_usage(request_count=0)
    for candidate in candidates:
        total = _add_usage(total, _normalize_qwenpaw_usage(candidate, request_count=0))
    return total


def _usage_from_candidate(candidate: Any, *, depth: int = 0) -> Dict[str, Any] | None:
    if depth > 4:
        return None
    if isinstance(candidate, list):
        usages = []
        for item in candidate:
            usage = _usage_from_candidate(item, depth=depth + 1)
            if usage is not None:
                usages.append(usage)
        return _combine_usage_candidates(usages)
    if not isinstance(candidate, dict):
        return None

    direct_usage = candidate.get("usage")
    if isinstance(direct_usage, dict):
        return direct_usage

    usages = []
    for key in ("metadata", "meta", "_meta", "field_meta", "data", "response", "result", "message"):
        usage = _usage_from_candidate(candidate.get(key), depth=depth + 1)
        if usage is not None:
            usages.append(usage)

    output = candidate.get("output")
    usage = _usage_from_candidate(output, depth=depth + 1)
    if usage is not None:
        usages.append(usage)
    if usages:
        return _combine_usage_candidates(usages)

    return candidate if _looks_like_usage(candidate) else None


def _process_outputs_transcript_fallback(
    prompts: List[str], process_outputs: List[str]
) -> List[Dict[str, Any]]:
    if not process_outputs:
        return []
    transcript: List[Dict[str, Any]] = []
    for index, prompt in enumerate(prompts):
        if prompt.strip():
            transcript.append({"type": "message", "message": {"role": "user", "content": [prompt]}})
        if index < len(process_outputs) and process_outputs[index].strip():
            transcript.append(
                {
                    "type": "message",
                    "message": {
                        "role": "assistant",
                        "content": [{"type": "text", "text": process_outputs[index]}],
                    },
                }
            )
    return transcript


def _summarize_body(body: str, limit: int = 500) -> str:
    text = " ".join(str(body).split())
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _safe_int(value: Any) -> int:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0
    if not math.isfinite(number):
        return 0
    return max(int(number), 0)


def _safe_float(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(number):
        return 0.0
    return number


def _coerce_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _append_stderr(existing: str, message: str) -> str:
    if not message:
        return existing
    if not existing:
        return message
    return f"{existing}\n{message}"
