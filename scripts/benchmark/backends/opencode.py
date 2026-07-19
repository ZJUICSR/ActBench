"""opencode backend adapter using the non-interactive opencode CLI."""

from __future__ import annotations

import json
import logging
import math
import os
import secrets
import shutil
import signal
import subprocess
import tempfile
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

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

DEFAULT_OPENCODE_EXECUTABLE = "opencode"


@dataclass(frozen=True)
class OpenCodeConfig:
    executable: str
    model: str
    agent: str | None
    timeout_seconds: float | None
    opencode_home: Path
    auto_approve: bool
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
        return self.opencode_home / "config"

    @property
    def data_dir(self) -> Path:
        return self.opencode_home / "data"

    @property
    def state_dir(self) -> Path:
        return self.opencode_home / "state"

    @property
    def cache_dir(self) -> Path:
        return self.opencode_home / "cache"

    @property
    def home_dir(self) -> Path:
        return self.opencode_home / "home"

    @property
    def db_path(self) -> Path:
        return self.opencode_home / "opencode.sqlite"


class OpenCodeBackend:
    """ActBench backend that drives opencode through ``opencode run`` subprocesses."""

    name = "opencode"
    uses_gateway_lock = False
    supports_parallel_runs = True

    def __init__(self) -> None:
        self._config: OpenCodeConfig | None = None
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
        logger.info("🤖 opencode backend [%s] starting task: %s", context.agent_id, task.task_id)
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
        transcript_source = "opencode_run_stdout_raw"
        transcript_extraction: Dict[str, Any] | None = None
        usage = zero_usage(request_count=0)
        run_session_id: str | None = None

        config = self._attempt_opencode_config(
            config,
            context=context,
            attempt_run_id=attempt_run_id,
            task=task,
            workspace=workspace,
        )

        try:
            materialize_task_workspace(workspace=workspace, skill_dir=context.skill_dir, task=task)
        except Exception as exc:  # noqa: BLE001 - convert setup issues to execution result
            return _augment_opencode_result(
                execution_error_result(
                    context=context,
                    task=task,
                    workspace=workspace,
                    stderr=f"opencode workspace setup failed: {exc}",
                    execution_time=elapsed_since(start_time),
                ),
                context=context,
                config=config,
            )

        try:
            self._prepare_opencode_home(config)
        except Exception as exc:  # noqa: BLE001 - convert setup issues to execution result
            return _augment_opencode_result(
                execution_error_result(
                    context=context,
                    task=task,
                    workspace=workspace,
                    stderr=f"opencode config setup failed: {exc}",
                    execution_time=elapsed_since(start_time),
                ),
                context=context,
                config=config,
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
                return _augment_opencode_result(
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
                    return _augment_opencode_result(
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
                stderr = "opencode execution timed out before starting subprocess"
            else:
                request_timeout = _subprocess_timeout(config=config, remaining=remaining)
                try:
                    completed = self._run_opencode_subprocess(
                        config=config,
                        prompt=effective_prompt,
                        workspace=workspace,
                        timeout_seconds=request_timeout,
                    )
                    stdout = _coerce_text(completed.stdout)
                    stderr = _coerce_text(completed.stderr)
                    exit_code = int(completed.returncode)
                    run_session_id = _extract_session_id_from_run_stdout(stdout)
                    if exit_code != 0:
                        status = "error"
                    transcript, transcript_source, transcript_extraction, usage = (
                        self._extract_opencode_transcript(
                            config=config,
                            workspace=workspace,
                            effective_prompt=effective_prompt,
                            stdout=stdout,
                            session_id=run_session_id,
                            redactions=[mcp_context_id] if mcp_context_id else [],
                            timeout_seconds=_transcript_export_timeout(
                                timeout_budget - (time.time() - start_time)
                            ),
                        )
                    )
                except subprocess.TimeoutExpired as exc:
                    timed_out = True
                    status = "timeout"
                    exit_code = -1
                    stdout = _coerce_text(
                        getattr(exc, "stdout", None) or getattr(exc, "output", "")
                    )
                    stderr = _coerce_text(getattr(exc, "stderr", ""))
                    run_session_id = _extract_session_id_from_run_stdout(stdout)
                    message = f"opencode execution timed out after {request_timeout:.1f}s"
                    stderr = (stderr + "\n" if stderr else "") + message
                    transcript, transcript_source, transcript_extraction, usage = (
                        self._extract_opencode_transcript(
                            config=config,
                            workspace=workspace,
                            effective_prompt=effective_prompt,
                            stdout=stdout,
                            session_id=run_session_id,
                            redactions=[mcp_context_id] if mcp_context_id else [],
                            timeout_seconds=_transcript_export_timeout(
                                timeout_budget - (time.time() - start_time)
                            ),
                        )
                    )
                except Exception as exc:  # noqa: BLE001 - surface unexpected backend failures
                    status = "error"
                    exit_code = -1
                    stderr = f"opencode execution failed: {exc}"
                    logger.warning("   %s", stderr)

            if config.mcp_enabled and mcp_context_id:
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
                        if transcript_extraction is None:
                            transcript_extraction = {}
                        transcript_extraction["mcp_trace_messages_available"] = len(
                            trace_transcript
                        )
                    if missing_trace_transcript:
                        transcript.extend(missing_trace_transcript)
                        if transcript_extraction is None:
                            transcript_extraction = {}
                        transcript_extraction["mcp_trace_messages_appended"] = len(
                            missing_trace_transcript
                        )
                except Exception as exc:  # noqa: BLE001 - tracing must not fail the task
                    logger.warning("   Failed to retrieve ActBench MCP traces: %s", exc)

            transcript = _redact_transcript(transcript, [mcp_context_id] if mcp_context_id else [])
            if usage.get("request_count", 0) == 0 and status in {"success", "error", "timeout"}:
                usage["request_count"] = 1

            if not _has_usable_transcript(transcript) and status == "success":
                status = "error"
                exit_code = -1
                stderr = "opencode execution produced no transcript"

            if api_group:
                api_audit = api_group.collect_audit()

            redactions = [mcp_context_id] if mcp_context_id else []
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
            return _augment_opencode_result(
                result,
                context=context,
                config=config,
                transcript_source=transcript_source,
                transcript_extraction=transcript_extraction,
                session_id=run_session_id,
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

    def _load_config(self, context: BackendRunContext) -> OpenCodeConfig:
        executable = _resolve_executable(
            os.environ.get("ACTBENCH_OPENCODE_BIN", DEFAULT_OPENCODE_EXECUTABLE).strip()
            or DEFAULT_OPENCODE_EXECUTABLE
        )
        model = os.environ.get("ACTBENCH_OPENCODE_MODEL", "").strip() or context.model
        if not model.strip():
            raise BackendInitializationError("opencode backend requires a non-empty model id")
        agent = os.environ.get("ACTBENCH_OPENCODE_AGENT", "").strip() or None
        timeout_seconds = _load_timeout_seconds()
        home_root = os.environ.get("ACTBENCH_OPENCODE_HOME_ROOT", "").strip()
        if home_root:
            opencode_home = Path(home_root).expanduser() / context.run_id / "opencode_home"
        else:
            opencode_home = context.agent_workspace / "opencode_home"

        auto_approve = _env_flag("ACTBENCH_OPENCODE_AUTO", default=True)
        mcp_enabled = _env_flag("ACTBENCH_OPENCODE_ENABLE_ACTBENCH_MCP", default=True)
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

        return OpenCodeConfig(
            executable=executable,
            model=model,
            agent=agent,
            timeout_seconds=timeout_seconds,
            opencode_home=opencode_home,
            auto_approve=auto_approve,
            mcp_enabled=mcp_enabled,
            mcp_autostart=mcp_autostart,
            mcp_host=mcp_host,
            mcp_port=mcp_port,
            mcp_public_url=mcp_public_url,
            mcp_admin_token=mcp_admin_token,
        )

    def _attempt_opencode_config(
        self,
        config: OpenCodeConfig,
        *,
        context: BackendRunContext,
        attempt_run_id: str,
        task: Task,
        workspace: Path,
    ) -> OpenCodeConfig:
        home_root = os.environ.get("ACTBENCH_OPENCODE_HOME_ROOT", "").strip()
        opencode_home = backend_attempt_home(
            home_root=home_root,
            context=context,
            attempt_run_id=attempt_run_id,
            task=task,
            workspace=workspace,
            leaf_name="opencode_home",
        )
        return replace(config, opencode_home=opencode_home)

    def _prepare_opencode_home(self, config: OpenCodeConfig) -> None:
        try:
            for directory in (
                config.opencode_home,
                config.config_dir,
                config.data_dir,
                config.state_dir,
                config.cache_dir,
                config.home_dir,
            ):
                directory.mkdir(parents=True, exist_ok=True)
            (config.opencode_home / "actbench-config.json").write_text(
                json.dumps(_opencode_config_payload(config), indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        except OSError as exc:
            raise BackendInitializationError(
                f"opencode backend could not write isolated config in {config.opencode_home}: {exc}"
            ) from exc

    def _initialize_mcp_gateway(self, config: OpenCodeConfig) -> None:
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
                "opencode backend could not start or authenticate to the ActBench MCP gateway at "
                f"{config.mcp_admin_url}: {exc}. Set ACTBENCH_MCP_AUTOSTART=0 for an "
                "externally managed gateway or ACTBENCH_OPENCODE_ENABLE_ACTBENCH_MCP=0 "
                "for weak direct-workspace mode."
            ) from exc
        logger.info("   ActBench MCP gateway ready for opencode at %s", config.mcp_public_url)

    def _run_opencode_subprocess(
        self,
        *,
        config: OpenCodeConfig,
        prompt: str,
        workspace: Path,
        timeout_seconds: float,
    ) -> subprocess.CompletedProcess[str]:
        cmd = [
            config.executable,
            "run",
            "--format",
            "json",
            "--model",
            config.model,
            "--dir",
            str(workspace),
        ]
        if config.agent:
            cmd.extend(["--agent", config.agent])
        if config.auto_approve:
            cmd.append("--auto")
        cmd.extend(["--", prompt])
        return _run_subprocess_with_process_group(
            cmd,
            cwd=workspace,
            env=_opencode_env(config),
            timeout_seconds=timeout_seconds,
        )

    def _run_opencode_export(
        self,
        *,
        config: OpenCodeConfig,
        session_id: str,
        workspace: Path,
        timeout_seconds: float,
    ) -> subprocess.CompletedProcess[str]:
        cmd = [config.executable, "export", session_id]
        return _run_subprocess_with_stdout_file(
            cmd,
            cwd=workspace,
            env=_opencode_env(config),
            timeout_seconds=timeout_seconds,
        )

    def _extract_opencode_transcript(
        self,
        *,
        config: OpenCodeConfig,
        workspace: Path,
        effective_prompt: str,
        stdout: str,
        session_id: str | None,
        redactions: List[str],
        timeout_seconds: float,
    ) -> Tuple[List[Dict[str, Any]], str, Dict[str, Any], Dict[str, Any]]:
        metadata: Dict[str, Any] = {
            "method": "opencode_export",
            "session_id": session_id,
        }

        def fallback(
            reason: str,
        ) -> Tuple[List[Dict[str, Any]], str, Dict[str, Any], Dict[str, Any]]:
            fallback_metadata = dict(metadata)
            fallback_metadata["fallback_reason"] = reason
            transcript, source = _opencode_stdout_transcript_fallback(effective_prompt, stdout)
            return (
                _redact_transcript(transcript, redactions),
                f"opencode_export_{reason}_fallback_{source}",
                fallback_metadata,
                zero_usage(request_count=1),
            )

        if not session_id:
            return fallback("missing_session_id")

        try:
            completed = self._run_opencode_export(
                config=config,
                session_id=session_id,
                workspace=workspace,
                timeout_seconds=timeout_seconds,
            )
        except subprocess.TimeoutExpired:
            return fallback("timeout")
        except Exception as exc:  # noqa: BLE001 - transcript extraction must not break execution
            metadata["error_type"] = type(exc).__name__
            metadata["error"] = str(exc)[:200]
            return fallback("failed")

        export_payload, export_metadata = _coerce_export_payload(completed)
        metadata.update(export_metadata)
        if export_payload is None:
            return fallback("failed")

        transcript = _normalize_opencode_export_to_transcript(export_payload, redactions=redactions)
        metadata["transcript_messages"] = len(transcript)
        if not _has_usable_transcript(transcript):
            return fallback("unusable")
        usage = _usage_from_opencode_export(export_payload)
        return transcript, "opencode_export", metadata, usage


def _run_subprocess_with_process_group(
    cmd: List[str],
    *,
    cwd: Path,
    env: Dict[str, str],
    timeout_seconds: float,
) -> subprocess.CompletedProcess[str]:
    process = subprocess.Popen(
        cmd,
        cwd=str(cwd),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        stdout, stderr = process.communicate(timeout=timeout_seconds)
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


def _run_subprocess_with_stdout_file(
    cmd: List[str],
    *,
    cwd: Path,
    env: Dict[str, str],
    timeout_seconds: float,
) -> subprocess.CompletedProcess[str]:
    """Run a subprocess with stdout redirected to a file.

    Some CLIs, including opencode 1.18.3's ``export`` command, truncate large
    JSON payloads when stdout is a pipe. Writing stdout to a regular file avoids
    that truncation while preserving the same CompletedProcess interface.
    """

    with tempfile.NamedTemporaryFile(
        prefix="opencode-export-", suffix=".json", mode="w+b"
    ) as stdout_file:
        process = subprocess.Popen(
            cmd,
            cwd=str(cwd),
            env=env,
            stdout=stdout_file,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
        try:
            _, stderr = process.communicate(timeout=timeout_seconds)
        except subprocess.TimeoutExpired as exc:
            stderr = _coerce_text(getattr(exc, "stderr", ""))
            _terminate_process_group(process, signal.SIGTERM)
            try:
                _, terminated_stderr = process.communicate(timeout=2.0)
            except subprocess.TimeoutExpired:
                _terminate_process_group(process, signal.SIGKILL)
                try:
                    _, terminated_stderr = process.communicate(timeout=2.0)
                except subprocess.TimeoutExpired:
                    terminated_stderr = stderr
            stderr = _coerce_text(terminated_stderr) or stderr
            stdout_file.flush()
            stdout_file.seek(0)
            stdout = _coerce_text(stdout_file.read())
            raise subprocess.TimeoutExpired(
                cmd=cmd,
                timeout=timeout_seconds,
                output=stdout,
                stderr=stderr,
            ) from exc
        stdout_file.flush()
        stdout_file.seek(0)
        stdout = _coerce_text(stdout_file.read())
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


def _opencode_env(config: OpenCodeConfig) -> Dict[str, str]:
    env = os.environ.copy()
    env["HOME"] = str(config.home_dir)
    env["XDG_CONFIG_HOME"] = str(config.config_dir)
    env["XDG_DATA_HOME"] = str(config.data_dir)
    env["XDG_STATE_HOME"] = str(config.state_dir)
    env["XDG_CACHE_HOME"] = str(config.cache_dir)
    env["OPENCODE_CONFIG_DIR"] = str(config.config_dir)
    env["OPENCODE_DB"] = str(config.db_path)
    env["OPENCODE_CONFIG_CONTENT"] = json.dumps(_opencode_config_payload(config), sort_keys=True)
    env["OPENCODE_DISABLE_PROJECT_CONFIG"] = "1"
    env["OPENCODE_PURE"] = "1"
    env["OPENCODE_DISABLE_AUTOUPDATE"] = "1"
    env.setdefault("NO_COLOR", "1")
    env.pop("ACTBENCH_MCP_ADMIN_TOKEN", None)
    return env


def _opencode_config_payload(config: OpenCodeConfig) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "model": config.model,
        "share": "disabled",
        "autoupdate": False,
        "permission": {
            "read": "allow",
            "edit": "allow",
            "glob": "allow",
            "grep": "allow",
            "list": "allow",
            "bash": "allow",
            "task": "allow",
            "external_directory": "deny",
            "webfetch": "allow",
            "websearch": "allow",
        },
        "tool_output": {
            "max_lines": 2000,
            "max_bytes": 51200,
        },
    }
    if config.agent:
        payload["default_agent"] = config.agent
    if config.mcp_enabled:
        payload["mcp"] = {
            "actbench": {
                "type": "remote",
                "url": config.mcp_public_url,
                "enabled": True,
                "oauth": False,
            }
        }
    return payload


def _augment_opencode_result(
    result: Dict[str, Any],
    *,
    context: BackendRunContext,
    config: OpenCodeConfig,
    transcript_source: str = "opencode_run_stdout_raw",
    transcript_extraction: Dict[str, Any] | None = None,
    session_id: str | None = None,
) -> Dict[str, Any]:
    return augment_execution_result(
        result,
        context=context,
        transcript_source=transcript_source,
        transcript_extraction=transcript_extraction,
        executable=config.executable,
        agent=config.agent,
        auto_approve=config.auto_approve,
        opencode_home=str(config.opencode_home),
        opencode_db=str(config.db_path),
        opencode_session_id=session_id,
        mcp_enabled=config.mcp_enabled,
        mcp_public_url=config.mcp_public_url if config.mcp_enabled else None,
    )


def _result_api_endpoints(config: OpenCodeConfig, api_endpoints: Dict[str, Any]) -> Dict[str, Any]:
    if not config.mcp_enabled:
        return api_endpoints
    return sanitize_api_endpoints(api_endpoints)


def _coerce_export_payload(raw_completed: Any) -> Tuple[Dict[str, Any] | None, Dict[str, Any]]:
    metadata: Dict[str, Any] = {}
    if isinstance(raw_completed, dict):
        metadata["export_exit_code"] = 0
        return raw_completed, metadata

    if isinstance(raw_completed, subprocess.CompletedProcess):
        metadata["export_exit_code"] = int(raw_completed.returncode)
        stdout = _coerce_text(raw_completed.stdout)
        stderr = _coerce_text(raw_completed.stderr)
        if stderr.strip():
            metadata["export_stderr"] = stderr.strip()[:500]
        if raw_completed.returncode != 0:
            return None, metadata
    else:
        metadata["export_exit_code"] = 0
        stdout = _coerce_text(raw_completed)

    try:
        parsed = json.loads(stdout)
    except json.JSONDecodeError as exc:
        metadata["parse_error"] = str(exc)[:200]
        return None, metadata
    if isinstance(parsed, list):
        return {"messages": parsed}, metadata
    if not isinstance(parsed, dict):
        metadata["parse_error"] = f"expected object, got {type(parsed).__name__}"
        return None, metadata
    return parsed, metadata


def _extract_session_id_from_run_stdout(raw: str) -> str | None:
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        session_id = _find_session_id(parsed)
        if session_id:
            return session_id
    return None


def _find_session_id(value: Any) -> str | None:
    if isinstance(value, dict):
        for key in ("sessionID", "session_id", "sessionId"):
            raw = value.get(key)
            if isinstance(raw, str) and raw.strip():
                return raw.strip()
        for key in ("properties", "part", "message", "info"):
            nested = _find_session_id(value.get(key))
            if nested:
                return nested
    if isinstance(value, list):
        for item in value:
            nested = _find_session_id(item)
            if nested:
                return nested
    return None


def _normalize_opencode_export_to_transcript(
    export_payload: Dict[str, Any],
    *,
    redactions: Iterable[str | None] = (),
) -> List[Dict[str, Any]]:
    raw_messages = export_payload.get("messages")
    if not isinstance(raw_messages, list):
        return []
    transcript: List[Dict[str, Any]] = []
    for raw_message in raw_messages:
        if not isinstance(raw_message, dict):
            continue
        transcript.extend(_normalize_opencode_message(raw_message))
    return _redact_transcript(transcript, redactions)


def _normalize_opencode_message(message: Dict[str, Any]) -> List[Dict[str, Any]]:
    if isinstance(message.get("info"), dict) and isinstance(message.get("parts"), list):
        return _normalize_opencode_with_parts_message(message)

    message_type = str(message.get("type") or "").strip()
    if message_type in {"system", "synthetic", "agent-switched", "model-switched", "compaction"}:
        return []
    if message_type == "user":
        text = _content_to_text(message.get("text"))
        if not text.strip():
            return []
        return [{"type": "message", "message": {"role": "user", "content": [text]}}]
    if message_type == "shell":
        return _normalize_opencode_shell_message(message)
    if message_type != "assistant":
        return []

    return _normalize_opencode_assistant_parts(
        message.get("content") if isinstance(message.get("content"), list) else [],
        error=message.get("error"),
    )


def _normalize_opencode_with_parts_message(message: Dict[str, Any]) -> List[Dict[str, Any]]:
    info = message.get("info") if isinstance(message.get("info"), dict) else {}
    role = str(info.get("role") or "").strip()
    parts = message.get("parts") if isinstance(message.get("parts"), list) else []
    if role == "user":
        content = _normalize_opencode_user_parts(parts)
        if not content:
            return []
        return [{"type": "message", "message": {"role": "user", "content": content}}]
    if role == "assistant":
        return _normalize_opencode_assistant_parts(parts, error=info.get("error"))
    return []


def _normalize_opencode_user_parts(parts: List[Any]) -> List[Any]:
    content: List[Any] = []
    for part in parts:
        if isinstance(part, str):
            if part.strip():
                content.append(part)
            continue
        if not isinstance(part, dict):
            continue
        part_type = str(part.get("type") or "")
        if part_type == "text":
            text = _content_to_text(part.get("text"))
            if text.strip():
                content.append(text)
        elif part_type == "file":
            file_text = _opencode_file_part_text(part)
            if file_text.strip():
                content.append(file_text)
    return content


def _normalize_opencode_assistant_parts(
    parts: List[Any],
    *,
    error: Any = None,
) -> List[Dict[str, Any]]:
    assistant_blocks: List[Dict[str, Any]] = []
    followup_entries: List[Dict[str, Any]] = []
    for item in parts:
        if not isinstance(item, dict):
            continue
        item_type = str(item.get("type") or "")
        if item_type == "text":
            text = _content_to_text(item.get("text"))
            if text.strip():
                assistant_blocks.append({"type": "text", "text": text})
        elif item_type == "tool":
            call_block, result_entry = _normalize_opencode_tool_part(item)
            if call_block is not None:
                assistant_blocks.append(call_block)
            if result_entry is not None:
                followup_entries.append(result_entry)
        elif item_type == "reasoning":
            # opencode may persist raw reasoning. ActBench scoring needs actions and final
            # content, not private chain-of-thought, so omit reasoning blocks.
            continue

    error_text = _opencode_error_text(error)
    if error_text.strip():
        assistant_blocks.append({"type": "text", "text": f"opencode error: {error_text}"})

    entries: List[Dict[str, Any]] = []
    if assistant_blocks:
        entries.append(
            {"type": "message", "message": {"role": "assistant", "content": assistant_blocks}}
        )
    entries.extend(followup_entries)
    return entries


def _opencode_file_part_text(part: Dict[str, Any]) -> str:
    source = part.get("source") if isinstance(part.get("source"), dict) else {}
    source_text = source.get("text") if isinstance(source.get("text"), dict) else {}
    text = source_text.get("value")
    if isinstance(text, str):
        return text
    filename = part.get("filename") or source.get("path") or part.get("url")
    return f"[file: {filename}]" if filename else ""


def _opencode_error_text(error: Any) -> str:
    if isinstance(error, dict):
        data = error.get("data") if isinstance(error.get("data"), dict) else {}
        return _content_to_text(error.get("message") or data.get("message") or error)
    return _content_to_text(error)


def _normalize_opencode_tool_part(
    part: Dict[str, Any],
) -> Tuple[Dict[str, Any] | None, Dict[str, Any] | None]:
    name = part.get("name") or part.get("tool")
    if not isinstance(name, str) or not name.strip():
        return None, None
    name = name.strip()
    state = part.get("state") if isinstance(part.get("state"), dict) else {}
    raw_arguments = state.get("input")
    if raw_arguments is None:
        raw_arguments = part.get("input")
    if raw_arguments is None:
        raw_arguments = part.get("arguments")
    arguments = _redact_mcp_trace_value(_coerce_tool_arguments(raw_arguments))
    call_id = str(part.get("callID") or part.get("id") or part.get("tool_call_id") or name)
    call_block: Dict[str, Any] = {
        "type": "toolCall",
        "name": name,
        "arguments": arguments,
        "id": call_id,
    }

    status = str(state.get("status") or "")
    if status not in {"completed", "error"}:
        return call_block, None

    result_block: Dict[str, Any] = {
        "type": "toolResult",
        "text": _opencode_tool_state_result_text(state),
        "tool_call_id": call_id,
        "name": name,
        "isError": status == "error",
    }
    return call_block, {
        "type": "message",
        "message": {"role": "toolResult", "content": [result_block]},
    }


def _normalize_opencode_shell_message(message: Dict[str, Any]) -> List[Dict[str, Any]]:
    command = _content_to_text(message.get("command"))
    if not command.strip():
        return []
    call_id = str(message.get("callID") or message.get("id") or "shell")
    output = _content_to_text(message.get("output"))
    return [
        {
            "type": "message",
            "message": {
                "role": "assistant",
                "content": [
                    {
                        "type": "toolCall",
                        "name": "shell",
                        "arguments": {"command": command},
                        "id": call_id,
                    }
                ],
            },
        },
        {
            "type": "message",
            "message": {
                "role": "toolResult",
                "content": [
                    {
                        "type": "toolResult",
                        "text": output,
                        "tool_call_id": call_id,
                        "name": "shell",
                        "isError": False,
                    }
                ],
            },
        },
    ]


def _opencode_tool_state_result_text(state: Dict[str, Any]) -> str:
    if state.get("output") is not None:
        return _content_to_text(state.get("output"))
    if state.get("result") is not None:
        return _content_to_text(state.get("result"))
    content_text = _content_to_text(state.get("content"))
    if content_text:
        return content_text
    if state.get("error") is not None:
        return _opencode_error_text(state.get("error"))
    if state.get("structured") is not None:
        return _content_to_text(state.get("structured"))
    return ""


def _opencode_stdout_transcript_fallback(
    prompt: str, stdout: str
) -> Tuple[List[Dict[str, Any]], str]:
    transcript = _normalize_opencode_run_stdout_to_transcript(prompt, stdout)
    if _has_usable_transcript(transcript):
        return transcript, "run_stdout_json"
    return stdout_transcript_fallback(prompt, stdout), "run_stdout_raw"


def _normalize_opencode_run_stdout_to_transcript(prompt: str, stdout: str) -> List[Dict[str, Any]]:
    transcript: List[Dict[str, Any]] = [
        {"type": "message", "message": {"role": "user", "content": [prompt]}}
    ]
    for line in stdout.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            event = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        event_type = str(event.get("type") or "")
        part = event.get("part") if isinstance(event.get("part"), dict) else {}
        if event_type == "text":
            text = _content_to_text(part.get("text"))
            if text.strip():
                transcript.append(
                    {
                        "type": "message",
                        "message": {
                            "role": "assistant",
                            "content": [{"type": "text", "text": text}],
                        },
                    }
                )
        elif event_type == "tool_use":
            call_block, result_entry = _normalize_opencode_tool_part(part)
            if call_block is not None:
                transcript.append(
                    {
                        "type": "message",
                        "message": {"role": "assistant", "content": [call_block]},
                    }
                )
            if result_entry is not None:
                transcript.append(result_entry)
        elif event_type == "error":
            error_text = _content_to_text(event.get("error"))
            if error_text.strip():
                transcript.append(
                    {
                        "type": "message",
                        "message": {
                            "role": "assistant",
                            "content": [{"type": "text", "text": f"opencode error: {error_text}"}],
                        },
                    }
                )
    return transcript


def _usage_from_opencode_export(export_payload: Dict[str, Any]) -> Dict[str, Any]:
    usage = zero_usage(request_count=0)
    messages = export_payload.get("messages")
    if not isinstance(messages, list):
        return usage
    assistant_messages = 0
    assistant_messages_with_tokens = 0
    for message in messages:
        if not isinstance(message, dict):
            continue
        info = message.get("info") if isinstance(message.get("info"), dict) else None
        if info is not None:
            role = info.get("role")
            tokens_source = info.get("tokens") if isinstance(info.get("tokens"), dict) else None
            cost_source = info.get("cost", 0.0)
        else:
            role = message.get("type")
            tokens_source = (
                message.get("tokens") if isinstance(message.get("tokens"), dict) else None
            )
            cost_source = message.get("cost", 0.0)
        if role != "assistant":
            continue
        assistant_messages += 1
        tokens = tokens_source or _step_finish_tokens(message.get("parts"))
        if tokens:
            assistant_messages_with_tokens += 1
        _add_opencode_tokens_to_usage(usage, tokens)
        usage["cost_usd"] += _safe_float(cost_source)
        if _safe_float(cost_source) == 0.0:
            usage["cost_usd"] += _step_finish_cost(message.get("parts"))
    usage["request_count"] = assistant_messages_with_tokens or assistant_messages
    return usage


def _step_finish_tokens(parts: Any) -> Dict[str, Any]:
    if not isinstance(parts, list):
        return {}
    combined: Dict[str, Any] = {
        "input": 0,
        "output": 0,
        "reasoning": 0,
        "cache": {"read": 0, "write": 0},
    }
    found = False
    for part in parts:
        if not isinstance(part, dict) or part.get("type") != "step-finish":
            continue
        raw_tokens = part.get("tokens") if isinstance(part.get("tokens"), dict) else {}
        if not raw_tokens:
            continue
        found = True
        combined["input"] += _safe_int(raw_tokens.get("input", 0))
        combined["output"] += _safe_int(raw_tokens.get("output", 0))
        combined["reasoning"] += _safe_int(raw_tokens.get("reasoning", 0))
        cache = raw_tokens.get("cache") if isinstance(raw_tokens.get("cache"), dict) else {}
        combined["cache"]["read"] += _safe_int(cache.get("read", 0))
        combined["cache"]["write"] += _safe_int(cache.get("write", 0))
        if raw_tokens.get("total") is not None:
            combined["total"] = _safe_int(combined.get("total", 0)) + _safe_int(
                raw_tokens.get("total")
            )
    return combined if found else {}


def _step_finish_cost(parts: Any) -> float:
    if not isinstance(parts, list):
        return 0.0
    total = 0.0
    for part in parts:
        if isinstance(part, dict) and part.get("type") == "step-finish":
            total += _safe_float(part.get("cost", 0.0))
    return total


def _add_opencode_tokens_to_usage(usage: Dict[str, Any], tokens: Dict[str, Any]) -> None:
    input_tokens = _safe_int(tokens.get("input", 0))
    output_tokens = _safe_int(tokens.get("output", 0)) + _safe_int(tokens.get("reasoning", 0))
    cache = tokens.get("cache") if isinstance(tokens.get("cache"), dict) else {}
    usage["input_tokens"] += input_tokens
    usage["output_tokens"] += output_tokens
    usage["cache_read_tokens"] += _safe_int(cache.get("read", 0))
    usage["cache_write_tokens"] += _safe_int(cache.get("write", 0))
    explicit_total = tokens.get("total")
    if explicit_total is not None:
        usage["total_tokens"] += _safe_int(explicit_total)
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
            result_block["isError"] = bool(trace.get("isError"))
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
        "ActBench has exposed task-scoped tools through the opencode MCP server "
        f"named `actbench` at {mcp_public_url}. For this task, always pass "
        f"context_id `{context_id}` exactly when calling ActBench MCP tools. Use "
        "actbench_list_files, actbench_read_file, and actbench_write_file to inspect or "
        "modify the task workspace. Use actbench_get_api_endpoints to discover declared "
        "mock API services, then call them only through actbench_call_api. If opencode "
        "displays these tools with the server prefix, such as actbench_actbench_read_file, "
        "use the prefixed tool names it exposes. Do not assume fixed localhost ports and "
        "do not call mock APIs directly."
    )


def _subprocess_timeout(*, config: OpenCodeConfig, remaining: float) -> float:
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
    timeout_raw = os.environ.get("ACTBENCH_OPENCODE_TIMEOUT_SECONDS")
    if timeout_raw is None or not timeout_raw.strip():
        return None
    try:
        timeout_seconds = float(timeout_raw)
    except ValueError as exc:
        raise BackendInitializationError(
            f"ACTBENCH_OPENCODE_TIMEOUT_SECONDS must be numeric, got {timeout_raw!r}"
        ) from exc
    if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
        raise BackendInitializationError(
            "ACTBENCH_OPENCODE_TIMEOUT_SECONDS must be a finite positive number"
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
    raw = executable.strip() or DEFAULT_OPENCODE_EXECUTABLE
    expanded = Path(raw).expanduser()
    if expanded.name != raw or os.sep in raw:
        if not expanded.is_file():
            raise BackendInitializationError(f"opencode executable not found: {expanded}")
        return str(expanded)
    resolved = shutil.which(raw)
    if not resolved:
        raise BackendInitializationError(
            f"opencode backend requires the `{raw}` executable on PATH. "
            "Set ACTBENCH_OPENCODE_BIN to the opencode CLI path."
        )
    return resolved


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
    return redacted


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
