"""Claude Code backend adapter using the non-interactive Claude Code CLI."""

from __future__ import annotations

import json
import logging
import math
import os
import re
import secrets
import shlex
import shutil
import signal
import subprocess
import time
import uuid
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

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
    safe_path_component,
    session_prompts,
    start_declared_api_services,
    stdout_transcript_fallback,
    zero_usage,
)

logger = logging.getLogger(__name__)

DEFAULT_CLAUDECODE_EXECUTABLE = "claude"
DEFAULT_CLAUDECODE_PERMISSION_MODE = "dontAsk"
_VALID_PERMISSION_MODES = {
    "default",
    "acceptEdits",
    "plan",
    "auto",
    "dontAsk",
    "bypassPermissions",
}
_CLAUDECODE_ACTBENCH_MCP_TOOLS = (
    "mcp__actbench__actbench_list_files",
    "mcp__actbench__actbench_read_file",
    "mcp__actbench__actbench_write_file",
    "mcp__actbench__actbench_get_api_endpoints",
    "mcp__actbench__actbench_call_api",
)
_CLAUDECODE_DIRECT_WORKSPACE_TOOLS = (
    "Read",
    "Write",
    "Edit",
    "MultiEdit",
    "Bash",
    "Glob",
    "Grep",
    "LS",
)
_CLAUDECODE_PROVIDER_ENV_KEYS = (
    "ANTHROPIC_BASE_URL",
    "ANTHROPIC_MODEL",
    "ANTHROPIC_DEFAULT_OPUS_MODEL",
    "ANTHROPIC_DEFAULT_SONNET_MODEL",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL",
    "CLAUDE_CODE_SUBAGENT_MODEL",
    "CLAUDE_CODE_EFFORT_LEVEL",
)
_CLAUDECODE_AUTH_ENV_KEYS = (
    "ANTHROPIC_AUTH_TOKEN",
    "ANTHROPIC_API_KEY",
)
_CLAUDECODE_REDACT_ENV_KEYS = _CLAUDECODE_AUTH_ENV_KEYS + ("DEEPSEEK_API_KEY",)
_SENSITIVE_URL_PARAM_RE = re.compile(
    r"(?i)(api[_-]?key|auth|token|access[_-]?token|refresh[_-]?token|secret|password|credential)"
)
_CLAUDECODE_PERMISSION_PROMPT_PATTERNS = (
    re.compile(r"(?i)\bpermission prompt\b"),
    re.compile(r"(?i)\bneeds? your permission\b"),
    re.compile(r"(?i)\bpermission(?:s)?\s+(?:required|requested)\b"),
    re.compile(r"(?is)\b(?:do you want to|would you like to)\b.{0,160}\b(?:allow|approve)\b"),
    re.compile(r"(?is)\b(?:allow|approve|deny)\b.{0,120}\b(?:tool|permission|request)\b"),
)


@dataclass(frozen=True)
class ClaudeCodeConfig:
    executable: str
    model: str
    timeout_seconds: float | None
    claudecode_home: Path
    permission_mode: str
    allowed_tools: Tuple[str, ...]
    builtin_tools: str | None
    mcp_enabled: bool
    mcp_autostart: bool
    mcp_host: str
    mcp_port: int
    mcp_public_url: str
    mcp_admin_token: str | None

    @property
    def mcp_admin_url(self) -> str:
        return f"http://{self.mcp_host}:{self.mcp_port}/mcp"

    @property
    def config_dir(self) -> Path:
        return self.claudecode_home / "config"

    @property
    def data_dir(self) -> Path:
        return self.claudecode_home / "data"

    @property
    def state_dir(self) -> Path:
        return self.claudecode_home / "state"

    @property
    def cache_dir(self) -> Path:
        return self.claudecode_home / "cache"

    @property
    def home_dir(self) -> Path:
        return self.claudecode_home / "home"

    @property
    def mcp_config_dir(self) -> Path:
        return self.claudecode_home / "mcp"


