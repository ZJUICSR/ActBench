"""OpenAgent backend adapter using its OpenAI-compatible HTTP API."""

from __future__ import annotations

import json
import logging
import math
import os
import secrets
import socket
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
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
    zero_usage,
)

logger = logging.getLogger(__name__)

DEFAULT_OPENAGENT_BASE_URL = "http://localhost:14000"
DEFAULT_OPENAGENT_ENDPOINT = "/api/v1/chat/completions"
DEFAULT_OPENAGENT_TIMEOUT_SECONDS = 120.0


@dataclass(frozen=True)
class OpenAgentConfig:
    base_url: str
    endpoint: str
    api_key: str
    timeout_seconds: float | None
    mcp_enabled: bool
    mcp_autostart: bool
    mcp_host: str
    mcp_port: int
    mcp_public_url: str
    mcp_admin_token: str | None

    @property
    def health_url(self) -> str:
        return _join_url(self.base_url, "/api/health")

    @property
    def completions_url(self) -> str:
        return _join_url(self.base_url, self.endpoint)

    @property
    def mcp_admin_url(self) -> str:
        return f"http://{self.mcp_host}:{self.mcp_port}/mcp"


class OpenAgentRequestError(RuntimeError):
    """Raised when the OpenAgent HTTP API returns an invalid or failed response."""


class OpenAgentTimeoutError(OpenAgentRequestError):
    """Raised when an OpenAgent HTTP request times out."""


