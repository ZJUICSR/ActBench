"""Task-scoped MCP gateway for ActBench backend adapters."""

from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response

from lib_api_services import SERVICE_SPECS

DEFAULT_MCP_HOST = "127.0.0.1"
DEFAULT_MCP_PORT = 8765
DEFAULT_CONTEXT_TTL_SECONDS = 3600.0
MAX_FILE_BYTES = 1024 * 1024
JSON_RPC_VERSION = "2.0"
MCP_PROTOCOL_VERSION = "2024-11-05"
ADMIN_TOKEN_ENV = "ACTBENCH_MCP_ADMIN_TOKEN"
INTERNAL_WORKSPACE_FILES = {"api_endpoints.json"}


@dataclass(frozen=True)
class ActBenchMcpContext:
    context_id: str
    workspace: Path
    api_endpoints: dict[str, Any]
    created_at: float
    expires_at: float
    traces: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class ActBenchMcpGatewayProcess:
    process: subprocess.Popen[str] | None
    host: str
    port: int
    mcp_url: str
    admin_token: str | None = None

    @property
    def started_by_actbench(self) -> bool:
        return self.process is not None


class ActBenchMcpError(RuntimeError):
    """Raised when an MCP tool or lifecycle helper fails."""


class ActBenchMcpRegistry:
    """Thread-safe in-memory registry of active ActBench task contexts."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._contexts: dict[str, ActBenchMcpContext] = {}

    def register(
        self,
        *,
        context_id: str,
        workspace: str | Path,
        api_endpoints: dict[str, Any] | None = None,
        ttl_seconds: float = DEFAULT_CONTEXT_TTL_SECONDS,
    ) -> ActBenchMcpContext:
        normalized_id = str(context_id).strip()
        if not normalized_id:
            raise ActBenchMcpError("context_id is required")
        try:
            ttl = float(ttl_seconds)
        except (TypeError, ValueError) as exc:
            raise ActBenchMcpError("ttl_seconds must be numeric") from exc
        if not math.isfinite(ttl) or ttl <= 0:
            raise ActBenchMcpError("ttl_seconds must be a finite positive number")

        workspace_path = Path(workspace).expanduser().resolve()
        if not workspace_path.is_dir():
            raise ActBenchMcpError(f"workspace does not exist: {workspace_path}")

        now = time.time()
        context = ActBenchMcpContext(
            context_id=normalized_id,
            workspace=workspace_path,
            api_endpoints=dict(api_endpoints or {}),
            created_at=now,
            expires_at=now + ttl,
        )
        with self._lock:
            self._cleanup_locked(now=now)
            self._contexts[normalized_id] = context
        return context

    def unregister(self, context_id: str) -> bool:
        normalized_id = str(context_id).strip()
        with self._lock:
            return self._contexts.pop(normalized_id, None) is not None

    def get(self, context_id: str) -> ActBenchMcpContext:
        normalized_id = str(context_id).strip()
        now = time.time()
        with self._lock:
            self._cleanup_locked(now=now)
            context = self._contexts.get(normalized_id)
            if context is None:
                raise ActBenchMcpError("unknown or expired context_id")
            return context

    def record_trace(self, context_id: str, trace: dict[str, Any]) -> dict[str, Any]:
        normalized_id = str(context_id).strip()
        now = time.time()
        with self._lock:
            self._cleanup_locked(now=now)
            context = self._contexts.get(normalized_id)
            if context is None:
                raise ActBenchMcpError("unknown or expired context_id")
            safe_trace = _json_safe_copy(trace)
            if not isinstance(safe_trace, dict):
                safe_trace = {"value": safe_trace}
            safe_trace.setdefault("sequence", len(context.traces) + 1)
            context.traces.append(safe_trace)
            return _json_safe_copy(safe_trace)

    def get_traces(self, context_id: str) -> list[dict[str, Any]]:
        normalized_id = str(context_id).strip()
        now = time.time()
        with self._lock:
            self._cleanup_locked(now=now)
            context = self._contexts.get(normalized_id)
            if context is None:
                raise ActBenchMcpError("unknown or expired context_id")
            return _json_safe_copy(context.traces)

    def clear(self) -> None:
        with self._lock:
            self._contexts.clear()

    def _cleanup_locked(self, *, now: float) -> None:
        expired = [key for key, value in self._contexts.items() if value.expires_at <= now]
        for key in expired:
            self._contexts.pop(key, None)


REGISTRY = ActBenchMcpRegistry()


def register_context(
    *,
    context_id: str,
    workspace: str | Path,
    api_endpoints: dict[str, Any] | None = None,
    ttl_seconds: float = DEFAULT_CONTEXT_TTL_SECONDS,
) -> ActBenchMcpContext:
    return REGISTRY.register(
        context_id=context_id,
        workspace=workspace,
        api_endpoints=api_endpoints,
        ttl_seconds=ttl_seconds,
    )


def unregister_context(context_id: str) -> bool:
    return REGISTRY.unregister(context_id)


def clear_contexts() -> None:
    REGISTRY.clear()


def get_context_traces(context_id: str) -> list[dict[str, Any]]:
    return REGISTRY.get_traces(context_id)


def _json_safe_copy(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))


def _is_sensitive_trace_key(key: str) -> bool:
    normalized = key.lower().replace("-", "_")
    if normalized in {"context_id", "token", "auth_token", "bearer_token"}:
        return True
    sensitive_fragments = (
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
    return any(fragment in normalized for fragment in sensitive_fragments)


def _redact_mcp_trace_value(value: Any, *, key: str = "") -> Any:
    if key and _is_sensitive_trace_key(key):
        return "[redacted]"
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for item_key, item_value in value.items():
            key_text = str(item_key)
            if key_text.lower().replace("-", "_") == "context_id":
                continue
            redacted[key_text] = _redact_mcp_trace_value(item_value, key=key_text)
        return redacted
    if isinstance(value, list):
        return [_redact_mcp_trace_value(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _resolve_workspace_path(context: ActBenchMcpContext, raw_path: str | None) -> Path:
    path_text = "" if raw_path is None else str(raw_path)
    candidate = Path(path_text)
    if candidate.is_absolute():
        raise ActBenchMcpError("absolute paths are not allowed")
    resolved = (context.workspace / candidate).resolve()
    if not resolved.is_relative_to(context.workspace):
        raise ActBenchMcpError("path escapes workspace")
    return resolved


def _relative_path(context: ActBenchMcpContext, path: Path) -> str:
    relative = path.resolve().relative_to(context.workspace)
    return str(relative).replace(os.sep, "/")


def _is_internal_workspace_path(context: ActBenchMcpContext, path: Path) -> bool:
    resolved = path.resolve()
    return resolved.parent == context.workspace and resolved.name in INTERNAL_WORKSPACE_FILES


def _reject_internal_workspace_path(context: ActBenchMcpContext, path: Path) -> None:
    if _is_internal_workspace_path(context, path):
        raise ActBenchMcpError(
            "api_endpoints.json is managed by ActBench; use actbench_get_api_endpoints"
        )


def actbench_list_files(context_id: str, path: str = "") -> dict[str, Any]:
    context = REGISTRY.get(context_id)
    root = _resolve_workspace_path(context, path)
    if not root.exists():
        raise ActBenchMcpError("path does not exist")
    if not root.is_dir():
        raise ActBenchMcpError("path is not a directory")

    entries: list[dict[str, Any]] = []
    for entry in sorted(root.iterdir(), key=lambda item: item.name):
        resolved = entry.resolve()
        if not resolved.is_relative_to(context.workspace) or _is_internal_workspace_path(context, resolved):
            continue
        item: dict[str, Any] = {
            "path": _relative_path(context, resolved),
            "name": entry.name,
            "type": "directory" if entry.is_dir() else "file",
        }
        if entry.is_file():
            item["size_bytes"] = entry.stat().st_size
        entries.append(item)
    return {"path": _relative_path(context, root) if root != context.workspace else "", "entries": entries}


def actbench_read_file(context_id: str, path: str) -> dict[str, Any]:
    context = REGISTRY.get(context_id)
    file_path = _resolve_workspace_path(context, path)
    _reject_internal_workspace_path(context, file_path)
    if not file_path.is_file():
        raise ActBenchMcpError("path is not a file")
    size = file_path.stat().st_size
    if size > MAX_FILE_BYTES:
        raise ActBenchMcpError(f"file is too large to read ({size} bytes)")
    try:
        content = file_path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ActBenchMcpError("file is not valid UTF-8 text") from exc
    return {"path": _relative_path(context, file_path), "content": content, "size_bytes": size}


def actbench_write_file(context_id: str, path: str, content: str) -> dict[str, Any]:
    if not isinstance(content, str):
        raise ActBenchMcpError("content must be a string")
    encoded = content.encode("utf-8")
    if len(encoded) > MAX_FILE_BYTES:
        raise ActBenchMcpError(f"content is too large to write ({len(encoded)} bytes)")

    context = REGISTRY.get(context_id)
    file_path = _resolve_workspace_path(context, path)
    _reject_internal_workspace_path(context, file_path)
    if file_path.exists() and file_path.is_dir():
        raise ActBenchMcpError("path is a directory")
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content, encoding="utf-8")
    return {"path": _relative_path(context, file_path), "size_bytes": len(encoded)}


def sanitize_api_endpoints(api_endpoints: dict[str, Any]) -> dict[str, Any]:
    services: dict[str, Any] = {}
    for service_name in sorted(api_endpoints):
        spec = SERVICE_SPECS.get(service_name)
        if spec is None:
            continue
        services[service_name] = {"business_paths": list(spec.business_paths)}
    return services


def actbench_get_api_endpoints(context_id: str) -> dict[str, Any]:
    context = REGISTRY.get(context_id)
    return {"services": sanitize_api_endpoints(context.api_endpoints)}


def actbench_call_api(
    context_id: str,
    service: str,
    method: str,
    path: str,
    headers: dict[str, Any] | None = None,
    body: Any = None,
) -> dict[str, Any]:
    context = REGISTRY.get(context_id)
    service_name = str(service).strip()
    spec = SERVICE_SPECS.get(service_name)
    if spec is None or service_name not in context.api_endpoints:
        raise ActBenchMcpError("service is not available for this context")

    request_path = str(path).strip()
    if not request_path.startswith("/") or "?" in request_path or "#" in request_path:
        raise ActBenchMcpError("path must be an exact business path")
    if request_path not in spec.business_paths:
        raise ActBenchMcpError("path is not allowed for this service")

    method_name = str(method or "GET").upper().strip()
    if method_name not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
        raise ActBenchMcpError("method is not allowed")

    endpoint = context.api_endpoints.get(service_name)
    if not isinstance(endpoint, dict) or not isinstance(endpoint.get("base_url"), str):
        raise ActBenchMcpError("service endpoint is missing a base_url")
    url = f"{endpoint['base_url'].rstrip('/')}{request_path}"

    outbound_headers = _sanitize_outbound_headers(headers or {})
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        outbound_headers.setdefault("Content-Type", "application/json")
    elif method_name in {"POST", "PUT", "PATCH"}:
        data = b"{}"
        outbound_headers.setdefault("Content-Type", "application/json")
    outbound_headers.setdefault("Accept", "application/json")

    req = urllib.request.Request(url, data=data, headers=outbound_headers, method=method_name)
    try:
        with urllib.request.urlopen(req, timeout=10.0) as response:
            raw = response.read()
            status_code = int(response.status)
            content_type = response.headers.get("Content-Type", "")
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        status_code = int(exc.code)
        content_type = exc.headers.get("Content-Type", "") if exc.headers else ""
    except (OSError, TimeoutError) as exc:
        raise ActBenchMcpError(f"API request failed: {exc}") from exc

    text = raw.decode("utf-8", errors="replace")
    parsed_body: Any = text
    if "json" in content_type.lower() or text[:1] in ("{", "["):
        try:
            parsed_body = json.loads(text) if text else None
        except json.JSONDecodeError:
            parsed_body = text
    return {"service": service_name, "path": request_path, "status_code": status_code, "body": parsed_body}


def _sanitize_outbound_headers(headers: dict[str, Any]) -> dict[str, str]:
    blocked = {"host", "content-length", "transfer-encoding", "connection"}
    sanitized: dict[str, str] = {}
    for key, value in headers.items():
        normalized = str(key).strip()
        if not normalized or normalized.lower() in blocked:
            continue
        sanitized[normalized] = str(value)
    return sanitized


TOOL_HANDLERS: dict[str, Callable[..., dict[str, Any]]] = {
    "actbench_list_files": actbench_list_files,
    "actbench_read_file": actbench_read_file,
    "actbench_write_file": actbench_write_file,
    "actbench_get_api_endpoints": actbench_get_api_endpoints,
    "actbench_call_api": actbench_call_api,
}


def mcp_tools() -> list[dict[str, Any]]:
    return [
        {
            "name": "actbench_list_files",
            "description": "List files directly under a directory in the current ActBench task workspace. Always pass the task context_id.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "context_id": {"type": "string"},
                    "path": {"type": "string", "default": ""},
                },
                "required": ["context_id"],
            },
        },
        {
            "name": "actbench_read_file",
            "description": "Read a UTF-8 text file from the current ActBench task workspace. Always pass the task context_id.",
            "inputSchema": {
                "type": "object",
                "properties": {"context_id": {"type": "string"}, "path": {"type": "string"}},
                "required": ["context_id", "path"],
            },
        },
        {
            "name": "actbench_write_file",
            "description": "Write a UTF-8 text file inside the current ActBench task workspace. Always pass the task context_id.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "context_id": {"type": "string"},
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["context_id", "path", "content"],
            },
        },
        {
            "name": "actbench_get_api_endpoints",
            "description": "Return sanitized mock API service names and allowed business paths for the current ActBench task. Always pass the task context_id.",
            "inputSchema": {
                "type": "object",
                "properties": {"context_id": {"type": "string"}},
                "required": ["context_id"],
            },
        },
        {
            "name": "actbench_call_api",
            "description": "Call one allowed business path on a mock API service declared by the current ActBench task. Always pass the task context_id and use paths from actbench_get_api_endpoints.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "context_id": {"type": "string"},
                    "service": {"type": "string"},
                    "method": {"type": "string"},
                    "path": {"type": "string"},
                    "headers": {
                        "type": "object",
                        "description": "Optional HTTP headers to forward. Restricted headers are ignored.",
                        "properties": {},
                        "additionalProperties": {"type": "string"},
                        "default": {},
                    },
                    "body": {
                        "type": "object",
                        "description": "Optional JSON request body for the allowed mock API business path.",
                        "properties": {},
                        "additionalProperties": True,
                        "default": {},
                    },
                },
                "required": ["context_id", "service", "method", "path"],
            },
        },
    ]


def dispatch_json_rpc(message: Any) -> dict[str, Any] | list[dict[str, Any]] | None:
    if isinstance(message, list):
        responses = [dispatch_json_rpc(item) for item in message]
        return [item for item in responses if item is not None]
    if not isinstance(message, dict):
        return _json_rpc_error(None, -32600, "Invalid Request")

    request_id = message.get("id")
    method = message.get("method")
    params = message.get("params") or {}
    is_notification = "id" not in message

    try:
        if method == "initialize":
            result = {
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "actbench-mcp-gateway", "version": "0.1.0"},
            }
        elif method == "notifications/initialized":
            return None if is_notification else _json_rpc_result(request_id, {})
        elif method == "tools/list":
            result = {"tools": mcp_tools()}
        elif method == "tools/call":
            result = _dispatch_tool_call(params)
        else:
            return None if is_notification else _json_rpc_error(request_id, -32601, "Method not found")
        return None if is_notification else _json_rpc_result(request_id, result)
    except Exception as exc:  # noqa: BLE001 - JSON-RPC must return structured errors
        return None if is_notification else _json_rpc_error(request_id, -32603, str(exc))


def _dispatch_tool_call(params: Any) -> dict[str, Any]:
    if not isinstance(params, dict):
        return _mcp_tool_error("tools/call params must be an object")
    name = params.get("name")
    arguments = params.get("arguments") or {}
    if not isinstance(name, str):
        return _mcp_tool_error("tool name is required")
    if not isinstance(arguments, dict):
        return _mcp_tool_error("tool arguments must be an object")

    handler = TOOL_HANDLERS.get(name)
    if handler is None:
        result = _mcp_tool_error(f"unknown tool: {name}")
        _maybe_record_tool_trace(name=name, arguments=arguments, result=result)
        return result
    try:
        value = handler(**arguments)
    except Exception as exc:  # noqa: BLE001 - tool errors are returned to the model
        result = _mcp_tool_error(str(exc))
        _maybe_record_tool_trace(name=name, arguments=arguments, result=result)
        return result
    result = _mcp_tool_result(value)
    _maybe_record_tool_trace(name=name, arguments=arguments, result=result)
    return result


def _maybe_record_tool_trace(*, name: str, arguments: dict[str, Any], result: dict[str, Any]) -> None:
    context_id = arguments.get("context_id")
    if not isinstance(context_id, str) or not context_id.strip():
        return
    trace = {
        "timestamp": time.time(),
        "name": name,
        "arguments": _redact_mcp_trace_value(arguments),
        "result": _redact_mcp_trace_value(result),
        "isError": bool(result.get("isError")),
    }
    try:
        REGISTRY.record_trace(context_id, trace)
    except ActBenchMcpError:
        return


def _mcp_tool_result(value: Any) -> dict[str, Any]:
    return {
        "content": [
            {"type": "text", "text": json.dumps(value, ensure_ascii=False, sort_keys=True)}
        ],
        "isError": False,
    }


def _mcp_tool_error(message: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": message}], "isError": True}


def _json_rpc_result(request_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": JSON_RPC_VERSION, "id": request_id, "result": result}


def _json_rpc_error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {
        "jsonrpc": JSON_RPC_VERSION,
        "id": request_id,
        "error": {"code": code, "message": message},
    }


def create_app() -> FastAPI:
    app = FastAPI(title="ActBench MCP Gateway")

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return {"status": "ok"}

    @app.post("/mcp")
    async def mcp_endpoint(request: Request) -> Response:
        payload = await request.json()
        response = dispatch_json_rpc(payload)
        if response is None:
            return Response(status_code=202)
        return JSONResponse(response)

    @app.post("/admin/contexts")
    async def admin_register_context(request: Request) -> JSONResponse:
        _require_admin_token(request)
        payload = await request.json()
        if not isinstance(payload, dict):
            raise HTTPException(status_code=400, detail="context payload must be an object")
        try:
            context = register_context(
                context_id=str(payload.get("context_id", "")),
                workspace=payload.get("workspace", ""),
                api_endpoints=payload.get("api_endpoints"),
                ttl_seconds=payload.get("ttl_seconds", DEFAULT_CONTEXT_TTL_SECONDS),
            )
        except ActBenchMcpError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return JSONResponse(
            {
                "status": "ok",
                "context_id": context.context_id,
                "expires_at": context.expires_at,
            }
        )

    @app.delete("/admin/contexts/{context_id}")
    async def admin_unregister_context(context_id: str, request: Request) -> JSONResponse:
        _require_admin_token(request)
        removed = unregister_context(context_id)
        return JSONResponse({"status": "ok", "removed": removed})

    @app.get("/admin/contexts/{context_id}/traces")
    async def admin_context_traces(context_id: str, request: Request) -> JSONResponse:
        _require_admin_token(request)
        try:
            traces = get_context_traces(context_id)
        except ActBenchMcpError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return JSONResponse({"status": "ok", "context_id": context_id, "traces": traces})

    return app


app = create_app()


def _require_admin_token(request: Request) -> None:
    expected = os.environ.get(ADMIN_TOKEN_ENV, "")
    if not expected:
        return
    authorization = request.headers.get("authorization", "")
    bearer = authorization.removeprefix("Bearer ").strip() if authorization else ""
    explicit = request.headers.get("x-actbench-mcp-admin-token", "").strip()
    if bearer != expected and explicit != expected:
        raise HTTPException(status_code=401, detail="invalid admin token")


def start_gateway_subprocess(
    *,
    host: str = DEFAULT_MCP_HOST,
    port: int = DEFAULT_MCP_PORT,
    admin_token: str | None = None,
    timeout_seconds: float = 10.0,
) -> ActBenchMcpGatewayProcess:
    env = os.environ.copy()
    if admin_token:
        env[ADMIN_TOKEN_ENV] = admin_token
    command = [sys.executable, str(Path(__file__).resolve()), "--host", host, "--port", str(port)]
    process = subprocess.Popen(
        command,
        cwd=str(Path(__file__).resolve().parents[1]),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    handle = ActBenchMcpGatewayProcess(
        process=process,
        host=host,
        port=port,
        mcp_url=f"http://{host}:{port}/mcp",
        admin_token=admin_token,
    )
    try:
        check_gateway_health(host=host, port=port, timeout_seconds=timeout_seconds)
    except Exception:
        stop_gateway_process(handle)
        raise
    return handle


def check_gateway_health(
    *,
    host: str = DEFAULT_MCP_HOST,
    port: int = DEFAULT_MCP_PORT,
    timeout_seconds: float = 10.0,
) -> None:
    deadline = time.time() + timeout_seconds
    url = f"http://{host}:{port}/health"
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            _client_request_json(url, method="GET", timeout_seconds=1.0)
            return
        except Exception as exc:  # noqa: BLE001 - retry until deadline
            last_error = exc
            time.sleep(0.2)
    raise ActBenchMcpError(f"MCP gateway health check timed out at {url}: {last_error}")


def register_gateway_context(
    *,
    mcp_url: str,
    context_id: str,
    workspace: str | Path,
    api_endpoints: dict[str, Any] | None = None,
    ttl_seconds: float = DEFAULT_CONTEXT_TTL_SECONDS,
    admin_token: str | None = None,
) -> dict[str, Any]:
    payload = {
        "context_id": context_id,
        "workspace": str(workspace),
        "api_endpoints": api_endpoints or {},
        "ttl_seconds": ttl_seconds,
    }
    return _client_request_json(
        _admin_contexts_url(mcp_url),
        method="POST",
        payload=payload,
        admin_token=admin_token,
    )


def unregister_gateway_context(
    *,
    mcp_url: str,
    context_id: str,
    admin_token: str | None = None,
) -> dict[str, Any]:
    encoded_context = urllib.parse.quote(context_id, safe="")
    return _client_request_json(
        f"{_admin_contexts_url(mcp_url).rstrip('/')}/{encoded_context}",
        method="DELETE",
        admin_token=admin_token,
    )


def get_gateway_context_traces(
    *,
    mcp_url: str,
    context_id: str,
    admin_token: str | None = None,
) -> dict[str, Any]:
    encoded_context = urllib.parse.quote(context_id, safe="")
    return _client_request_json(
        f"{_admin_contexts_url(mcp_url).rstrip('/')}/{encoded_context}/traces",
        method="GET",
        admin_token=admin_token,
    )


def stop_gateway_process(handle: ActBenchMcpGatewayProcess | None) -> None:
    if handle is None or handle.process is None:
        return
    process = handle.process
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=3.0)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=3.0)


def _admin_contexts_url(mcp_url: str) -> str:
    parsed = urllib.parse.urlparse(mcp_url)
    return urllib.parse.urlunparse((parsed.scheme, parsed.netloc, "/admin/contexts", "", "", ""))


def _client_request_json(
    url: str,
    *,
    method: str,
    timeout_seconds: float = 5.0,
    payload: dict[str, Any] | None = None,
    admin_token: str | None = None,
) -> dict[str, Any]:
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if admin_token:
        headers["Authorization"] = f"Bearer {admin_token}"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout_seconds) as response:
            text = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise ActBenchMcpError(f"HTTP {exc.code}: {body}") from exc
    except (OSError, TimeoutError) as exc:
        raise ActBenchMcpError(str(exc)) from exc
    if not text:
        return {}
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise ActBenchMcpError("unexpected JSON response type")
    return parsed


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the ActBench MCP gateway")
    parser.add_argument("--host", default=DEFAULT_MCP_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_MCP_PORT)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    import uvicorn

    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
