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
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

from lib_mcp_gateway import (
    DEFAULT_MCP_HOST,
    DEFAULT_MCP_PORT,
    ActBenchMcpGatewayProcess,
    check_gateway_health,
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
        self._write_hermes_config(config)
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
        session_id = f"{task.task_id}_{int(start_time * 1000)}"
        workspace = backend_task_workspace(context=context, attempt_run_id=attempt_run_id, task=task)
        usage_file = workspace.parent / "hermes_usage.json"
        api_group = None
        api_endpoints: Dict[str, Any] = {}
        api_audit: Dict[str, Any] = {}
        mcp_context_id: str | None = None
        stdout = ""
        stderr = ""
        exit_code = 0
        transcript: List[Dict[str, Any]] = []
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
                        stderr = (stderr + "\n" if stderr else "") + "hermes produced no final response"
                    transcript = stdout_transcript_fallback(effective_prompt, stdout)
                except subprocess.TimeoutExpired as exc:
                    timed_out = True
                    status = "timeout"
                    exit_code = -1
                    stdout = _coerce_text(getattr(exc, "stdout", ""))
                    stderr = _coerce_text(getattr(exc, "stderr", ""))
                    message = f"hermes execution timed out after {request_timeout:.1f}s"
                    stderr = (stderr + "\n" if stderr else "") + message
                    transcript = stdout_transcript_fallback(effective_prompt, stdout)
                except Exception as exc:  # noqa: BLE001 - surface unexpected backend failures
                    status = "error"
                    exit_code = -1
                    stderr = f"hermes execution failed: {exc}"
                    logger.warning("   %s", stderr)

            usage = _read_usage_file(usage_file, request_count=1 if status != "success" else 0)
            if usage.get("request_count", 0) == 0 and status in {"success", "error", "timeout"}:
                usage["request_count"] = 1

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
            return _augment_hermes_result(result, context=context, config=config)
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
            raise BackendInitializationError("ACTBENCH_MCP_URL must not be blank when MCP is enabled")
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
                    self._mcp_gateway = ActBenchMcpGatewayProcess(
                        process=None,
                        host=config.mcp_host,
                        port=config.mcp_port,
                        mcp_url=config.mcp_admin_url,
                        admin_token=config.mcp_admin_token,
                    )
                except Exception:
                    self._mcp_gateway = start_gateway_subprocess(
                        host=config.mcp_host,
                        port=config.mcp_port,
                        admin_token=config.mcp_admin_token,
                    )
            else:
                check_gateway_health(host=config.mcp_host, port=config.mcp_port)
                self._mcp_gateway = ActBenchMcpGatewayProcess(
                    process=None,
                    host=config.mcp_host,
                    port=config.mcp_port,
                    mcp_url=config.mcp_admin_url,
                    admin_token=config.mcp_admin_token,
                )
        except Exception as exc:  # noqa: BLE001
            raise BackendInitializationError(
                "hermes backend could not start or reach the ActBench MCP gateway at "
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


def _augment_hermes_result(
    result: Dict[str, Any],
    *,
    context: BackendRunContext,
    config: HermesConfig,
) -> Dict[str, Any]:
    return augment_execution_result(
        result,
        context=context,
        transcript_source="hermes_oneshot_stdout",
        executable=config.executable,
        provider=config.provider,
        toolsets=config.toolsets,
        mcp_enabled=config.mcp_enabled,
        mcp_public_url=config.mcp_public_url if config.mcp_enabled else None,
    )


def _result_api_endpoints(config: HermesConfig, api_endpoints: Dict[str, Any]) -> Dict[str, Any]:
    if not config.mcp_enabled:
        return api_endpoints
    return sanitize_api_endpoints(api_endpoints)


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
    cost = raw_usage.get("cost_usd", raw_usage.get("estimated_cost_usd", raw_usage.get("cost", 0.0)))
    usage["cost_usd"] = _safe_float(cost)
    usage["request_count"] = _safe_int(raw_usage.get("api_calls", raw_usage.get("request_count", request_count)))
    return usage


def _subprocess_timeout(*, config: HermesConfig, remaining: float) -> float:
    if config.timeout_seconds is None:
        return max(remaining, 0.001)
    return max(min(config.timeout_seconds, remaining), 0.001)


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