class OpenAgentBackend:
    """ActBench backend that drives a running OpenAgent service over HTTP."""

    name = "openagent"
    uses_gateway_lock = False

    def __init__(self) -> None:
        self._config: OpenAgentConfig | None = None
        self._mcp_gateway: ActBenchMcpGatewayProcess | None = None

    def slugify_model(self, model_id: str) -> str:
        return default_slugify_model(model_id)

    def make_agent_id(self, model_id: str) -> str:
        return default_agent_id(model_id)

    def initialize_run(self, context: BackendRunContext) -> None:
        context.agent_workspace.mkdir(parents=True, exist_ok=True)
        config = self._load_config()
        self._check_health(config)
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
        config = self._config or self._load_config()
        logger.info("🤖 OpenAgent backend [%s] starting task: %s", context.agent_id, task.task_id)
        start_time = time.time()
        session_id = f"{task.task_id}_{int(start_time * 1000)}"
        workspace = backend_task_workspace(context=context, attempt_run_id=attempt_run_id, task=task)
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
            return _augment_openagent_result(
                execution_error_result(
                    context=context,
                    task=task,
                    workspace=workspace,
                    stderr=f"openagent workspace setup failed: {exc}",
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
                return _augment_openagent_result(
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
                    return _augment_openagent_result(
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
            messages: List[Dict[str, Any]] = []
            if config.mcp_enabled and mcp_context_id:
                messages.append(_mcp_system_message(config.mcp_public_url, mcp_context_id))
            if len(prompts) > 1:
                logger.info("📋 Multi-session task with %d sessions", len(prompts))

            for index, prompt in enumerate(prompts, 1):
                if len(prompts) > 1:
                    logger.info("   Session %d/%d", index, len(prompts))
                remaining = timeout_budget - (time.time() - start_time)
                if remaining <= 0:
                    timed_out = True
                    status = "timeout"
                    exit_code = -1
                    stderr = "openagent execution timed out before sending the next prompt"
                    break

                messages.append({"role": "user", "content": prompt})
                transcript.append(_transcript_message("user", prompt))
                try:
                    request_timeout = _request_timeout(config=config, remaining=remaining)
                    response = self._post_chat_completion(
                        config=config,
                        model_id=context.model,
                        messages=messages,
                        timeout_seconds=request_timeout,
                    )
                    assistant_message = _assistant_message(response)
                    if assistant_message is None or _assistant_message_is_empty(assistant_message):
                        status = "error"
                        exit_code = -1
                        stderr = "openagent response did not include assistant content"
                        break

                    messages.append(_request_assistant_message(assistant_message))
                    transcript.append(_transcript_from_openai_message(assistant_message))
                    assistant_text = _assistant_content_text(assistant_message)
                    if assistant_text:
                        stdout = f"{stdout}\n{assistant_text}".strip()
                    usage = _add_usage(usage, _normalize_usage(response.get("usage"), request_count=1))
                except OpenAgentTimeoutError as exc:
                    timed_out = True
                    status = "timeout"
                    exit_code = -1
                    stderr = str(exc)
                    logger.warning("   %s", stderr)
                    break
                except OpenAgentRequestError as exc:
                    status = "error"
                    exit_code = -1
                    stderr = str(exc)
                    logger.warning("   %s", stderr)
                    break
                except Exception as exc:  # noqa: BLE001 - surface unexpected backend failures
                    status = "error"
                    exit_code = -1
                    stderr = f"openagent execution failed: {exc}"
                    logger.warning("   %s", stderr)
                    break

            if not transcript and status == "success":
                status = "error"
                exit_code = -1
                stderr = "openagent execution produced no transcript"

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
            return _augment_openagent_result(result, context=context, config=config)
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

    def _initialize_mcp_gateway(self, config: OpenAgentConfig) -> None:
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
                "openagent backend could not start or reach the ActBench MCP gateway at "
                f"{config.mcp_admin_url}: {exc}. Set ACTBENCH_MCP_AUTOSTART=0 for an "
                "externally managed gateway or OPENAGENT_ENABLE_ACTBENCH_MCP=0 for weak "
                "HTTP-only mode."
            ) from exc
        logger.info("   ActBench MCP gateway ready for OpenAgent at %s", config.mcp_public_url)

    def _load_config(self) -> OpenAgentConfig:
        api_key = os.environ.get("OPENAGENT_API_KEY", "").strip()
        if not api_key:
            raise BackendInitializationError(
                "openagent backend requires OPENAGENT_API_KEY for the running OpenAgent service. "
                "Start OpenAgent and export a Store or Provider external API key."
            )

        timeout_seconds = _load_timeout_seconds()
        base_url = os.environ.get("OPENAGENT_BASE_URL", DEFAULT_OPENAGENT_BASE_URL).strip().rstrip(
            "/"
        )
        if not base_url:
            raise BackendInitializationError("OPENAGENT_BASE_URL must not be blank")
        endpoint = os.environ.get("OPENAGENT_ENDPOINT", DEFAULT_OPENAGENT_ENDPOINT).strip()
        if not endpoint:
            raise BackendInitializationError("OPENAGENT_ENDPOINT must not be blank")

        mcp_enabled = _env_flag("OPENAGENT_ENABLE_ACTBENCH_MCP", default=True)
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

        return OpenAgentConfig(
            base_url=base_url,
            endpoint=endpoint,
            api_key=api_key,
            timeout_seconds=timeout_seconds,
            mcp_enabled=mcp_enabled,
            mcp_autostart=mcp_autostart,
            mcp_host=mcp_host,
            mcp_port=mcp_port,
            mcp_public_url=mcp_public_url,
            mcp_admin_token=mcp_admin_token,
        )

    def _check_health(self, config: OpenAgentConfig) -> None:
        try:
            _request_text(
                config.health_url,
                method="GET",
                timeout_seconds=min(config.timeout_seconds or DEFAULT_OPENAGENT_TIMEOUT_SECONDS, 10.0),
            )
        except OpenAgentRequestError as exc:
            raise BackendInitializationError(
                "openagent backend could not reach a healthy OpenAgent service at "
                f"{config.health_url}: {exc}. Set OPENAGENT_BASE_URL or start OpenAgent first."
            ) from exc

    def _post_chat_completion(
        self,
        *,
        config: OpenAgentConfig,
        model_id: str,
        messages: List[Dict[str, Any]],
        timeout_seconds: float,
    ) -> Dict[str, Any]:
        payload = {
            "model": model_id,
            "stream": False,
            "messages": messages,
        }
        return _request_json(
            config.completions_url,
            method="POST",
            api_key=config.api_key,
            payload=payload,
            timeout_seconds=timeout_seconds,
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
    payload: Dict[str, Any] | None = None,
) -> str:
    headers = {"Accept": "application/json"}
    data = None
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            return response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        if exc.code in {408, 504}:
            raise OpenAgentTimeoutError(
                f"request to {url} timed out with HTTP {exc.code}: {_summarize_body(body)}"
            ) from exc
        raise OpenAgentRequestError(
            f"HTTP {exc.code} {exc.reason}: {_summarize_body(body)}"
        ) from exc
    except urllib.error.URLError as exc:
        reason = getattr(exc, "reason", exc)
        if isinstance(reason, (TimeoutError, socket.timeout)):
            raise OpenAgentTimeoutError(f"request to {url} timed out") from exc
        raise OpenAgentRequestError(f"request to {url} failed: {reason}") from exc
    except (TimeoutError, socket.timeout) as exc:
        raise OpenAgentTimeoutError(f"request to {url} timed out") from exc


def _request_json(
    url: str,
    *,
    method: str,
    timeout_seconds: float,
    api_key: str | None = None,
    payload: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    body = _request_text(
        url,
        method=method,
        timeout_seconds=timeout_seconds,
        api_key=api_key,
        payload=payload,
    )
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError as exc:
        raise OpenAgentRequestError(f"invalid JSON response: {_summarize_body(body)}") from exc
    if not isinstance(parsed, dict):
        raise OpenAgentRequestError(f"unexpected JSON response type: {type(parsed).__name__}")
    if parsed.get("error"):
        raise OpenAgentRequestError(_format_openai_error(parsed["error"]))
    if parsed.get("status") == "error" and "choices" not in parsed:
        raise OpenAgentRequestError(str(parsed.get("msg") or parsed.get("data") or parsed))
    return parsed


def _assistant_message(response: Dict[str, Any]) -> Dict[str, Any] | None:
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        return None
    first = choices[0]
    if not isinstance(first, dict):
        return None
    message = first.get("message")
    if not isinstance(message, dict):
        return None
    normalized = dict(message)
    normalized["role"] = str(normalized.get("role") or "assistant")
    return normalized


def _assistant_content_text(message: Dict[str, Any]) -> str:
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: List[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text") or item.get("content")
                if isinstance(text, str):
                    parts.append(text)
        return "".join(parts)
    return ""


def _assistant_message_is_empty(message: Dict[str, Any]) -> bool:
    if _assistant_content_text(message):
        return False
    content = message.get("content")
    if isinstance(content, list) and content:
        return False
    if message.get("tool_calls") or message.get("function_call"):
        return False
    return True


def _request_assistant_message(message: Dict[str, Any]) -> Dict[str, Any]:
    request_message: Dict[str, Any] = {"role": message.get("role") or "assistant"}
    for key in ("content", "tool_calls", "function_call", "name"):
        if key in message:
            request_message[key] = message[key]
    return request_message


def _normalize_usage(raw_usage: Any, *, request_count: int) -> Dict[str, Any]:
    usage = zero_usage(request_count=request_count)
    if not isinstance(raw_usage, dict):
        return usage
    input_tokens = raw_usage.get("prompt_tokens", raw_usage.get("input_tokens", 0)) or 0
    output_tokens = raw_usage.get("completion_tokens", raw_usage.get("output_tokens", 0)) or 0
    total_tokens = raw_usage.get("total_tokens", _safe_int(input_tokens) + _safe_int(output_tokens)) or 0
    usage["input_tokens"] = _safe_int(input_tokens)
    usage["output_tokens"] = _safe_int(output_tokens)
    usage["total_tokens"] = _safe_int(total_tokens)
    cost = raw_usage.get("cost_usd", raw_usage.get("cost", 0.0)) or 0.0
    usage["cost_usd"] = _safe_float(cost)
    return usage


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
        merged[key] = int(merged.get(key, 0) or 0) + int(increment.get(key, 0) or 0)
    merged["cost_usd"] = float(merged.get("cost_usd", 0.0) or 0.0) + float(
        increment.get("cost_usd", 0.0) or 0.0
    )
    return merged


def _transcript_message(role: str, text: str) -> Dict[str, Any]:
    if role == "assistant":
        content: List[Any] = [{"type": "text", "text": text}]
    else:
        content = [text]
    return {"type": "message", "message": {"role": role, "content": content}}


def _transcript_from_openai_message(message: Dict[str, Any]) -> Dict[str, Any]:
    role = str(message.get("role") or "assistant")
    content = message.get("content")
    if isinstance(content, str):
        transcript_content: Any = [{"type": "text", "text": content}]
    elif isinstance(content, list):
        transcript_content = content
    elif content is None:
        transcript_content = []
    else:
        transcript_content = [{"type": "text", "text": str(content)}]
    transcript_message: Dict[str, Any] = {"role": role, "content": transcript_content}
    for key in ("tool_calls", "function_call"):
        if key in message:
            transcript_message[key] = message[key]
    return {"type": "message", "message": transcript_message}


def _augment_openagent_result(
    result: Dict[str, Any],
    *,
    context: BackendRunContext,
    config: OpenAgentConfig,
) -> Dict[str, Any]:
    return augment_execution_result(
        result,
        context=context,
        transcript_source="openagent_openai_compatible",
        base_url=config.base_url,
        endpoint=config.endpoint,
        mcp_enabled=config.mcp_enabled,
        mcp_public_url=config.mcp_public_url if config.mcp_enabled else None,
    )


def _result_api_endpoints(config: OpenAgentConfig, api_endpoints: Dict[str, Any]) -> Dict[str, Any]:
    if not config.mcp_enabled:
        return api_endpoints
    return sanitize_api_endpoints(api_endpoints)


def _mcp_system_message(mcp_public_url: str, context_id: str) -> Dict[str, str]:
    content = (
        "ActBench has exposed task-scoped tools through the ActBench MCP server at "
        f"{mcp_public_url}. For this task, always pass context_id "
        f"`{context_id}` exactly when calling ActBench MCP tools. Use "
        "actbench_list_files, actbench_read_file, and actbench_write_file to inspect or "
        "modify the task workspace. Use actbench_get_api_endpoints to discover declared "
        "mock API services, then call them only through actbench_call_api. Do not assume "
        "fixed localhost ports and do not call mock APIs directly."
    )
    return {"role": "system", "content": content}


def _request_timeout(*, config: OpenAgentConfig, remaining: float) -> float:
    if config.timeout_seconds is None:
        return max(remaining, 0.001)
    return max(min(config.timeout_seconds, remaining), 0.001)


def _load_timeout_seconds() -> float | None:
    timeout_raw = os.environ.get("OPENAGENT_TIMEOUT_SECONDS")
    if timeout_raw is None or not timeout_raw.strip():
        return None
    try:
        timeout_seconds = float(timeout_raw)
    except ValueError as exc:
        raise BackendInitializationError(
            f"OPENAGENT_TIMEOUT_SECONDS must be numeric, got {timeout_raw!r}"
        ) from exc
    if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
        raise BackendInitializationError("OPENAGENT_TIMEOUT_SECONDS must be a finite positive number")
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


def _format_openai_error(raw_error: Any) -> str:
    if isinstance(raw_error, dict):
        message = raw_error.get("message") or raw_error.get("type") or raw_error.get("code")
        if message:
            return f"OpenAgent error: {message}"
    return f"OpenAgent error: {raw_error}"


def _summarize_body(body: str, limit: int = 500) -> str:
    compact = " ".join(body.split())
    if len(compact) > limit:
        return compact[:limit] + "..."
    return compact