class ClaudeCodeBackend:
    """ActBench backend that drives Claude Code through headless subprocesses."""

    name = "claudecode"
    uses_gateway_lock = False
    supports_parallel_runs = True

    def __init__(self) -> None:
        self._config: ClaudeCodeConfig | None = None
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
        logger.info("🤖 Claude Code backend [%s] starting task: %s", context.agent_id, task.task_id)
        start_time = time.time()
        artifact_session_id = f"{attempt_run_id}_{task.task_id}_{int(start_time * 1000)}"
        workspace = backend_task_workspace(
            context=context, attempt_run_id=attempt_run_id, task=task
        )
        api_group = None
        api_endpoints: Dict[str, Any] = {}
        api_audit: Dict[str, Any] = {}
        mcp_context_id: str | None = None
        stdout = ""
        stderr = ""
        exit_code = 0
        status = "success"
        timed_out = False
        transcript: List[Dict[str, Any]] = []
        transcript_source = "claudecode_stream_json"
        transcript_extraction: Dict[str, Any] | None = None
        usage = zero_usage(request_count=0)
        claudecode_session_id = str(uuid.uuid4())
        mcp_config_path: Path | None = None

        config = self._attempt_claudecode_config(
            config,
            context=context,
            attempt_run_id=attempt_run_id,
            task=task,
            workspace=workspace,
        )

        try:
            materialize_task_workspace(workspace=workspace, skill_dir=context.skill_dir, task=task)
        except Exception as exc:  # noqa: BLE001 - convert setup issues to execution result
            return _augment_claudecode_result(
                execution_error_result(
                    context=context,
                    task=task,
                    workspace=workspace,
                    stderr=f"claudecode workspace setup failed: {exc}",
                    execution_time=elapsed_since(start_time),
                ),
                context=context,
                config=config,
            )

        try:
            self._prepare_claudecode_home(config)
        except Exception as exc:  # noqa: BLE001 - convert setup issues to execution result
            return _augment_claudecode_result(
                execution_error_result(
                    context=context,
                    task=task,
                    workspace=workspace,
                    stderr=f"claudecode config setup failed: {exc}",
                    execution_time=elapsed_since(start_time),
                ),
                context=context,
                config=config,
                session_id=claudecode_session_id,
            )

        artifact_key, recorder = begin_task_artifacts(
            context=context,
            task=task,
            attempt_run_id=attempt_run_id,
            session_id=artifact_session_id,
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
                return _augment_claudecode_result(
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
                    session_id=claudecode_session_id,
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
                    mcp_config_path = _write_mcp_config(config, session_id=claudecode_session_id)
                    logger.info("   ActBench MCP context registered")
                except Exception as exc:  # noqa: BLE001
                    stderr = f"ActBench MCP context registration failed: {exc}"
                    return _augment_claudecode_result(
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
                        session_id=claudecode_session_id,
                        mcp_config_path=mcp_config_path,
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
            redactions = _redaction_values(config=config, mcp_context_id=mcp_context_id)
            if remaining <= 0:
                timed_out = True
                status = "timeout"
                exit_code = -1
                stderr = "claudecode execution timed out before starting subprocess"
            else:
                request_timeout = _subprocess_timeout(config=config, remaining=remaining)
                try:
                    completed = self._run_claudecode_subprocess(
                        config=config,
                        prompt=effective_prompt,
                        workspace=workspace,
                        session_id=claudecode_session_id,
                        mcp_config_path=mcp_config_path,
                        timeout_seconds=request_timeout,
                    )
                    stdout = _coerce_text(completed.stdout)
                    stderr = _coerce_text(completed.stderr)
                    exit_code = int(completed.returncode)
                    if exit_code != 0:
                        status = "error"
                    transcript, transcript_source, transcript_extraction, usage = (
                        _extract_claudecode_transcript(
                            effective_prompt=effective_prompt,
                            stdout=stdout,
                            redactions=redactions,
                        )
                    )
                    terminal_error = _terminal_error_from_metadata(transcript_extraction)
                    if terminal_error:
                        if status == "success":
                            status = "error"
                            exit_code = -1
                        stderr = _append_stderr(
                            stderr, f"claudecode terminal result error: {terminal_error}"
                        )
                except subprocess.TimeoutExpired as exc:
                    timed_out = True
                    status = "timeout"
                    exit_code = -1
                    stdout = _coerce_text(
                        getattr(exc, "stdout", None) or getattr(exc, "output", "")
                    )
                    stderr = _coerce_text(getattr(exc, "stderr", ""))
                    message = f"claudecode execution timed out after {request_timeout:.1f}s"
                    stderr = (stderr + "\n" if stderr else "") + message
                    transcript, transcript_source, transcript_extraction, usage = (
                        _extract_claudecode_transcript(
                            effective_prompt=effective_prompt,
                            stdout=stdout,
                            redactions=redactions,
                        )
                    )
                    terminal_error = _terminal_error_from_metadata(transcript_extraction)
                    if terminal_error:
                        stderr = _append_stderr(
                            stderr, f"claudecode terminal result error: {terminal_error}"
                        )
                except Exception as exc:  # noqa: BLE001 - surface unexpected backend failures
                    status = "error"
                    exit_code = -1
                    stderr = f"claudecode execution failed: {exc}"
                    logger.warning("   %s", stderr)

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
                    transcript_extraction["mcp_trace_error"] = _redact_text_values(
                        str(exc)[:500], redactions
                    )

            if transcript_extraction is None:
                transcript_extraction = {}
            permission_prompt_detected = _detect_claudecode_permission_prompt(
                stdout=stdout,
                stderr=stderr,
                transcript_extraction=transcript_extraction,
            )
            transcript_extraction["permission_prompt_detected"] = permission_prompt_detected
            if permission_prompt_detected:
                if status == "success":
                    status = "error"
                    exit_code = -1
                stderr = _append_stderr(
                    stderr,
                    "claudecode permission prompt detected; interactive approvals are unsupported",
                )

            transcript = _redact_transcript(transcript, redactions)
            if usage.get("request_count", 0) == 0 and status in {"success", "error", "timeout"}:
                usage["request_count"] = 1

            if not _has_usable_transcript(transcript) and status == "success":
                status = "error"
                exit_code = -1
                stderr = "claudecode execution produced no transcript"

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
                "stdout": _redact_text_values(stdout, redactions),
                "stderr": _redact_text_values(stderr, redactions),
                "api_audit": api_audit,
                "api_endpoints": _result_api_endpoints(config, api_endpoints),
                "training_artifact_key": artifact_key,
            }
            return _augment_claudecode_result(
                result,
                context=context,
                config=config,
                transcript_source=transcript_source,
                transcript_extraction=transcript_extraction,
                session_id=claudecode_session_id,
                mcp_config_path=mcp_config_path,
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

    def _load_config(self, context: BackendRunContext) -> ClaudeCodeConfig:
        executable = _resolve_executable(
            os.environ.get("ACTBENCH_CLAUDECODE_BIN", DEFAULT_CLAUDECODE_EXECUTABLE).strip()
            or DEFAULT_CLAUDECODE_EXECUTABLE
        )
        model = os.environ.get("ACTBENCH_CLAUDECODE_MODEL", "").strip() or context.model
        if not model.strip():
            raise BackendInitializationError("claudecode backend requires a non-empty model id")
        timeout_seconds = _load_timeout_seconds()
        home_root = os.environ.get("ACTBENCH_CLAUDECODE_HOME_ROOT", "").strip()
        if home_root:
            claudecode_home = Path(home_root).expanduser() / context.run_id / "claudecode_home"
        else:
            claudecode_home = context.agent_workspace / "claudecode_home"

        permission_mode = (
            os.environ.get("ACTBENCH_CLAUDECODE_PERMISSION_MODE", "").strip()
            or DEFAULT_CLAUDECODE_PERMISSION_MODE
        )
        if permission_mode not in _VALID_PERMISSION_MODES:
            expected = ", ".join(sorted(_VALID_PERMISSION_MODES))
            raise BackendInitializationError(
                f"ACTBENCH_CLAUDECODE_PERMISSION_MODE must be one of {expected}, got {permission_mode!r}"
            )

        mcp_enabled = _env_flag("ACTBENCH_CLAUDECODE_ENABLE_ACTBENCH_MCP", default=True)
        if mcp_enabled:
            mcp_autostart = _env_flag("ACTBENCH_MCP_AUTOSTART", default=True)
            mcp_host = (
                os.environ.get("ACTBENCH_MCP_HOST", DEFAULT_MCP_HOST).strip() or DEFAULT_MCP_HOST
            )
            mcp_port = _env_int("ACTBENCH_MCP_PORT", default=DEFAULT_MCP_PORT)
            default_mcp_url = f"http://{mcp_host}:{mcp_port}/mcp"
            mcp_public_url = os.environ.get("ACTBENCH_MCP_URL", default_mcp_url).strip()
            if not mcp_public_url:
                raise BackendInitializationError(
                    "ACTBENCH_MCP_URL must not be blank when MCP is enabled"
                )
            mcp_admin_token = os.environ.get("ACTBENCH_MCP_ADMIN_TOKEN", "").strip() or None
            if mcp_autostart and mcp_admin_token is None:
                mcp_admin_token = secrets.token_urlsafe(32)
        else:
            mcp_autostart = False
            mcp_host = DEFAULT_MCP_HOST
            mcp_port = DEFAULT_MCP_PORT
            mcp_public_url = f"http://{mcp_host}:{mcp_port}/mcp"
            mcp_admin_token = None

        allowed_tools = _load_allowed_tools(mcp_enabled=mcp_enabled)
        builtin_tools = _load_builtin_tools(mcp_enabled=mcp_enabled)

        return ClaudeCodeConfig(
            executable=executable,
            model=model,
            timeout_seconds=timeout_seconds,
            claudecode_home=claudecode_home,
            permission_mode=permission_mode,
            allowed_tools=allowed_tools,
            builtin_tools=builtin_tools,
            mcp_enabled=mcp_enabled,
            mcp_autostart=mcp_autostart,
            mcp_host=mcp_host,
            mcp_port=mcp_port,
            mcp_public_url=mcp_public_url,
            mcp_admin_token=mcp_admin_token,
        )

    def _attempt_claudecode_config(
        self,
        config: ClaudeCodeConfig,
        *,
        context: BackendRunContext,
        attempt_run_id: str,
        task: Task,
        workspace: Path,
    ) -> ClaudeCodeConfig:
        home_root = os.environ.get("ACTBENCH_CLAUDECODE_HOME_ROOT", "").strip()
        claudecode_home = backend_attempt_home(
            home_root=home_root,
            context=context,
            attempt_run_id=attempt_run_id,
            task=task,
            workspace=workspace,
            leaf_name="claudecode_home",
        )
        return replace(config, claudecode_home=claudecode_home)

    def _prepare_claudecode_home(self, config: ClaudeCodeConfig) -> None:
        try:
            for directory in (
                config.claudecode_home,
                config.config_dir,
                config.data_dir,
                config.state_dir,
                config.cache_dir,
                config.home_dir,
                config.mcp_config_dir,
            ):
                directory.mkdir(parents=True, exist_ok=True)
            # Keep an explicit, harmless marker in the isolated config root so tests and
            # operators can verify this run did not reuse ~/.claude.
            (config.claudecode_home / "actbench-claudecode.json").write_text(
                json.dumps(
                    {
                        "backend": "claudecode",
                        "model": config.model,
                        "claudecode_cli_model": config.model,
                        "provider_env": _claudecode_provider_env_metadata(),
                        "permission_mode": config.permission_mode,
                        "allowed_tools": list(config.allowed_tools),
                        "builtin_tools": config.builtin_tools,
                        "mcp_enabled": config.mcp_enabled,
                    },
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
        except OSError as exc:
            raise BackendInitializationError(
                f"claudecode backend could not write isolated config in {config.claudecode_home}: {exc}"
            ) from exc

    def _initialize_mcp_gateway(self, config: ClaudeCodeConfig) -> None:
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
                "claudecode backend could not start or authenticate to the ActBench MCP gateway at "
                f"{config.mcp_admin_url}: {exc}. If another gateway is already running, set "
                "ACTBENCH_MCP_ADMIN_TOKEN to its token, choose a different ACTBENCH_MCP_PORT, "
                "or restart the gateway. Set ACTBENCH_CLAUDECODE_ENABLE_ACTBENCH_MCP=0 for "
                "weak direct-workspace mode."
            ) from exc
        logger.info("   ActBench MCP gateway ready for Claude Code at %s", config.mcp_public_url)

    def _run_claudecode_subprocess(
        self,
        *,
        config: ClaudeCodeConfig,
        prompt: str,
        workspace: Path,
        session_id: str,
        mcp_config_path: Path | None,
        timeout_seconds: float,
    ) -> subprocess.CompletedProcess[str]:
        cmd = [
            config.executable,
            "--bare",
            "-p",
            "--input-format",
            "text",
            "--output-format",
            "stream-json",
            "--verbose",
            "--permission-mode",
            config.permission_mode,
            "--session-id",
            session_id,
            "--model",
            config.model,
        ]
        if config.builtin_tools is not None:
            cmd.extend(["--tools", config.builtin_tools])
        if config.allowed_tools:
            cmd.extend(["--allowedTools", ",".join(config.allowed_tools)])
        if mcp_config_path is not None:
            cmd.extend(["--mcp-config", str(mcp_config_path), "--strict-mcp-config"])
        return _run_subprocess_with_process_group(
            cmd,
            input_text=prompt,
            cwd=workspace,
            env=_claudecode_env(config),
            timeout_seconds=timeout_seconds,
        )


def _run_subprocess_with_process_group(
    cmd: List[str],
    *,
    input_text: str,
    cwd: Path,
    env: Dict[str, str],
    timeout_seconds: float,
) -> subprocess.CompletedProcess[str]:
    process = subprocess.Popen(
        cmd,
        cwd=str(cwd),
        env=env,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        stdout, stderr = process.communicate(input=input_text, timeout=timeout_seconds)
    except subprocess.TimeoutExpired as exc:
        stdout = _coerce_text(getattr(exc, "stdout", None) or getattr(exc, "output", ""))
        stderr = _coerce_text(getattr(exc, "stderr", ""))
        _terminate_process_group(process, signal.SIGTERM)
        try:
            terminated_stdout, terminated_stderr = process.communicate(timeout=2.0)
        except subprocess.TimeoutExpired:
            _terminate_process_group(process, signal.SIGKILL)
            try:
                terminated_stdout, terminated_stderr = process.communicate(timeout=2.0)
            except subprocess.TimeoutExpired:
                terminated_stdout, terminated_stderr = stdout, stderr
        stdout = _coerce_text(terminated_stdout) or stdout
        stderr = _coerce_text(terminated_stderr) or stderr
        raise subprocess.TimeoutExpired(
            cmd=cmd,
            timeout=timeout_seconds,
            output=stdout,
            stderr=stderr,
        ) from exc
    return subprocess.CompletedProcess(
        args=cmd, returncode=process.returncode, stdout=stdout, stderr=stderr
    )


def _terminate_process_group(process: subprocess.Popen[str], sig: signal.Signals) -> None:
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, sig)
    except ProcessLookupError:
        return
    except OSError:
        if sig == signal.SIGTERM:
            process.terminate()
        else:
            process.kill()


def _claudecode_env(config: ClaudeCodeConfig) -> Dict[str, str]:
    env = os.environ.copy()
    if not str(env.get("ANTHROPIC_AUTH_TOKEN") or "").strip():
        deepseek_api_key = str(env.get("DEEPSEEK_API_KEY") or "").strip()
        if deepseek_api_key:
            env["ANTHROPIC_AUTH_TOKEN"] = deepseek_api_key
    env["HOME"] = str(config.home_dir)
    env["XDG_CONFIG_HOME"] = str(config.config_dir)
    env["XDG_DATA_HOME"] = str(config.data_dir)
    env["XDG_STATE_HOME"] = str(config.state_dir)
    env["XDG_CACHE_HOME"] = str(config.cache_dir)
    env["CLAUDE_CONFIG_DIR"] = str(config.config_dir)
    env.setdefault("NO_COLOR", "1")
    env.setdefault("CI", "1")
    env.setdefault("TERM", "dumb")
    env.pop("ACTBENCH_MCP_ADMIN_TOKEN", None)
    return env


def _write_mcp_config(config: ClaudeCodeConfig, *, session_id: str) -> Path:
    path = config.mcp_config_dir / f"{safe_path_component(session_id)}.mcp.json"
    payload = {
        "mcpServers": {
            "actbench": {
                "type": "http",
                "url": config.mcp_public_url,
            }
        }
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _augment_claudecode_result(
    result: Dict[str, Any],
    *,
    context: BackendRunContext,
    config: ClaudeCodeConfig,
    transcript_source: str = "claudecode_stream_json",
    transcript_extraction: Dict[str, Any] | None = None,
    session_id: str | None = None,
    mcp_config_path: Path | None = None,
) -> Dict[str, Any]:
    extraction = transcript_extraction or {}
    return augment_execution_result(
        result,
        context=context,
        transcript_source=transcript_source,
        transcript_extraction=transcript_extraction,
        executable=config.executable,
        claudecode_cli_model=config.model,
        claudecode_cli_model_matches_result_label=config.model == context.model,
        provider_env=_claudecode_provider_env_metadata(),
        permission_mode=config.permission_mode,
        permission_prompt_detected=extraction.get("permission_prompt_detected"),
        allowed_tools=list(config.allowed_tools),
        builtin_tools=config.builtin_tools,
        claudecode_session_id=session_id,
        claudecode_home=str(config.claudecode_home),
        claudecode_config_dir=str(config.config_dir),
        mcp_config_path=str(mcp_config_path) if mcp_config_path else None,
        mcp_enabled=config.mcp_enabled,
        mcp_public_url=config.mcp_public_url if config.mcp_enabled else None,
    )


def _claudecode_provider_env_metadata(env: Dict[str, str] | None = None) -> Dict[str, Any]:
    source = os.environ if env is None else env
    metadata: Dict[str, Any] = {}
    for key in _CLAUDECODE_PROVIDER_ENV_KEYS:
        value = source.get(key)
        if value is None or not str(value).strip():
            continue
        metadata[key.lower()] = _sanitize_provider_env_value(key, value)

    auth_present = {
        key.lower(): bool(str(source.get(key) or "").strip()) for key in _CLAUDECODE_AUTH_ENV_KEYS
    }
    deepseek_key_present = bool(str(source.get("DEEPSEEK_API_KEY") or "").strip())
    anthropic_auth_token_present = bool(str(source.get("ANTHROPIC_AUTH_TOKEN") or "").strip())
    anthropic_api_key_present = bool(str(source.get("ANTHROPIC_API_KEY") or "").strip())
    metadata["auth_env_present"] = auth_present
    metadata["deepseek_api_key_present"] = deepseek_key_present
    metadata["effective_auth_present"] = (
        anthropic_auth_token_present or anthropic_api_key_present or deepseek_key_present
    )
    metadata["effective_anthropic_auth_token_present"] = (
        anthropic_auth_token_present or deepseek_key_present
    )
    metadata["auth_token_source"] = _claudecode_auth_token_source(source)
    metadata["deepseek_api_key_mapped_to_anthropic_auth_token"] = (
        deepseek_key_present and not anthropic_auth_token_present
    )
    metadata["auth_mapping"] = "deepseek_api_key_to_anthropic_auth_token" if (
        deepseek_key_present and not anthropic_auth_token_present
    ) else None
    metadata = {key: value for key, value in metadata.items() if value is not None}
    return metadata


def _claudecode_auth_token_source(env: Dict[str, str]) -> str | None:
    if str(env.get("ANTHROPIC_AUTH_TOKEN") or "").strip():
        return "ANTHROPIC_AUTH_TOKEN"
    if str(env.get("DEEPSEEK_API_KEY") or "").strip():
        return "DEEPSEEK_API_KEY"
    if str(env.get("ANTHROPIC_API_KEY") or "").strip():
        return "ANTHROPIC_API_KEY"
    return None


def _sanitize_provider_env_value(key: str, value: str) -> str:
    text = str(value).strip()
    if "URL" in key:
        return _sanitize_provider_env_url(text)
    return text


def _sanitize_provider_env_url(url: str) -> str:
    try:
        parts = urlsplit(url)
    except ValueError:
        return url
    if not parts.scheme and not parts.netloc:
        return url

    netloc = parts.netloc
    if "@" in netloc:
        _userinfo, host = netloc.rsplit("@", 1)
        netloc = f"[redacted]@{host}"

    query_pairs = parse_qsl(parts.query, keep_blank_values=True)
    if query_pairs:
        query = urlencode(
            [
                (name, "[redacted]" if _SENSITIVE_URL_PARAM_RE.search(name) else value)
                for name, value in query_pairs
            ]
        )
    else:
        query = parts.query
    return urlunsplit((parts.scheme, netloc, parts.path, query, parts.fragment))


def _detect_claudecode_permission_prompt(
    *,
    stdout: str,
    stderr: str,
    transcript_extraction: Dict[str, Any] | None = None,
) -> bool:
    if isinstance(transcript_extraction, dict) and transcript_extraction.get(
        "permission_prompt_detected"
    ) is True:
        return True
    text = "\n".join(part for part in (stdout[-8000:], stderr[-8000:]) if part)
    if not text:
        return False
    return any(pattern.search(text) for pattern in _CLAUDECODE_PERMISSION_PROMPT_PATTERNS)


def _result_api_endpoints(
    config: ClaudeCodeConfig, api_endpoints: Dict[str, Any]
) -> Dict[str, Any]:
    if not config.mcp_enabled:
        return api_endpoints
    return sanitize_api_endpoints(api_endpoints)


def _load_allowed_tools(*, mcp_enabled: bool) -> Tuple[str, ...]:
    raw = os.environ.get("ACTBENCH_CLAUDECODE_ALLOWED_TOOLS")
    if raw is not None:
        return tuple(_split_tool_list(raw))
    if mcp_enabled:
        return _CLAUDECODE_ACTBENCH_MCP_TOOLS
    return _CLAUDECODE_DIRECT_WORKSPACE_TOOLS


def _load_builtin_tools(*, mcp_enabled: bool) -> str | None:
    raw = os.environ.get("ACTBENCH_CLAUDECODE_TOOLS")
    if raw is None:
        return "" if mcp_enabled else None
    stripped = raw.strip()
    if not stripped:
        return "" if mcp_enabled else None
    if stripped.lower() in {"none", "disabled", "disable"}:
        return ""
    return stripped


def _split_tool_list(raw: str) -> List[str]:
    stripped = raw.strip()
    if not stripped or stripped.lower() in {"none", "disabled", "disable"}:
        return []
    if "," in stripped:
        return [item.strip() for item in stripped.split(",") if item.strip()]
    return [item.strip() for item in shlex.split(stripped) if item.strip()]


def _extract_claudecode_transcript(
    *,
    effective_prompt: str,
    stdout: str,
    redactions: Iterable[str | None] = (),
) -> Tuple[List[Dict[str, Any]], str, Dict[str, Any], Dict[str, Any]]:
    redaction_values = [str(item) for item in redactions if item]
    events, metadata = _parse_claudecode_stream(stdout)
    terminal_error = _claudecode_terminal_error(events)
    if terminal_error:
        metadata["terminal_error"] = _redact_text_values(terminal_error[:1000], redaction_values)
    transcript = _normalize_claudecode_stream_to_transcript(
        effective_prompt=effective_prompt,
        events=events,
    )
    source = "claudecode_stream_json"
    if not _has_usable_transcript(transcript):
        metadata["fallback_reason"] = "unusable_stream_transcript"
        if not events:
            fallback = stdout_transcript_fallback(effective_prompt, stdout)
            if fallback:
                transcript = fallback
                source = "claudecode_stream_json_fallback_stdout_raw"
    transcript = _redact_transcript(transcript, redaction_values)
    usage = _usage_from_claudecode_stream(events)
    metadata["transcript_messages"] = len(transcript)
    return transcript, source, metadata, usage


def _parse_claudecode_stream(stdout: str) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    event_counts: Dict[str, int] = {}
    parse_errors: List[str] = []
    non_json_lines = 0
    for line_number, line in enumerate(stdout.splitlines(), 1):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            event = json.loads(stripped)
        except json.JSONDecodeError as exc:
            non_json_lines += 1
            if len(parse_errors) < 5:
                parse_errors.append(f"line {line_number}: {exc.msg}")
            continue
        if not isinstance(event, dict):
            non_json_lines += 1
            continue
        events.append(event)
        event_type = str(event.get("type") or "unknown")
        event_counts[event_type] = event_counts.get(event_type, 0) + 1
    metadata: Dict[str, Any] = {
        "method": "stream_json",
        "events_total": len(events),
        "event_counts": event_counts,
        "non_json_lines": non_json_lines,
    }
    if parse_errors:
        metadata["parse_errors"] = parse_errors
    return events, metadata


def _claudecode_terminal_error(events: List[Dict[str, Any]]) -> str | None:
    for event in events:
        if not isinstance(event, dict):
            continue
        event_type = str(event.get("type") or "")
        if event_type == "error":
            error_text = _content_to_text(event.get("error") or event.get("message") or event)
            return error_text.strip() or "error event"
        if event_type != "result":
            continue
        subtype = str(event.get("subtype") or "")
        if not (_coerce_bool(event.get("is_error")) or subtype.startswith("error_")):
            continue
        details = []
        if subtype:
            details.append(subtype)
        for key in ("error", "errors", "message", "result"):
            text = _content_to_text(event.get(key))
            if text.strip():
                details.append(text.strip())
        return ": ".join(details) if details else "result error"
    return None


def _terminal_error_from_metadata(metadata: Dict[str, Any] | None) -> str | None:
    if not isinstance(metadata, dict):
        return None
    raw = metadata.get("terminal_error")
    if raw is None:
        return None
    text = str(raw).strip()
    return text or None


def _append_stderr(stderr: str, message: str) -> str:
    return (stderr + "\n" if stderr else "") + message


def _normalize_claudecode_stream_to_transcript(
    *,
    effective_prompt: str,
    events: List[Dict[str, Any]] | None = None,
    stdout: str | None = None,
) -> List[Dict[str, Any]]:
    if events is None:
        events, _ = _parse_claudecode_stream(stdout or "")
    transcript: List[Dict[str, Any]] = [
        {"type": "message", "message": {"role": "user", "content": [effective_prompt]}}
    ]
    tool_names_by_id: Dict[str, str] = {}
    saw_assistant_text_or_tool = False

    for event in events:
        event_type = str(event.get("type") or "")
        if event_type == "assistant":
            message = event.get("message") if isinstance(event.get("message"), dict) else event
            entries, tool_names = _normalize_claudecode_assistant_message(message)
            for call_id, name in tool_names.items():
                tool_names_by_id[call_id] = name
            if entries:
                saw_assistant_text_or_tool = True
                transcript.extend(entries)
        elif event_type == "user":
            message = event.get("message") if isinstance(event.get("message"), dict) else event
            transcript.extend(
                _normalize_claudecode_user_message(
                    message,
                    tool_names_by_id=tool_names_by_id,
                    effective_prompt=effective_prompt,
                )
            )
        elif event_type == "result":
            if not saw_assistant_text_or_tool:
                result_text = _content_to_text(event.get("result"))
                if result_text.strip():
                    transcript.append(
                        {
                            "type": "message",
                            "message": {
                                "role": "assistant",
                                "content": [{"type": "text", "text": result_text}],
                            },
                        }
                    )
                    saw_assistant_text_or_tool = True
        elif event_type == "error":
            error_text = _content_to_text(event.get("error") or event.get("message"))
            if error_text.strip():
                transcript.append(
                    {
                        "type": "message",
                        "message": {
                            "role": "assistant",
                            "content": [
                                {"type": "text", "text": f"claudecode error: {error_text}"}
                            ],
                        },
                    }
                )
    return transcript


def _normalize_claudecode_assistant_message(
    message: Dict[str, Any],
) -> Tuple[List[Dict[str, Any]], Dict[str, str]]:
    raw_content_value = message.get("content")
    if isinstance(raw_content_value, str):
        raw_content: List[Any] = [{"type": "text", "text": raw_content_value}]
    else:
        raw_content = raw_content_value if isinstance(raw_content_value, list) else []
    assistant_blocks: List[Dict[str, Any]] = []
    followup_entries: List[Dict[str, Any]] = []
    tool_names_by_id: Dict[str, str] = {}
    for block in raw_content:
        if isinstance(block, str):
            if block.strip():
                assistant_blocks.append({"type": "text", "text": block})
            continue
        if not isinstance(block, dict):
            continue
        block_type = str(block.get("type") or "")
        if block_type == "text":
            text = _content_to_text(block.get("text"))
            if text.strip():
                assistant_blocks.append({"type": "text", "text": text})
        elif block_type in {"tool_use", "server_tool_use"}:
            call_block = _normalize_claudecode_tool_use_block(block)
            if call_block is not None:
                assistant_blocks.append(call_block)
                tool_names_by_id[str(call_block["id"])] = str(call_block["name"])
        elif block_type == "tool_result":
            result_block = _normalize_claudecode_tool_result_block(
                block, tool_names_by_id=tool_names_by_id
            )
            if result_block is not None:
                followup_entries.append(
                    {
                        "type": "message",
                        "message": {"role": "toolResult", "content": [result_block]},
                    }
                )
        elif block_type in {"thinking", "redacted_thinking", "reasoning"}:
            # Do not persist raw reasoning/thinking. ActBench scoring only needs evidence of
            # actions, observations, and final text.
            continue
    entries: List[Dict[str, Any]] = []
    if assistant_blocks:
        entries.append(
            {"type": "message", "message": {"role": "assistant", "content": assistant_blocks}}
        )
    entries.extend(followup_entries)
    return entries, tool_names_by_id


def _normalize_claudecode_user_message(
    message: Dict[str, Any],
    *,
    tool_names_by_id: Dict[str, str],
    effective_prompt: str,
) -> List[Dict[str, Any]]:
    raw_content = message.get("content")
    if isinstance(raw_content, str):
        if raw_content.strip() and raw_content.strip() != effective_prompt.strip():
            return [{"type": "message", "message": {"role": "user", "content": [raw_content]}}]
        return []
    if not isinstance(raw_content, list):
        return []

    user_content: List[Any] = []
    tool_results: List[Dict[str, Any]] = []
    for block in raw_content:
        if isinstance(block, str):
            if block.strip() and block.strip() != effective_prompt.strip():
                user_content.append(block)
            continue
        if not isinstance(block, dict):
            continue
        block_type = str(block.get("type") or "")
        if block_type == "tool_result":
            result_block = _normalize_claudecode_tool_result_block(
                block, tool_names_by_id=tool_names_by_id
            )
            if result_block is not None:
                tool_results.append(result_block)
        elif block_type == "text":
            text = _content_to_text(block.get("text"))
            if text.strip() and text.strip() != effective_prompt.strip():
                user_content.append(text)
    entries: List[Dict[str, Any]] = []
    if user_content:
        entries.append({"type": "message", "message": {"role": "user", "content": user_content}})
    for result_block in tool_results:
        entries.append(
            {"type": "message", "message": {"role": "toolResult", "content": [result_block]}}
        )
    return entries


def _normalize_claudecode_tool_use_block(block: Dict[str, Any]) -> Dict[str, Any] | None:
    name = block.get("name") or block.get("tool")
    if not isinstance(name, str) or not name.strip():
        return None
    call_id = str(block.get("id") or block.get("tool_use_id") or name)
    raw_arguments = block.get("input")
    if raw_arguments is None:
        raw_arguments = block.get("arguments")
    return {
        "type": "toolCall",
        "name": name.strip(),
        "arguments": _redact_mcp_trace_value(_coerce_tool_arguments(raw_arguments)),
        "id": call_id,
    }


def _normalize_claudecode_tool_result_block(
    block: Dict[str, Any],
    *,
    tool_names_by_id: Dict[str, str],
) -> Dict[str, Any] | None:
    call_id = block.get("tool_use_id") or block.get("id") or block.get("tool_call_id")
    if call_id is None:
        return None
    call_id = str(call_id)
    name = block.get("name")
    if not isinstance(name, str) or not name.strip():
        name = tool_names_by_id.get(call_id, "")
    raw_is_error = block.get("is_error") if "is_error" in block else block.get("isError")
    result: Dict[str, Any] = {
        "type": "toolResult",
        "text": _content_to_text(block.get("content") if "content" in block else block.get("text")),
        "tool_call_id": call_id,
        "name": name,
        "isError": _coerce_bool(raw_is_error),
    }
    return result


def _usage_from_claudecode_stream(events: List[Dict[str, Any]] | str) -> Dict[str, Any]:
    if isinstance(events, str):
        events, _ = _parse_claudecode_stream(events)
    usage = zero_usage(request_count=0)
    result_usage_seen = False
    assistant_messages = 0
    assistant_messages_with_usage = 0

    for event in events:
        if not isinstance(event, dict):
            continue
        event_type = str(event.get("type") or "")
        if event_type == "result":
            raw_usage = event.get("usage") if isinstance(event.get("usage"), dict) else {}
            if raw_usage:
                result_usage_seen = True
                usage = zero_usage(request_count=_safe_int(event.get("num_turns", 0)))
                _add_anthropic_usage(usage, raw_usage)
            cost = event.get("total_cost_usd", event.get("cost_usd", event.get("cost")))
            if cost is not None:
                usage["cost_usd"] = _safe_float(cost)
            if usage.get("request_count", 0) == 0 and event.get("num_turns") is not None:
                usage["request_count"] = _safe_int(event.get("num_turns"))
        elif event_type == "assistant" and not result_usage_seen:
            assistant_messages += 1
            message = event.get("message") if isinstance(event.get("message"), dict) else event
            raw_usage = message.get("usage") if isinstance(message.get("usage"), dict) else {}
            if raw_usage:
                assistant_messages_with_usage += 1
                _add_anthropic_usage(usage, raw_usage)
    if usage.get("request_count", 0) == 0:
        usage["request_count"] = assistant_messages_with_usage or assistant_messages
    return usage


def _add_anthropic_usage(usage: Dict[str, Any], raw_usage: Dict[str, Any]) -> None:
    input_tokens = _safe_int(raw_usage.get("input_tokens", raw_usage.get("prompt_tokens", 0)))
    output_tokens = _safe_int(raw_usage.get("output_tokens", raw_usage.get("completion_tokens", 0)))
    cache_read = _safe_int(
        raw_usage.get("cache_read_input_tokens", raw_usage.get("cache_read_tokens", 0))
    )
    cache_write = _safe_int(
        raw_usage.get(
            "cache_creation_input_tokens",
            raw_usage.get("cache_write_input_tokens", raw_usage.get("cache_write_tokens", 0)),
        )
    )
    usage["input_tokens"] += input_tokens
    usage["output_tokens"] += output_tokens
    usage["cache_read_tokens"] += cache_read
    usage["cache_write_tokens"] += cache_write
    total_tokens = raw_usage.get("total_tokens")
    if total_tokens is not None:
        usage["total_tokens"] += _safe_int(total_tokens)
    else:
        usage["total_tokens"] += input_tokens + output_tokens


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
        sequence = trace.get("sequence", index)
        if sequence is None:
            sequence = index
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


def _has_actbench_tool_result(transcript: List[Dict[str, Any]]) -> bool:
    return bool(_actbench_tool_result_counts(transcript))


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
        return name.rsplit("__actbench__", 1)[1]
    return name


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
        "ActBench has exposed task-scoped tools through the Claude Code MCP server "
        f"named `actbench` at {mcp_public_url}. For this task, always pass "
        f"context_id `{context_id}` exactly when calling ActBench MCP tools. Use "
        "actbench_list_files, actbench_read_file, and actbench_write_file to inspect or "
        "modify the task workspace. Use actbench_get_api_endpoints to discover declared "
        "mock API services, then call them only through actbench_call_api. Claude Code may "
        "display these tools with MCP prefixes such as mcp__actbench__actbench_read_file; "
        "use the prefixed tool names it exposes. Do not assume fixed localhost ports and "
        "do not call mock APIs directly."
    )


def _subprocess_timeout(*, config: ClaudeCodeConfig, remaining: float) -> float:
    if config.timeout_seconds is None:
        return max(remaining, 0.001)
    return max(min(config.timeout_seconds, remaining), 0.001)


def _load_timeout_seconds() -> float | None:
    timeout_raw = os.environ.get("ACTBENCH_CLAUDECODE_TIMEOUT_SECONDS")
    if timeout_raw is None or not timeout_raw.strip():
        return None
    try:
        timeout_seconds = float(timeout_raw)
    except ValueError as exc:
        raise BackendInitializationError(
            f"ACTBENCH_CLAUDECODE_TIMEOUT_SECONDS must be numeric, got {timeout_raw!r}"
        ) from exc
    if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
        raise BackendInitializationError(
            "ACTBENCH_CLAUDECODE_TIMEOUT_SECONDS must be a finite positive number"
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
    raw = executable.strip() or DEFAULT_CLAUDECODE_EXECUTABLE
    expanded = Path(raw).expanduser()
    if expanded.name != raw or os.sep in raw:
        if not expanded.is_file():
            raise BackendInitializationError(f"claudecode executable not found: {expanded}")
        return str(expanded)
    resolved = shutil.which(raw)
    if not resolved:
        raise BackendInitializationError(
            f"claudecode backend requires the `{raw}` executable on PATH. "
            "Set ACTBENCH_CLAUDECODE_BIN to the Claude Code CLI path."
        )
    return resolved


def _coerce_tool_arguments(value: Any) -> Dict[str, Any]:
    if value is None or value == "":
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {"raw": value}
        if isinstance(parsed, dict):
            return parsed
        return {"raw": parsed}
    return {"raw": value}


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
        return "\n".join(part for part in parts if part)
    if isinstance(content, dict):
        text = content.get("text") or content.get("content") or content.get("message")
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


def _redact_transcript(
    transcript: List[Dict[str, Any]], redactions: Iterable[str | None]
) -> List[Dict[str, Any]]:
    return _redact_value(transcript, redactions)


def _redact_value(value: Any, redactions: Iterable[str | None]) -> Any:
    redaction_values = [str(item) for item in redactions if item]
    if isinstance(value, str):
        return _redact_text_values(value, redaction_values)
    if isinstance(value, list):
        return [_redact_value(item, redaction_values) for item in value]
    if isinstance(value, dict):
        redacted: Dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if _is_sensitive_mcp_trace_key(key_text):
                redacted[key_text] = "[redacted]"
            else:
                redacted[key_text] = _redact_value(item, redaction_values)
        return redacted
    return value


def _redact_text_values(text: str, redactions: Iterable[str | None]) -> str:
    redacted = text
    for value in redactions:
        if value:
            redacted = redacted.replace(str(value), "[redacted]")
    # Best-effort redaction for credential-shaped text emitted in stderr/stdout.
    redacted = re.sub(
        r"(?i)([\"']?authorization[\"']?\s*[:=]\s*[\"']?)(bearer\s+)?([^\"'\s,;\]}]+)",
        lambda match: f"{match.group(1)}{match.group(2) or ''}[redacted]",
        redacted,
    )
    redacted = re.sub(
        r"(?i)((?:admin[_-]?token|api[_-]?key|access[_-]?token|refresh[_-]?token|password|secret|credential|cookie)\s*[\"']?\s*[:=]\s*[\"']?)([^\"'\s,;\]}]+)",
        lambda match: f"{match.group(1)}[redacted]",
        redacted,
    )
    return redacted


def _redaction_values(*, config: ClaudeCodeConfig, mcp_context_id: str | None) -> List[str]:
    values: List[str] = []
    if mcp_context_id:
        values.append(mcp_context_id)
    if config.mcp_admin_token:
        values.append(config.mcp_admin_token)
    for key in _CLAUDECODE_REDACT_ENV_KEYS:
        value = os.environ.get(key)
        if value:
            values.append(value)
    return values


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "y", "on"}:
            return True
        if normalized in {"0", "false", "no", "n", "off", ""}:
            return False
    if isinstance(value, (int, float)):
        return bool(value)
    return False


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
