"""Hermes backend adapter using the non-interactive hermes CLI."""

from __future__ import annotations

import json
import logging
import math
import os
import secrets
import shutil
import subprocess
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Dict, List, Tuple

from lib_mcp_gateway import (
    DEFAULT_MCP_HOST,
    DEFAULT_MCP_PORT,
    ActBenchMcpGatewayProcess,
    check_gateway_admin_health,
    check_gateway_health,
    get_gateway_context_traces,
    register_gateway_context,
    sanitize_api_endpoints,
    start_gateway_subprocess,
    stop_gateway_process,
    unregister_gateway_context,
)
from lib_tasks import Task

from benchmark.backends.base import (
    BackendInitializationError,
    BackendRunContext,
    augment_execution_result,
    default_agent_id,
    default_slugify_model,
)
from benchmark.backends.common import (
    backend_attempt_home,
    backend_task_workspace,
    begin_task_artifacts,
    elapsed_since,
    execution_error_result,
    finish_task_artifacts,
    materialize_task_workspace,
    session_prompts,
    start_declared_api_services,
    stdout_transcript_fallback,
    zero_usage,
)

logger = logging.getLogger(__name__)

DEFAULT_HERMES_EXECUTABLE = "hermes"
DEFAULT_HERMES_MCP_TOOLSET = "actbench"


@dataclass(frozen=True)
class HermesConfig:
    executable: str
    provider: str | None
    model: str
    toolsets: str | None
    timeout_seconds: float | None
    hermes_home: Path
    mcp_enabled: bool
    mcp_autostart: bool
    mcp_host: str
    mcp_port: int
    mcp_public_url: str
    mcp_admin_token: str | None

    @property
    def mcp_admin_url(self) -> str:
        return f"http://{self.mcp_host}:{self.mcp_port}/mcp"


