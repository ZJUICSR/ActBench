from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
for path in (ROOT, SCRIPTS_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from lib_api_services import start_api_services  # noqa: E402
import lib_mcp_gateway as mcp_gateway_module  # noqa: E402
from lib_mcp_gateway import (  # noqa: E402
    ActBenchMcpError,
    actbench_call_api,
    actbench_get_api_endpoints,
    actbench_list_files,
    actbench_read_file,
    actbench_write_file,
    clear_contexts,
    dispatch_json_rpc,
    get_context_traces,
    get_gateway_context_traces,
    mcp_tools,
    register_context,
    unregister_context,
)


@pytest.fixture(autouse=True)
def _clear_mcp_contexts() -> None:
    clear_contexts()
    yield
    clear_contexts()


def _rpc_tool_result(response: dict) -> dict:
    result = response["result"]
    assert result["isError"] is False
    return json.loads(result["content"][0]["text"])


def _rpc_tool_error(response: dict) -> str:
    result = response["result"]
    assert result["isError"] is True
    return result["content"][0]["text"]


def _call_tool(name: str, arguments: dict) -> dict:
    response = dispatch_json_rpc(
        {
            "jsonrpc": "2.0",
            "id": "call-1",
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        }
    )
    assert isinstance(response, dict)
    return response


def test_json_rpc_initialize_and_tools_list_shapes() -> None:
    initialized = dispatch_json_rpc(
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
    )
    assert isinstance(initialized, dict)
    assert initialized["jsonrpc"] == "2.0"
    assert initialized["id"] == 1
    assert initialized["result"]["capabilities"] == {"tools": {}}

    listed = dispatch_json_rpc({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    assert isinstance(listed, dict)
    tool_names = {tool["name"] for tool in listed["result"]["tools"]}
    assert tool_names == {
        "actbench_list_files",
        "actbench_read_file",
        "actbench_write_file",
        "actbench_get_api_endpoints",
        "actbench_call_api",
    }


def test_mcp_tool_input_property_schemas_are_explicit() -> None:
    for tool in mcp_tools():
        schema = tool["inputSchema"]
        assert schema["type"] == "object"
        properties = schema.get("properties", {})
        assert isinstance(properties, dict)
        for property_name, property_schema in properties.items():
            assert property_schema != {}, f"{tool['name']}.{property_name} has empty schema"


def test_call_api_body_schema_is_provider_compatible() -> None:
    tools = {tool["name"]: tool for tool in mcp_tools()}
    body_schema = tools["actbench_call_api"]["inputSchema"]["properties"]["body"]

    assert body_schema != {}
    assert body_schema["type"] == "object"
    assert body_schema["default"] == {}
    assert body_schema["additionalProperties"] is True


def test_context_registration_unregisters_and_invalidates_tools(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "README.md").write_text("hello", encoding="utf-8")

    register_context(context_id="ctx", workspace=workspace, ttl_seconds=30)
    listed = actbench_list_files("ctx")
    assert listed["entries"][0]["path"] == "README.md"

    assert unregister_context("ctx") is True
    with pytest.raises(ActBenchMcpError, match="unknown or expired"):
        actbench_list_files("ctx")


def test_workspace_file_tools_and_json_rpc_call(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    (workspace / "nested").mkdir(parents=True)
    (workspace / "nested" / "input.txt").write_text("input", encoding="utf-8")
    register_context(context_id="ctx", workspace=workspace, ttl_seconds=30)

    listed = actbench_list_files("ctx", "nested")
    assert listed["entries"] == [
        {"path": "nested/input.txt", "name": "input.txt", "type": "file", "size_bytes": 5}
    ]
    assert actbench_read_file("ctx", "nested/input.txt")["content"] == "input"
    written = actbench_write_file("ctx", "nested/output.txt", "done")
    assert written == {"path": "nested/output.txt", "size_bytes": 4}
    assert (workspace / "nested" / "output.txt").read_text(encoding="utf-8") == "done"

    response = _call_tool("actbench_read_file", {"context_id": "ctx", "path": "nested/output.txt"})
    assert _rpc_tool_result(response)["content"] == "done"


def test_json_rpc_tool_calls_are_recorded_as_redacted_traces(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "README.md").write_text("hello", encoding="utf-8")
    register_context(context_id="ctx-secret", workspace=workspace, ttl_seconds=30)

    response = _call_tool(
        "actbench_read_file",
        {
            "context_id": "ctx-secret",
            "path": "README.md",
        },
    )

    assert _rpc_tool_result(response)["content"] == "hello"
    traces = get_context_traces("ctx-secret")
    assert len(traces) == 1
    trace = traces[0]
    assert trace["sequence"] == 1
    assert trace["name"] == "actbench_read_file"
    assert trace["arguments"]["path"] == "README.md"
    assert "context_id" not in trace["arguments"]
    assert trace["isError"] is False
    assert trace["result"]["isError"] is False
    assert "hello" in trace["result"]["content"][0]["text"]
    assert "ctx-secret" not in json.dumps(trace, sort_keys=True)


def test_json_rpc_tool_errors_are_recorded_as_traces(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    register_context(context_id="ctx", workspace=workspace, ttl_seconds=30)

    missing = _call_tool("actbench_read_file", {"context_id": "ctx", "path": "missing.txt"})
    unknown = _call_tool(
        "missing_tool",
        {
            "context_id": "ctx",
            "headers": {"Authorization": "Bearer should-not-leak"},
            "api_key": "also-secret",
        },
    )

    assert "path is not a file" in _rpc_tool_error(missing)
    assert "unknown tool" in _rpc_tool_error(unknown)
    traces = get_context_traces("ctx")
    assert [trace["name"] for trace in traces] == ["actbench_read_file", "missing_tool"]
    assert all(trace["isError"] is True for trace in traces)
    assert "path is not a file" in traces[0]["result"]["content"][0]["text"]
    assert "unknown tool" in traces[1]["result"]["content"][0]["text"]
    assert traces[1]["arguments"]["headers"]["Authorization"] == "[redacted]"
    assert traces[1]["arguments"]["api_key"] == "[redacted]"
    assert "should-not-leak" not in json.dumps(traces[1], sort_keys=True)
    assert "also-secret" not in json.dumps(traces[1], sort_keys=True)


def test_get_gateway_context_traces_client_helper_quotes_context_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict] = []

    def fake_client_request_json(url: str, **kwargs: object) -> dict:
        calls.append({"url": url, **kwargs})
        return {"status": "ok", "traces": []}

    monkeypatch.setattr(mcp_gateway_module, "_client_request_json", fake_client_request_json)

    result = get_gateway_context_traces(
        mcp_url="http://127.0.0.1:8765/mcp",
        context_id="ctx/with space",
        admin_token="admin-secret",
    )

    assert result == {"status": "ok", "traces": []}
    assert calls == [
        {
            "url": "http://127.0.0.1:8765/admin/contexts/ctx%2Fwith%20space/traces",
            "method": "GET",
            "admin_token": "admin-secret",
        }
    ]


def test_workspace_file_tools_reject_absolute_and_parent_escape(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    register_context(context_id="ctx", workspace=workspace, ttl_seconds=30)

    with pytest.raises(ActBenchMcpError, match="absolute"):
        actbench_read_file("ctx", str(tmp_path / "outside.txt"))
    with pytest.raises(ActBenchMcpError, match="escapes"):
        actbench_write_file("ctx", "../outside.txt", "bad")

    response = _call_tool("actbench_read_file", {"context_id": "ctx", "path": "../outside.txt"})
    assert "escapes" in _rpc_tool_error(response)
    assert not (tmp_path / "outside.txt").exists()


def test_sanitized_api_endpoint_discovery_hides_internal_urls_and_admin_paths(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    group = start_api_services(
        services=["mailbox"],
        run_id="test_run",
        attempt_id="mcp_sanitize",
        workspace=workspace,
    )
    assert group is not None
    try:
        register_context(
            context_id="ctx",
            workspace=workspace,
            api_endpoints=group.endpoints,
            ttl_seconds=30,
        )
        sanitized = actbench_get_api_endpoints("ctx")
        assert sanitized == {
            "services": {
                "mailbox": {
                    "business_paths": [
                        "/mailbox/messages",
                        "/mailbox/messages/get",
                        "/mailbox/messages/send",
                        "/mailbox/drafts/save",
                    ]
                }
            }
        }
        serialized = json.dumps(sanitized)
        assert "127.0.0.1" not in serialized
        assert "audit" not in serialized
        assert "reset" not in serialized
        assert "health" not in serialized
        assert "log" not in serialized
        assert "fixture" not in serialized.lower()
        assert "api_endpoints.json" not in {
            entry["path"] for entry in actbench_list_files("ctx")["entries"]
        }
        with pytest.raises(ActBenchMcpError, match="actbench_get_api_endpoints"):
            actbench_read_file("ctx", "api_endpoints.json")
    finally:
        group.stop()


def test_call_api_allows_only_declared_mock_service_business_paths(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    group = start_api_services(
        services=["mailbox"],
        run_id="test_run",
        attempt_id="mcp_call_api",
        workspace=workspace,
    )
    assert group is not None
    try:
        register_context(
            context_id="ctx",
            workspace=workspace,
            api_endpoints=group.endpoints,
            ttl_seconds=30,
        )
        result = actbench_call_api(
            "ctx",
            "mailbox",
            "POST",
            "/mailbox/messages/send",
            body={"to": "maya.chen@company.example", "subject": "MCP", "body": "hello"},
        )
        assert result["status_code"] == 200
        assert result["body"]["status"] == "sent"
        audit = group.collect_audit()["mailbox"]
        assert audit["sent"][0]["subject"] == "MCP"

        for blocked_path in ("/mailbox/audit", "/mailbox/reset", "/mailbox/health"):
            with pytest.raises(ActBenchMcpError, match="not allowed"):
                actbench_call_api("ctx", "mailbox", "POST", blocked_path, body={})
        with pytest.raises(ActBenchMcpError, match="not available"):
            actbench_call_api("ctx", "taskboard", "POST", "/taskboard/tasks", body={})
        with pytest.raises(ActBenchMcpError, match="exact business path"):
            actbench_call_api("ctx", "mailbox", "POST", "/mailbox/messages?x=1", body={})
    finally:
        group.stop()
