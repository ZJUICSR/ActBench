"""OpenAgent backend adapter using its OpenAI-compatible HTTP API."""

from __future__ import annotations

import json
import logging
import os
import socket
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, List

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
    timeout_seconds: float

    @property
    def health_url(self) -> str:
        return _join_url(self.base_url, "/api/health")

    @property
    def completions_url(self) -> str:
        return _join_url(self.base_url, self.endpoint)


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
        config = self._config or self._load_config()
        logger.info("🤖 OpenAgent backend [%s] starting task: %s", context.agent_id, task.task_id)
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
        usage = zero_usage(request_count=0)
        status = "success"
        timed_out = False

        try:
            materialize_task_workspace(workspace=workspace, skill_dir=context.skill_dir, task=task)
        except Exception as exc:  # noqa: BLE001 - convert setup issues to execution result
            return execution_error_result(
                context=context,
                task=task,
                workspace=workspace,
                stderr=f"openagent workspace setup failed: {exc}",
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
            messages: List[Dict[str, str]] = []
            timeout_budget = task.timeout_seconds * context.timeout_multiplier
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
                    response = self._post_chat_completion(
                        config=config,
                        model_id=context.model,
                        messages=messages,
                        timeout_seconds=min(config.timeout_seconds, remaining),
                    )
                    assistant_text = _assistant_content(response)
                    if not assistant_text:
                        status = "error"
                        exit_code = -1
                        stderr = "openagent response did not include assistant content"
                        break
                    messages.append({"role": "assistant", "content": assistant_text})
                    transcript.append(_transcript_message("assistant", assistant_text))
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
                "api_endpoints": api_endpoints,
                "training_artifact_key": artifact_key,
            }
            return augment_execution_result(
                result,
                context=context,
                transcript_source="openagent_openai_compatible",
                base_url=config.base_url,
                endpoint=config.endpoint,
            )
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

    def _load_config(self) -> OpenAgentConfig:
        api_key = os.environ.get("OPENAGENT_API_KEY", "").strip()
        if not api_key:
            raise BackendInitializationError(
                "openagent backend requires OPENAGENT_API_KEY for the running OpenAgent service. "
                "Start OpenAgent and export a Store or Provider external API key."
            )

        timeout_raw = os.environ.get(
            "OPENAGENT_TIMEOUT_SECONDS", str(DEFAULT_OPENAGENT_TIMEOUT_SECONDS)
        )
        try:
            timeout_seconds = float(timeout_raw)
        except ValueError as exc:
            raise BackendInitializationError(
                f"OPENAGENT_TIMEOUT_SECONDS must be numeric, got {timeout_raw!r}"
            ) from exc
        if timeout_seconds <= 0:
            raise BackendInitializationError("OPENAGENT_TIMEOUT_SECONDS must be positive")

        return OpenAgentConfig(
            base_url=os.environ.get("OPENAGENT_BASE_URL", DEFAULT_OPENAGENT_BASE_URL).strip().rstrip(
                "/"
            ),
            endpoint=os.environ.get("OPENAGENT_ENDPOINT", DEFAULT_OPENAGENT_ENDPOINT).strip(),
            api_key=api_key,
            timeout_seconds=timeout_seconds,
        )

    def _check_health(self, config: OpenAgentConfig) -> None:
        try:
            _request_text(
                config.health_url,
                method="GET",
                timeout_seconds=min(config.timeout_seconds, 10.0),
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
        messages: List[Dict[str, str]],
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
    if parsed.get("status") == "error" and "choices" not in parsed:
        raise OpenAgentRequestError(str(parsed.get("msg") or parsed.get("data") or parsed))
    return parsed


def _assistant_content(response: Dict[str, Any]) -> str:
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    first = choices[0]
    if not isinstance(first, dict):
        return ""
    message = first.get("message")
    if not isinstance(message, dict):
        return ""
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


def _normalize_usage(raw_usage: Any, *, request_count: int) -> Dict[str, Any]:
    usage = zero_usage(request_count=request_count)
    if not isinstance(raw_usage, dict):
        return usage
    input_tokens = raw_usage.get("prompt_tokens", raw_usage.get("input_tokens", 0)) or 0
    output_tokens = raw_usage.get("completion_tokens", raw_usage.get("output_tokens", 0)) or 0
    total_tokens = raw_usage.get("total_tokens", input_tokens + output_tokens) or 0
    usage["input_tokens"] = _safe_int(input_tokens)
    usage["output_tokens"] = _safe_int(output_tokens)
    usage["total_tokens"] = _safe_int(total_tokens)
    cost = raw_usage.get("cost_usd", raw_usage.get("cost", 0.0)) or 0.0
    usage["cost_usd"] = float(cost) if isinstance(cost, (int, float)) else 0.0
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


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _summarize_body(body: str, limit: int = 500) -> str:
    compact = " ".join(body.split())
    if len(compact) > limit:
        return compact[:limit] + "..."
    return compact