class HermesBackend:
    """ActBench backend that drives Hermes through ``hermes -z`` subprocesses."""

    name = "hermes"
    uses_gateway_lock = False
    supports_parallel_runs = True

    def __init__(self) -> None:
        self._config: HermesConfig | None = None
        self._mcp_gateway: ActBenchMcpGatewayProcess | None = None

    def slugify_model(self, model_id: str) -> str:
        return default_slugify_model(model_id)

    def make_agent_id(self, model_id: str) -> str:
        return default_agent_id(model_id)

    def initialize_run(self, context: BackendRunContext) -> None:
        context.agent_workspace.mkdir(parents=True, exist_ok=True)
        config = self._load_config(context)
        if config.mcp_enabled:
            self._initialize_mcp_gateway(config)
        self._config = config

    def finalize_run(self, context: BackendRunContext) -> None:
        stop_gateway_process(self._mcp_gateway)
        self._mcp_gateway = None

    def execute_task(
        self,
        *,
        task: Task,
        context: BackendRunContext,
        attempt_run_id: str,
    ) -> Dict[str, Any]:
        config = self._config or self._load_config(context)
        logger.info("🤖 Hermes backend [%s] starting task: %s", context.agent_id, task.task_id)
        start_time = time.time()
        session_id = f"{attempt_run_id}_{task.task_id}_{int(start_time * 1000)}"
        workspace = backend_task_workspace(
            context=context, attempt_run_id=attempt_run_id, task=task
        )
        usage_file = workspace.parent / "hermes_usage.json"
        api_group = None
        api_endpoints: Dict[str, Any] = {}
        api_audit: Dict[str, Any] = {}
        mcp_context_id: str | None = None
        stdout = ""
        stderr = ""
        exit_code = 0
        transcript: List[Dict[str, Any]] = []
        transcript_source = "hermes_oneshot_stdout"
        transcript_extraction: Dict[str, Any] | None = None
        usage = zero_usage(request_count=0)
        status = "success"
        timed_out = False

        try:
            materialize_task_workspace(workspace=workspace, skill_dir=context.skill_dir, task=task)
        except Exception as exc:  # noqa: BLE001 - convert setup issues to execution result
            return _augment_hermes_result(
                execution_error_result(
                    context=context,
                    task=task,
                    workspace=workspace,
                    stderr=f"hermes workspace setup failed: {exc}",
                    execution_time=elapsed_since(start_time),
                ),
                context=context,
                config=config,
            )

        config = self._attempt_hermes_config(
            config,
            context=context,
            attempt_run_id=attempt_run_id,
            task=task,
            workspace=workspace,
        )
        try:
            self._write_hermes_config(config)
        except Exception as exc:  # noqa: BLE001 - convert setup issues to execution result
            return _augment_hermes_result(
                execution_error_result(
                    context=context,
                    task=task,
                    workspace=workspace,
                    stderr=f"hermes config setup failed: {exc}",
                    execution_time=elapsed_since(start_time),
                ),
                context=context,
                config=config,
            )

        artifact_key, recorder = begin_task_artifacts(
            context=context,
            task=task,
            attempt_run_id=attempt_run_id,
            session_id=session_id,
            workspace=workspace,
        )

        try:
            timeout_budget = task.timeout_seconds * context.timeout_multiplier
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
                return _augment_hermes_result(
                    execution_error_result(
                        context=context,
                        task=task,
                        workspace=workspace,
                        stderr=stderr,
                        execution_time=elapsed_since(start_time),
                        api_endpoints=_result_api_endpoints(config, api_endpoints),
                        training_artifact_key=artifact_key,
                    ),
                    context=context,
                    config=config,
                )

            if config.mcp_enabled:
                try:
                    mcp_context_id = secrets.token_urlsafe(32)
                    ttl_seconds = max(float(timeout_budget) + 60.0, 60.0)
                    register_gateway_context(
                        mcp_url=config.mcp_admin_url,
                        context_id=mcp_context_id,
                        workspace=workspace,
                        api_endpoints=api_endpoints,
                        ttl_seconds=ttl_seconds,
                        admin_token=config.mcp_admin_token,
                    )
                    logger.info("   ActBench MCP context registered")
                except Exception as exc:  # noqa: BLE001
                    stderr = f"ActBench MCP context registration failed: {exc}"
                    return _augment_hermes_result(
                        execution_error_result(
                            context=context,
                            task=task,
                            workspace=workspace,
                            stderr=stderr,
                            execution_time=elapsed_since(start_time),
                            api_endpoints=_result_api_endpoints(config, api_endpoints),
                            training_artifact_key=artifact_key,
                        ),
                        context=context,
                        config=config,
                    )

            prompts = session_prompts(task)
            effective_prompt = _effective_prompt(
                prompts=prompts,
                mcp_instruction=(
                    _mcp_prompt_instruction(config.mcp_public_url, mcp_context_id)
                    if config.mcp_enabled and mcp_context_id
                    else None
                ),
            )
            remaining = timeout_budget - (time.time() - start_time)
            if remaining <= 0:
                timed_out = True
                status = "timeout"
                exit_code = -1
                stderr = "hermes execution timed out before starting subprocess"
            else:
                request_timeout = _subprocess_timeout(config=config, remaining=remaining)
                try:
                    completed = self._run_hermes_subprocess(
                        config=config,
                        prompt=effective_prompt,
                        workspace=workspace,
                        usage_file=usage_file,
                        timeout_seconds=request_timeout,
                    )
                    stdout = _coerce_text(completed.stdout)
                    stderr = _coerce_text(completed.stderr)
                    exit_code = int(completed.returncode)
                    if exit_code != 0:
                        status = "error"
                    elif not stdout.strip():
                        status = "error"
                        exit_code = -1
                        stderr = (
                            stderr + "\n" if stderr else ""
                        ) + "hermes produced no final response"
                    transcript, transcript_source, transcript_extraction = (
                        _extract_hermes_transcript(
                            config=config,
                            workspace=workspace,
                            effective_prompt=effective_prompt,
                            stdout=stdout,
                            started_at=start_time,
                            timeout_seconds=_transcript_export_timeout(
                                timeout_budget - (time.time() - start_time)
                            ),
                        )
                    )
                except subprocess.TimeoutExpired as exc:
                    timed_out = True
                    status = "timeout"
                    exit_code = -1
                    stdout = _coerce_text(getattr(exc, "stdout", ""))
                    stderr = _coerce_text(getattr(exc, "stderr", ""))
                    message = f"hermes execution timed out after {request_timeout:.1f}s"
                    stderr = (stderr + "\n" if stderr else "") + message
                    transcript, transcript_source, transcript_extraction = (
                        _extract_hermes_transcript(
                            config=config,
                            workspace=workspace,
                            effective_prompt=effective_prompt,
                            stdout=stdout,
                            started_at=start_time,
                            timeout_seconds=_transcript_export_timeout(
                                timeout_budget - (time.time() - start_time)
                            ),
                        )
                    )
                except Exception as exc:  # noqa: BLE001 - surface unexpected backend failures
                    status = "error"
                    exit_code = -1
                    stderr = f"hermes execution failed: {exc}"
                    logger.warning("   %s", stderr)

            usage = _read_usage_file(usage_file, request_count=1 if status != "success" else 0)
            if usage.get("request_count", 0) == 0 and status in {"success", "error", "timeout"}:
                usage["request_count"] = 1

            if config.mcp_enabled and mcp_context_id:
                if transcript_extraction is None:
                    transcript_extraction = {}
                try:
                    trace_response = get_gateway_context_traces(
                        mcp_url=config.mcp_admin_url,
                        context_id=mcp_context_id,
                        admin_token=config.mcp_admin_token,
                    )
                    trace_transcript = _mcp_gateway_traces_to_transcript(
                        trace_response.get("traces")
                    )
                    missing_trace_transcript = _missing_mcp_trace_transcript(
                        transcript=transcript,
                        trace_transcript=trace_transcript,
                    )
                    if trace_transcript:
                        transcript_extraction["mcp_trace_messages_available"] = len(
                            trace_transcript
                        )
                    if missing_trace_transcript:
                        transcript.extend(missing_trace_transcript)
                        transcript_extraction["mcp_trace_messages_appended"] = len(
                            missing_trace_transcript
                        )
                except Exception as exc:  # noqa: BLE001 - tracing must not fail the task
                    logger.warning("   Failed to retrieve ActBench MCP traces: %s", exc)
                    transcript_extraction["mcp_trace_error"] = str(exc)[:500]

            if not transcript and status == "success":
                status = "error"
                exit_code = -1
                stderr = "hermes execution produced no transcript"

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
                "api_endpoints": _result_api_endpoints(config, api_endpoints),
                "training_artifact_key": artifact_key,
            }
            return _augment_hermes_result(
                result,
                context=context,
                config=config,
                transcript_source=transcript_source,
                transcript_extraction=transcript_extraction,
            )
        finally:
            if mcp_context_id:
                try:
                    unregister_gateway_context(
                        mcp_url=config.mcp_admin_url,
                        context_id=mcp_context_id,
                        admin_token=config.mcp_admin_token,
                    )
                except Exception as exc:  # noqa: BLE001 - stale contexts expire by TTL
                    logger.warning("   Failed to unregister ActBench MCP context: %s", exc)
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

    def _load_config(self, context: BackendRunContext) -> HermesConfig:
        executable = _resolve_executable(
            os.environ.get("ACTBENCH_HERMES_BIN", DEFAULT_HERMES_EXECUTABLE).strip()
            or DEFAULT_HERMES_EXECUTABLE
        )
        provider = os.environ.get("ACTBENCH_HERMES_PROVIDER", "").strip() or None
        model = os.environ.get("ACTBENCH_HERMES_MODEL", "").strip() or context.model
        if not model.strip():
            raise BackendInitializationError("hermes backend requires a non-empty model id")
        timeout_seconds = _load_timeout_seconds()
        mcp_enabled = _env_flag("ACTBENCH_HERMES_ENABLE_ACTBENCH_MCP", default=True)
        raw_toolsets = os.environ.get("ACTBENCH_HERMES_TOOLSETS")
        if raw_toolsets is None:
            toolsets = DEFAULT_HERMES_MCP_TOOLSET if mcp_enabled else None
        else:
            toolsets = raw_toolsets.strip() or None

        home_root = os.environ.get("ACTBENCH_HERMES_HOME_ROOT", "").strip()
        if home_root:
            hermes_home = Path(home_root).expanduser() / context.run_id / "hermes_home"
        else:
            hermes_home = context.agent_workspace / "hermes_home"

        mcp_autostart = _env_flag("ACTBENCH_MCP_AUTOSTART", default=True)
        mcp_host = os.environ.get("ACTBENCH_MCP_HOST", DEFAULT_MCP_HOST).strip() or DEFAULT_MCP_HOST
        mcp_port = _env_int("ACTBENCH_MCP_PORT", default=DEFAULT_MCP_PORT)
        default_mcp_url = f"http://{mcp_host}:{mcp_port}/mcp"
        mcp_public_url = os.environ.get("ACTBENCH_MCP_URL", default_mcp_url).strip()
        if mcp_enabled and not mcp_public_url:
            raise BackendInitializationError(
                "ACTBENCH_MCP_URL must not be blank when MCP is enabled"
            )
        mcp_admin_token = os.environ.get("ACTBENCH_MCP_ADMIN_TOKEN", "").strip() or None
        if mcp_enabled and mcp_autostart and mcp_admin_token is None:
            mcp_admin_token = secrets.token_urlsafe(32)

        return HermesConfig(
            executable=executable,
            provider=provider,
            model=model,
            toolsets=toolsets,
            timeout_seconds=timeout_seconds,
            hermes_home=hermes_home,
            mcp_enabled=mcp_enabled,
            mcp_autostart=mcp_autostart,
            mcp_host=mcp_host,
            mcp_port=mcp_port,
            mcp_public_url=mcp_public_url,
            mcp_admin_token=mcp_admin_token,
        )

    def _attempt_hermes_config(
        self,
        config: HermesConfig,
        *,
        context: BackendRunContext,
        attempt_run_id: str,
        task: Task,
        workspace: Path,
    ) -> HermesConfig:
        home_root = os.environ.get("ACTBENCH_HERMES_HOME_ROOT", "").strip()
        hermes_home = backend_attempt_home(
            home_root=home_root,
            context=context,
            attempt_run_id=attempt_run_id,
            task=task,
            workspace=workspace,
            leaf_name="hermes_home",
        )
        return replace(config, hermes_home=hermes_home)

    def _write_hermes_config(self, config: HermesConfig) -> None:
        try:
            config.hermes_home.mkdir(parents=True, exist_ok=True)
            payload: Dict[str, Any] = {}
            if config.mcp_enabled:
                payload["mcp_servers"] = {
                    "actbench": {
                        "enabled": True,
                        "url": config.mcp_public_url,
                    }
                }
            (config.hermes_home / "config.yaml").write_text(
                json.dumps(payload, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        except OSError as exc:
            raise BackendInitializationError(
                f"hermes backend could not write isolated config in {config.hermes_home}: {exc}"
            ) from exc

    def _initialize_mcp_gateway(self, config: HermesConfig) -> None:
        try:
            if config.mcp_autostart:
                try:
                    check_gateway_health(
                        host=config.mcp_host,
                        port=config.mcp_port,
                        timeout_seconds=1.0,
                    )
                except Exception:
                    self._mcp_gateway = start_gateway_subprocess(
                        host=config.mcp_host,
                        port=config.mcp_port,
                        admin_token=config.mcp_admin_token,
                    )
                else:
                    check_gateway_admin_health(
                        mcp_url=config.mcp_admin_url,
                        admin_token=config.mcp_admin_token,
                        timeout_seconds=1.0,
                    )
                    self._mcp_gateway = ActBenchMcpGatewayProcess(
                        process=None,
                        host=config.mcp_host,
                        port=config.mcp_port,
                        mcp_url=config.mcp_admin_url,
                        admin_token=config.mcp_admin_token,
                    )
            else:
                check_gateway_health(host=config.mcp_host, port=config.mcp_port)
                check_gateway_admin_health(
                    mcp_url=config.mcp_admin_url,
                    admin_token=config.mcp_admin_token,
                )
                self._mcp_gateway = ActBenchMcpGatewayProcess(
                    process=None,
                    host=config.mcp_host,
                    port=config.mcp_port,
                    mcp_url=config.mcp_admin_url,
                    admin_token=config.mcp_admin_token,
                )
        except Exception as exc:  # noqa: BLE001
            raise BackendInitializationError(
                "hermes backend could not start or authenticate to the ActBench MCP gateway at "
                f"{config.mcp_admin_url}: {exc}. Set ACTBENCH_MCP_AUTOSTART=0 for an "
                "externally managed gateway or ACTBENCH_HERMES_ENABLE_ACTBENCH_MCP=0 "
                "for weak direct-workspace mode."
            ) from exc
        logger.info("   ActBench MCP gateway ready for Hermes at %s", config.mcp_public_url)

    def _run_hermes_subprocess(
        self,
        *,
        config: HermesConfig,
        prompt: str,
        workspace: Path,
        usage_file: Path,
        timeout_seconds: float,
    ) -> subprocess.CompletedProcess[str]:
        usage_file.parent.mkdir(parents=True, exist_ok=True)
        cmd = [
            config.executable,
            "--model",
            config.model,
            "--usage-file",
            str(usage_file),
        ]
        if config.provider:
            cmd.extend(["--provider", config.provider])
        if config.toolsets:
            cmd.extend(["--toolsets", config.toolsets])
        cmd.extend(["-z", prompt])

        env = os.environ.copy()
        env["HERMES_HOME"] = str(config.hermes_home)
        env.setdefault("NO_COLOR", "1")
        env.pop("ACTBENCH_MCP_ADMIN_TOKEN", None)
        return subprocess.run(
            cmd,
            cwd=str(workspace),
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )


def _run_hermes_sessions_export(
    *,
    config: HermesConfig,
    workspace: Path,
    timeout_seconds: float,
) -> subprocess.CompletedProcess[str]:
    # Export the isolated Hermes home and select the matching task session ourselves.
    # Hermes' CLI filters are user-facing conveniences and have changed behavior across
    # versions; the attempt-scoped HERMES_HOME keeps this bounded while local selection
    # keeps extraction stable.
    cmd = [
        config.executable,
        "sessions",
        "export",
        "--format",
        "jsonl",
        "-",
    ]

    env = os.environ.copy()
    env["HERMES_HOME"] = str(config.hermes_home)
    env.setdefault("NO_COLOR", "1")
    env.pop("ACTBENCH_MCP_ADMIN_TOKEN", None)
    return subprocess.run(
        cmd,
        cwd=str(workspace),
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
        check=False,
    )


def _augment_hermes_result(
    result: Dict[str, Any],
    *,
    context: BackendRunContext,
    config: HermesConfig,
    transcript_source: str = "hermes_oneshot_stdout",
    transcript_extraction: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    return augment_execution_result(
        result,
        context=context,
        transcript_source=transcript_source,
        transcript_extraction=transcript_extraction,
        executable=config.executable,
        provider=config.provider,
        toolsets=config.toolsets,
        hermes_home=str(config.hermes_home),
        mcp_enabled=config.mcp_enabled,
        mcp_public_url=config.mcp_public_url if config.mcp_enabled else None,
    )


def _result_api_endpoints(config: HermesConfig, api_endpoints: Dict[str, Any]) -> Dict[str, Any]:
    if not config.mcp_enabled:
        return api_endpoints
    return sanitize_api_endpoints(api_endpoints)


def _mcp_gateway_traces_to_transcript(raw_traces: Any) -> List[Dict[str, Any]]:
    if not isinstance(raw_traces, list):
        return []
    transcript: List[Dict[str, Any]] = []
    for index, trace in enumerate(raw_traces, 1):
        if not isinstance(trace, dict):
            continue
        name = trace.get("name")
        if not isinstance(name, str) or not name:
            continue
        sequence = trace.get("sequence") or index
        tool_call_id = f"actbench-mcp-{sequence}"
        arguments = trace.get("arguments") if isinstance(trace.get("arguments"), dict) else {}
        arguments = _redact_mcp_trace_value(arguments)
        transcript.append(
            {
                "type": "message",
                "message": {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "toolCall",
                            "name": name,
                            "arguments": arguments,
                            "id": tool_call_id,
                        }
                    ],
                },
            }
        )
        result_block: Dict[str, Any] = {
            "type": "toolResult",
            "text": _mcp_trace_result_text(trace.get("result")),
            "tool_call_id": tool_call_id,
            "name": name,
        }
        if "isError" in trace:
            result_block["isError"] = _coerce_bool(trace.get("isError"))
        transcript.append(
            {
                "type": "message",
                "message": {"role": "toolResult", "content": [result_block]},
            }
        )
    return transcript


def _mcp_trace_result_text(result: Any) -> str:
    if isinstance(result, dict):
        content = result.get("content")
        if isinstance(content, list):
            parts: List[str] = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict):
                    text = item.get("text") or item.get("content")
                    if isinstance(text, str):
                        parts.append(text)
            if parts:
                return "\n".join(parts)
        text = result.get("text")
        if isinstance(text, str):
            return text
    if result is None:
        return ""
    return json.dumps(result, ensure_ascii=False, sort_keys=True, default=str)


def _redact_mcp_trace_value(value: Any, *, key: str = "") -> Any:
    if key and _is_sensitive_mcp_trace_key(key):
        return "[redacted]"
    if isinstance(value, dict):
        redacted: Dict[str, Any] = {}
        for item_key, item_value in value.items():
            key_text = str(item_key)
            if key_text.lower().replace("-", "_") == "context_id":
                continue
            redacted[key_text] = _redact_mcp_trace_value(item_value, key=key_text)
        return redacted
    if isinstance(value, list):
        return [_redact_mcp_trace_value(item) for item in value]
    return value


def _is_sensitive_mcp_trace_key(key: str) -> bool:
    normalized = key.lower().replace("-", "_")
    if normalized in {"context_id", "token", "auth_token", "bearer_token"}:
        return True
    return any(
        fragment in normalized
        for fragment in (
            "authorization",
            "admin_token",
            "api_key",
            "apikey",
            "access_token",
            "refresh_token",
            "password",
            "secret",
            "credential",
            "cookie",
        )
    )


def _missing_mcp_trace_transcript(
    *,
    transcript: List[Dict[str, Any]],
    trace_transcript: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    if not trace_transcript:
        return []
    existing_counts = _actbench_tool_result_counts(transcript)
    missing: List[Dict[str, Any]] = []
    pending_call: Dict[str, Any] | None = None
    for entry in trace_transcript:
        result_signature = _actbench_tool_result_signature(entry)
        if result_signature is None:
            if _entry_has_actbench_tool_call(entry):
                pending_call = entry
            continue
        count = existing_counts.get(result_signature, 0)
        if count > 0:
            existing_counts[result_signature] = count - 1
            pending_call = None
            continue
        if pending_call is not None:
            missing.append(pending_call)
        missing.append(entry)
        pending_call = None
    return missing


def _actbench_tool_result_counts(
    transcript: List[Dict[str, Any]],
) -> Dict[Tuple[str, str, bool], int]:
    counts: Dict[Tuple[str, str, bool], int] = {}
    for entry in transcript:
        signature = _actbench_tool_result_signature(entry)
        if signature is None:
            continue
        counts[signature] = counts.get(signature, 0) + 1
    return counts


def _actbench_tool_result_signature(entry: Dict[str, Any]) -> Tuple[str, str, bool] | None:
    message = entry.get("message") if isinstance(entry, dict) else None
    if not isinstance(message, dict):
        return None
    content = message.get("content") if isinstance(message.get("content"), list) else []
    for block in content:
        if not isinstance(block, dict) or block.get("type") != "toolResult":
            continue
        name = str(block.get("name") or "")
        text = str(block.get("text") or "")
        if not _is_actbench_tool_name(name) or not text.strip():
            continue
        return (_canonical_actbench_tool_name(name), text, _coerce_bool(block.get("isError")))
    return None


def _entry_has_actbench_tool_call(entry: Dict[str, Any]) -> bool:
    message = entry.get("message") if isinstance(entry, dict) else None
    if not isinstance(message, dict):
        return False
    content = message.get("content") if isinstance(message.get("content"), list) else []
    return any(
        isinstance(block, dict)
        and block.get("type") == "toolCall"
        and _is_actbench_tool_name(str(block.get("name") or ""))
        for block in content
    )


def _is_actbench_tool_name(name: str) -> bool:
    return name.startswith("actbench_") or "__actbench__actbench_" in name


def _canonical_actbench_tool_name(name: str) -> str:
    if "__actbench__" in name:
        return name.rsplit("__actbench__", 1)[-1]
    if name.startswith("actbench_actbench_"):
        return name[len("actbench_") :]
    return name


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _extract_hermes_transcript(
    *,
    config: HermesConfig,
    workspace: Path,
    effective_prompt: str,
    stdout: str,
    started_at: float,
    timeout_seconds: float,
) -> Tuple[List[Dict[str, Any]], str, Dict[str, Any]]:
    metadata: Dict[str, Any] = {
        "method": "sessions_export",
        "state_db_exists": (config.hermes_home / "state.db").exists(),
    }

    def fallback(reason: str) -> Tuple[List[Dict[str, Any]], str, Dict[str, Any]]:
        fallback_metadata = dict(metadata)
        fallback_metadata["fallback_reason"] = reason
        return (
            stdout_transcript_fallback(effective_prompt, stdout),
            f"hermes_sessions_export_{reason}_fallback_stdout",
            fallback_metadata,
        )

    if not metadata["state_db_exists"]:
        return fallback("empty")

    try:
        completed = _run_hermes_sessions_export(
            config=config,
            workspace=workspace,
            timeout_seconds=timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        return fallback("timeout")
    except Exception as exc:  # noqa: BLE001 - transcript extraction must not break execution
        metadata["error_type"] = type(exc).__name__
        metadata["error"] = str(exc)[:200]
        return fallback("failed")

    metadata["export_exit_code"] = int(completed.returncode)
    if completed.returncode != 0:
        return fallback("failed")

    records, parse_errors = _parse_hermes_export_jsonl(_coerce_text(completed.stdout))
    metadata["records_seen"] = len(records)
    metadata["parse_errors"] = len(parse_errors)
    if parse_errors:
        metadata["first_parse_error"] = parse_errors[0][:200]
    if not records:
        return fallback("empty")

    selected_records, selection_metadata = _select_hermes_export_records(
        records=records,
        workspace=workspace,
        model=config.model,
        provider=config.provider,
        started_at=started_at,
    )
    metadata.update(selection_metadata)
    if not selected_records:
        return fallback("empty")

    transcript = _normalize_hermes_export_to_transcript(selected_records)
    metadata["transcript_messages"] = len(transcript)
    if not _has_usable_transcript(transcript):
        return fallback("unusable")

    return transcript, "hermes_sessions_export", metadata


def _parse_hermes_export_jsonl(raw: str) -> Tuple[List[Dict[str, Any]], List[str]]:
    records: List[Dict[str, Any]] = []
    errors: List[str] = []
    for line_no, line in enumerate(raw.splitlines(), 1):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError as exc:
            errors.append(f"line {line_no}: {exc}")
            continue
        if isinstance(parsed, dict):
            records.append(parsed)
        elif isinstance(parsed, list):
            records.extend(item for item in parsed if isinstance(item, dict))
        else:
            errors.append(f"line {line_no}: expected object, got {type(parsed).__name__}")
    return records, errors


def _select_hermes_export_records(
    *,
    records: List[Dict[str, Any]],
    workspace: Path,
    model: str,
    provider: str | None,
    started_at: float,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    session_records = [record for record in records if isinstance(record.get("messages"), list)]
    metadata: Dict[str, Any] = {
        "sessions_seen": len(session_records),
        "records_selected": 0,
    }
    if not session_records:
        metadata["records_selected"] = len(records)
        return records, metadata

    workspace_text = str(workspace)

    def matches_workspace(record: Dict[str, Any]) -> bool:
        cwd = record.get("cwd")
        return not cwd or str(cwd) == workspace_text

    def matches_model(record: Dict[str, Any]) -> bool:
        raw_model = str(record.get("model") or "")
        return not raw_model or raw_model == model

    def matches_provider(record: Dict[str, Any]) -> bool:
        if provider is None:
            return True
        raw_provider = str(record.get("provider") or record.get("billing_provider") or "")
        return not raw_provider or raw_provider == provider

    candidates = [
        record
        for record in session_records
        if matches_workspace(record) and matches_model(record) and matches_provider(record)
    ]
    if not candidates:
        candidates = [record for record in session_records if matches_workspace(record)]
    if not candidates:
        return [], metadata

    recent = [
        record
        for record in candidates
        if _safe_float(record.get("started_at")) >= max(0.0, started_at - 5.0)
    ]
    if recent:
        candidates = recent

    selected = max(candidates, key=_hermes_record_sort_key)
    metadata["records_selected"] = len(selected.get("messages") or [])
    metadata["session_id"] = selected.get("id")
    metadata["selection_ambiguous"] = len(candidates) > 1
    metadata["tool_call_count"] = _safe_int(selected.get("tool_call_count", 0))
    return [selected], metadata


def _hermes_record_sort_key(record: Dict[str, Any]) -> float:
    for key in ("last_active", "ended_at", "started_at", "timestamp"):
        value = _safe_float(record.get(key))
        if value:
            return value
    return 0.0


def _normalize_hermes_export_to_transcript(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    raw_messages: List[Dict[str, Any]] = []
    for record in records:
        messages = record.get("messages")
        if isinstance(messages, list):
            raw_messages.extend(message for message in messages if isinstance(message, dict))
        elif isinstance(record, dict):
            raw_messages.append(record)

    transcript: List[Dict[str, Any]] = []
    for message in raw_messages:
        entry = _normalize_hermes_message(message)
        if entry is not None:
            transcript.append(entry)
    return transcript


def _normalize_hermes_message(message: Dict[str, Any]) -> Dict[str, Any] | None:
    if isinstance(message.get("message"), dict):
        message = message["message"]
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


def _assistant_content_item_to_block(item: Dict[str, Any]) -> Dict[str, Any] | None:
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


def _tool_call_to_content_block(call: Dict[str, Any]) -> Dict[str, Any] | None:
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


def _has_usable_transcript(transcript: List[Dict[str, Any]]) -> bool:
    for entry in transcript:
        if not isinstance(entry, dict) or entry.get("type") != "message":
            continue
        message = entry.get("message") if isinstance(entry.get("message"), dict) else {}
        role = message.get("role")
        content = message.get("content") if isinstance(message.get("content"), list) else []
        if role == "toolResult" and content:
            return True
        if role != "assistant":
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "toolCall":
                return True
            if block.get("type") == "text" and str(block.get("text") or "").strip():
                return True
    return False


def _effective_prompt(*, prompts: List[str], mcp_instruction: str | None) -> str:
    if len(prompts) == 1:
        task_prompt = prompts[0]
    else:
        sessions = [
            "This ActBench task contains multiple sessions. Complete them in order.",
            "",
        ]
        for index, prompt in enumerate(prompts, 1):
            sessions.append(f"Session {index}:")
            sessions.append(prompt)
            sessions.append("")
        task_prompt = "\n".join(sessions).rstrip()
    if not mcp_instruction:
        return task_prompt
    return f"{mcp_instruction}\n\nUser task:\n{task_prompt}"


def _mcp_prompt_instruction(mcp_public_url: str, context_id: str | None) -> str:
    return (
        "ActBench has exposed task-scoped tools through the ActBench MCP server "
        f"named `actbench` at {mcp_public_url}. For this task, always pass "
        f"context_id `{context_id}` exactly when calling ActBench MCP tools. Use "
        "actbench_list_files, actbench_read_file, and actbench_write_file to inspect or "
        "modify the task workspace. Use actbench_get_api_endpoints to discover declared "
        "mock API services, then call them only through actbench_call_api. Do not assume "
        "fixed localhost ports and do not call mock APIs directly."
    )


def _read_usage_file(path: Path, *, request_count: int) -> Dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return zero_usage(request_count=request_count)
    return _normalize_usage(raw, request_count=request_count)


def _normalize_usage(raw_usage: Any, *, request_count: int) -> Dict[str, Any]:
    usage = zero_usage(request_count=request_count)
    if not isinstance(raw_usage, dict):
        return usage
    input_tokens = raw_usage.get("input_tokens", raw_usage.get("prompt_tokens", 0)) or 0
    output_tokens = raw_usage.get("output_tokens", raw_usage.get("completion_tokens", 0)) or 0
    total_tokens = raw_usage.get("total_tokens")
    if total_tokens is None:
        total_tokens = _safe_int(input_tokens) + _safe_int(output_tokens)
    usage["input_tokens"] = _safe_int(input_tokens)
    usage["output_tokens"] = _safe_int(output_tokens)
    usage["cache_read_tokens"] = _safe_int(raw_usage.get("cache_read_tokens", 0))
    usage["cache_write_tokens"] = _safe_int(raw_usage.get("cache_write_tokens", 0))
    usage["total_tokens"] = _safe_int(total_tokens)
    cost = raw_usage.get(
        "cost_usd", raw_usage.get("estimated_cost_usd", raw_usage.get("cost", 0.0))
    )
    usage["cost_usd"] = _safe_float(cost)
    usage["request_count"] = _safe_int(
        raw_usage.get("api_calls", raw_usage.get("request_count", request_count))
    )
    return usage


def _subprocess_timeout(*, config: HermesConfig, remaining: float) -> float:
    if config.timeout_seconds is None:
        return max(remaining, 0.001)
    return max(min(config.timeout_seconds, remaining), 0.001)


def _transcript_export_timeout(remaining: float) -> float:
    try:
        value = float(remaining)
    except (TypeError, ValueError):
        value = 1.0
    if not math.isfinite(value) or value <= 0:
        value = 1.0
    return max(1.0, min(5.0, value))


def _load_timeout_seconds() -> float | None:
    timeout_raw = os.environ.get("ACTBENCH_HERMES_TIMEOUT_SECONDS")
    if timeout_raw is None or not timeout_raw.strip():
        return None
    try:
        timeout_seconds = float(timeout_raw)
    except ValueError as exc:
        raise BackendInitializationError(
            f"ACTBENCH_HERMES_TIMEOUT_SECONDS must be numeric, got {timeout_raw!r}"
        ) from exc
    if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
        raise BackendInitializationError(
            "ACTBENCH_HERMES_TIMEOUT_SECONDS must be a finite positive number"
        )
    return timeout_seconds


def _env_flag(name: str, *, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    raise BackendInitializationError(f"{name} must be a boolean flag, got {raw!r}")


def _env_int(name: str, *, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise BackendInitializationError(f"{name} must be an integer, got {raw!r}") from exc
    if value <= 0 or value > 65535:
        raise BackendInitializationError(f"{name} must be a TCP port in the range 1-65535")
    return value


def _resolve_executable(executable: str) -> str:
    raw = executable.strip() or DEFAULT_HERMES_EXECUTABLE
    expanded = Path(raw).expanduser()
    if expanded.name != raw or os.sep in raw:
        if not expanded.is_file():
            raise BackendInitializationError(f"hermes executable not found: {expanded}")
        return str(expanded)
    resolved = shutil.which(raw)
    if not resolved:
        raise BackendInitializationError(
            f"hermes backend requires the `{raw}` executable on PATH. "
            "Set ACTBENCH_HERMES_BIN to the Hermes CLI path."
        )
    return resolved


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
