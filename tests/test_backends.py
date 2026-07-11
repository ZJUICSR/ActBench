from __future__ import annotations

import json
import subprocess
import sys
from argparse import Namespace
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from benchmark.backends.base import BackendInitializationError, BackendRunContext  # noqa: E402
from benchmark.backends.fake import FakeBackend  # noqa: E402
from benchmark.backends.openclaw import OpenClawBackend  # noqa: E402
from benchmark.backends.registry import available_backend_names, get_backend  # noqa: E402
from benchmark.cli import _parse_args  # noqa: E402
from benchmark.runner import run_benchmark  # noqa: E402
from lib_tasks import Task  # noqa: E402


@pytest.fixture(autouse=True)
def _cleanup_cli_logs():
    yield
    for name in ("actbench.log", "benchmark.log"):
        (ROOT / name).unlink(missing_ok=True)


def _task(frontmatter: dict | None = None) -> Task:
    return Task(
        task_id="task_fake",
        name="Fake task",
        category="",
        grading_type="automated",
        timeout_seconds=30,
        workspace_files=[{"path": "README.md", "content": "hello"}],
        prompt="Say hello.",
        expected_behavior="",
        grading_criteria=[],
        frontmatter=frontmatter or {},
    )


def _context(tmp_path: Path, backend: str = "fake") -> BackendRunContext:
    return BackendRunContext(
        backend=backend,
        model="test/model",
        run_id="run_001",
        run_root=tmp_path / "run_root",
        skill_dir=ROOT,
        agent_id="bench-test-model",
        agent_workspace=tmp_path / "agent_workspace",
        timeout_multiplier=1.0,
        verbose=False,
    )


def _configure_hermes_test_env(
    monkeypatch: pytest.MonkeyPatch,
    *,
    mcp_enabled: bool = False,
) -> None:
    monkeypatch.setenv("ACTBENCH_HERMES_BIN", "hermes")
    monkeypatch.setenv("ACTBENCH_HERMES_PROVIDER", "test-provider")
    monkeypatch.setenv("ACTBENCH_HERMES_ENABLE_ACTBENCH_MCP", "1" if mcp_enabled else "0")
    monkeypatch.delenv("ACTBENCH_HERMES_MODEL", raising=False)
    monkeypatch.delenv("ACTBENCH_HERMES_TOOLSETS", raising=False)
    monkeypatch.delenv("ACTBENCH_HERMES_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("ACTBENCH_HERMES_HOME_ROOT", raising=False)
    monkeypatch.delenv("ACTBENCH_MCP_ADMIN_TOKEN", raising=False)
    monkeypatch.delenv("ACTBENCH_MCP_URL", raising=False)
    monkeypatch.delenv("ACTBENCH_MCP_HOST", raising=False)
    monkeypatch.delenv("ACTBENCH_MCP_PORT", raising=False)
    monkeypatch.delenv("ACTBENCH_MCP_AUTOSTART", raising=False)


def _configure_opencode_test_env(
    monkeypatch: pytest.MonkeyPatch,
    *,
    mcp_enabled: bool = False,
) -> None:
    monkeypatch.setenv("ACTBENCH_OPENCODE_BIN", "opencode")
    monkeypatch.setenv("ACTBENCH_OPENCODE_ENABLE_ACTBENCH_MCP", "1" if mcp_enabled else "0")
    monkeypatch.delenv("ACTBENCH_OPENCODE_MODEL", raising=False)
    monkeypatch.delenv("ACTBENCH_OPENCODE_AGENT", raising=False)
    monkeypatch.delenv("ACTBENCH_OPENCODE_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("ACTBENCH_OPENCODE_HOME_ROOT", raising=False)
    monkeypatch.delenv("ACTBENCH_OPENCODE_AUTO", raising=False)
    monkeypatch.delenv("ACTBENCH_MCP_ADMIN_TOKEN", raising=False)
    monkeypatch.delenv("ACTBENCH_MCP_URL", raising=False)
    monkeypatch.delenv("ACTBENCH_MCP_HOST", raising=False)
    monkeypatch.delenv("ACTBENCH_MCP_PORT", raising=False)
    monkeypatch.delenv("ACTBENCH_MCP_AUTOSTART", raising=False)


def _configure_claudecode_test_env(
    monkeypatch: pytest.MonkeyPatch,
    *,
    mcp_enabled: bool = False,
) -> None:
    monkeypatch.setenv("ACTBENCH_CLAUDECODE_BIN", "claude")
    monkeypatch.setenv("ACTBENCH_CLAUDECODE_ENABLE_ACTBENCH_MCP", "1" if mcp_enabled else "0")
    monkeypatch.delenv("ACTBENCH_CLAUDECODE_MODEL", raising=False)
    monkeypatch.delenv("ACTBENCH_CLAUDECODE_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("ACTBENCH_CLAUDECODE_HOME_ROOT", raising=False)
    monkeypatch.delenv("ACTBENCH_CLAUDECODE_PERMISSION_MODE", raising=False)
    monkeypatch.delenv("ACTBENCH_MCP_ADMIN_TOKEN", raising=False)
    monkeypatch.delenv("ACTBENCH_MCP_URL", raising=False)
    monkeypatch.delenv("ACTBENCH_MCP_HOST", raising=False)
    monkeypatch.delenv("ACTBENCH_MCP_PORT", raising=False)
    monkeypatch.delenv("ACTBENCH_MCP_AUTOSTART", raising=False)


def _configure_qwenpaw_test_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ACTBENCH_QWENPAW_BASE_URL", "http://qwenpaw.test")
    monkeypatch.delenv("ACTBENCH_QWENPAW_API_KEY", raising=False)
    monkeypatch.delenv("ACTBENCH_QWENPAW_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("ACTBENCH_QWENPAW_AGENT_PREFIX", raising=False)
    monkeypatch.delenv("ACTBENCH_QWENPAW_DELETE_AGENT", raising=False)
    monkeypatch.delenv("ACTBENCH_QWENPAW_HEADLESS_TOOL_GUARD", raising=False)


def _write_minimal_task(tasks_dir: Path) -> None:
    task_dir = tasks_dir / "task_fake"
    (task_dir / "workspace").mkdir(parents=True)
    (task_dir / "workspace" / "README.md").write_text("hello", encoding="utf-8")
    (task_dir / "task.yaml").write_text(
        yaml.safe_dump(
            {
                "id": "task_fake",
                "name": "Fake task",
                "prompt": "Say hello.",
                "workspace_dir": "workspace",
            }
        ),
        encoding="utf-8",
    )


def test_cli_default_backend_is_openclaw(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["actbench"])

    args = _parse_args()

    assert args.backend == "openclaw"
    assert args.model == "deepseek/deepseek-v4-pro"


def test_cli_accepts_qwenpaw_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["actbench", "--backend", "qwenpaw", "--model", "qwen/test"])

    args = _parse_args()

    assert args.backend == "qwenpaw"
    assert args.model == "qwen/test"


def test_cli_accepts_openagent_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["actbench", "--backend", "openagent", "--model", "oa/test"])

    args = _parse_args()

    assert args.backend == "openagent"
    assert args.model == "oa/test"


def test_cli_accepts_hermes_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["actbench", "--backend", "hermes", "--model", "hermes/test"])

    args = _parse_args()

    assert args.backend == "hermes"
    assert args.model == "hermes/test"


def test_cli_accepts_opencode_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["actbench", "--backend", "opencode", "--model", "opencode/test"])

    args = _parse_args()

    assert args.backend == "opencode"
    assert args.model == "opencode/test"


def test_cli_accepts_claudecode_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["actbench", "--backend", "claudecode", "--model", "claude/test"])

    args = _parse_args()

    assert args.backend == "claudecode"
    assert args.model == "claude/test"


def test_registry_resolves_backends_without_eager_optional_imports() -> None:
    assert available_backend_names() == (
        "openclaw",
        "qwenpaw",
        "openagent",
        "hermes",
        "opencode",
        "claudecode",
        "fake",
    )
    assert get_backend("openclaw").name == "openclaw"
    assert get_backend("fake").name == "fake"
    assert get_backend("qwenpaw").name == "qwenpaw"
    assert get_backend("openagent").name == "openagent"
    assert get_backend("hermes").name == "hermes"
    assert get_backend("opencode").name == "opencode"
    assert get_backend("claudecode").name == "claudecode"
    with pytest.raises(ValueError, match="unknown backend"):
        get_backend("missing")


def test_openclaw_backend_delegates_to_existing_helpers(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import benchmark.backends.openclaw as openclaw_module

    calls: list[tuple[str, object]] = []

    monkeypatch.setattr(
        openclaw_module,
        "ensure_agent_exists",
        lambda agent_id, model, workspace: calls.append(("ensure", (agent_id, model, workspace))),
    )
    monkeypatch.setattr(
        openclaw_module,
        "cleanup_agent_sessions",
        lambda agent_id: calls.append(("cleanup", agent_id)),
    )
    monkeypatch.setattr(
        openclaw_module,
        "execute_openclaw_task",
        lambda **kwargs: {
            "agent_id": kwargs["agent_id"],
            "task_id": kwargs["task"].task_id,
            "status": "success",
            "transcript": [],
            "usage": {},
            "workspace": "",
            "exit_code": 0,
            "timed_out": False,
            "execution_time": 0.0,
            "stdout": "",
            "stderr": "",
            "api_audit": {},
            "api_endpoints": {},
        },
    )

    backend = OpenClawBackend()
    context = _context(tmp_path, backend="openclaw")

    backend.initialize_run(context)
    result = backend.execute_task(task=_task(), context=context, attempt_run_id="run_001-1")

    assert calls == [
        ("ensure", (context.agent_id, context.model, context.agent_workspace)),
        ("cleanup", context.agent_id),
    ]
    assert result["backend"] == "openclaw"
    assert result["backend_metadata"]["agent_id"] == context.agent_id


def test_fake_backend_returns_backend_compatible_result(tmp_path: Path) -> None:
    task = _task(frontmatter={"sessions": ["first", {"prompt": "second"}]})
    backend = FakeBackend()
    context = _context(tmp_path)

    backend.initialize_run(context)
    result = backend.execute_task(task=task, context=context, attempt_run_id="run_001-1")

    assert result["status"] == "success"
    assert result["backend"] == "fake"
    assert result["usage"]["request_count"] == 2
    assert len(result["transcript"]) == 4
    assert (Path(result["workspace"]) / "README.md").read_text(encoding="utf-8") == "hello"


def test_qwenpaw_backend_health_failure_is_controlled(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import benchmark.backends.qwenpaw as qwenpaw_module
    from benchmark.backends.qwenpaw import QwenPawBackend, QwenPawRequestError

    _configure_qwenpaw_test_env(monkeypatch)

    def fake_request_json(*args, **kwargs):
        raise QwenPawRequestError("connection refused")

    monkeypatch.setattr(qwenpaw_module, "_request_json", fake_request_json)
    backend = QwenPawBackend()
    context = _context(tmp_path, backend="qwenpaw")

    with pytest.raises(BackendInitializationError, match="ACTBENCH_QWENPAW_BASE_URL"):
        backend.initialize_run(context)


def test_qwenpaw_backend_service_success_returns_backend_compatible_result(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from benchmark.backends.qwenpaw import QwenPawBackend

    _configure_qwenpaw_test_env(monkeypatch)
    backend = QwenPawBackend()
    monkeypatch.setattr(backend, "_check_health", lambda config: None)
    create_calls: list[dict] = []
    process_calls: list[dict] = []
    delete_calls: list[str] = []

    def fake_create(**kwargs):
        create_calls.append(kwargs)
        return "actbench-test-agent"

    def fake_process(**kwargs):
        process_calls.append(kwargs)
        return {
            "output": [{"content": [{"type": "text", "text": f"answer:{kwargs['prompt']}"}]}],
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "total_tokens": 15,
                "cost": 0.125,
                "request_count": 2,
            },
        }

    def fake_history(**kwargs):
        return [
            {"role": "user", "content": "first"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "function": {
                            "name": "read_file",
                            "arguments": '{"path": "README.md"}',
                        },
                    }
                ],
            },
        ]

    def fake_delete(**kwargs):
        delete_calls.append(kwargs["agent_id"])

    monkeypatch.setattr(backend, "_create_task_agent", fake_create)
    monkeypatch.setattr(backend, "_post_agent_process", fake_process)
    monkeypatch.setattr(backend, "_fetch_chat_history_messages", fake_history)
    monkeypatch.setattr(backend, "_delete_task_agent", fake_delete)
    context = _context(tmp_path, backend="qwenpaw")
    task = _task(frontmatter={"sessions": ["first", {"prompt": "second"}]})

    backend.initialize_run(context)
    result = backend.execute_task(task=task, context=context, attempt_run_id="run_001-1")

    assert result["status"] == "success"
    assert result["backend"] == "qwenpaw"
    assert result["backend_metadata"]["transcript_source"] == "qwenpaw_service_chat_history"
    assert result["backend_metadata"]["base_url"] == "http://qwenpaw.test"
    assert result["backend_metadata"]["service_agent_id"] == "actbench-test-agent"
    assert result["usage"]["input_tokens"] == 10
    assert result["usage"]["output_tokens"] == 5
    assert result["usage"]["total_tokens"] == 15
    assert result["usage"]["cost_usd"] == 0.125
    assert result["usage"]["request_count"] == 2
    assert result["transcript"][1]["message"]["content"][0]["type"] == "toolCall"
    assert [call["prompt"] for call in process_calls] == ["first", "second"]
    assert len({call["session_id"] for call in process_calls}) == 1
    assert all(call["agent_id"] == "actbench-test-agent" for call in process_calls)
    workspace = Path(result["workspace"])
    assert create_calls[0]["workspace"] == workspace
    assert (workspace / "README.md").read_text(encoding="utf-8") == "hello"
    assert (workspace / ".bootstrap_completed").exists()
    assert not (workspace / "BOOTSTRAP.md").exists()
    assert delete_calls == ["actbench-test-agent"]


def test_qwenpaw_backend_create_agent_payload_uses_workspace_and_model(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import benchmark.backends.qwenpaw as qwenpaw_module
    from benchmark.backends.qwenpaw import QwenPawBackend, QwenPawConfig

    captured: dict[str, object] = {}

    def fake_request_json(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return {"id": "returned-agent"}

    monkeypatch.setattr(qwenpaw_module, "_request_json", fake_request_json)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "skill.json").write_text(
        json.dumps(
            {
                "skills": {
                    "mock_api": {"enabled": True},
                    "disabled_skill": {"enabled": False},
                }
            }
        ),
        encoding="utf-8",
    )
    backend = QwenPawBackend()
    config = QwenPawConfig(
        base_url="http://qwenpaw.test",
        api_key="token",
        timeout_seconds=None,
        agent_prefix="actbench.test",
        delete_agent=True,
        headless_tool_guard=None,
    )
    context = _context(tmp_path, backend="qwenpaw")

    agent_id = backend._create_task_agent(
        config=config,
        context=context,
        task=_task(),
        attempt_run_id="run.001-1",
        session_id="task_fake_123",
        workspace=workspace,
        timeout_seconds=1.0,
    )

    payload = captured["payload"]
    assert agent_id == "returned-agent"
    assert captured["url"] == "http://qwenpaw.test/api/agents"
    assert captured["method"] == "POST"
    assert captured["api_key"] == "token"
    assert isinstance(payload, dict)
    assert payload["workspace_dir"] == str(workspace)
    assert payload["skill_names"] == ["mock_api"]
    assert payload["active_model"] == {"provider_id": "test", "model": "model"}
    assert "." not in payload["id"]
    assert 2 <= len(payload["id"]) <= 64
    assert payload["id"][0].isalnum()
    assert payload["id"][-1].isalnum()


def test_qwenpaw_backend_request_failure_returns_error_result(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from benchmark.backends.qwenpaw import QwenPawBackend, QwenPawRequestError

    _configure_qwenpaw_test_env(monkeypatch)
    backend = QwenPawBackend()
    monkeypatch.setattr(backend, "_check_health", lambda config: None)
    monkeypatch.setattr(backend, "_create_task_agent", lambda **kwargs: "actbench-test-agent")
    monkeypatch.setattr(
        backend,
        "_post_agent_process",
        lambda **kwargs: (_ for _ in ()).throw(QwenPawRequestError("service boom")),
    )
    monkeypatch.setattr(backend, "_delete_task_agent", lambda **kwargs: None)
    context = _context(tmp_path, backend="qwenpaw")

    backend.initialize_run(context)
    result = backend.execute_task(task=_task(), context=context, attempt_run_id="run_001-1")

    assert result["status"] == "error"
    assert result["backend"] == "qwenpaw"
    assert result["exit_code"] == -1
    assert "service boom" in result["stderr"]


def test_qwenpaw_backend_timeout_returns_timeout_result(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from benchmark.backends.qwenpaw import QwenPawBackend, QwenPawTimeoutError

    _configure_qwenpaw_test_env(monkeypatch)
    backend = QwenPawBackend()
    monkeypatch.setattr(backend, "_check_health", lambda config: None)
    monkeypatch.setattr(backend, "_create_task_agent", lambda **kwargs: "actbench-test-agent")
    monkeypatch.setattr(
        backend,
        "_post_agent_process",
        lambda **kwargs: (_ for _ in ()).throw(QwenPawTimeoutError("timed out")),
    )
    monkeypatch.setattr(backend, "_delete_task_agent", lambda **kwargs: None)
    context = _context(tmp_path, backend="qwenpaw")

    backend.initialize_run(context)
    result = backend.execute_task(task=_task(), context=context, attempt_run_id="run_001-1")

    assert result["status"] == "timeout"
    assert result["timed_out"] is True
    assert result["exit_code"] == -1
    assert result["backend_metadata"]["transcript_source"] == "qwenpaw_service_no_transcript"
    assert "timed out" in result["stderr"]


def test_qwenpaw_backend_falls_back_when_history_fetch_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from benchmark.backends.qwenpaw import QwenPawBackend, QwenPawRequestError

    _configure_qwenpaw_test_env(monkeypatch)
    backend = QwenPawBackend()
    monkeypatch.setattr(backend, "_check_health", lambda config: None)
    monkeypatch.setattr(backend, "_create_task_agent", lambda **kwargs: "actbench-test-agent")
    monkeypatch.setattr(
        backend,
        "_post_agent_process",
        lambda **kwargs: {"output": [{"content": [{"type": "text", "text": "fallback answer"}]}]},
    )
    monkeypatch.setattr(
        backend,
        "_fetch_chat_history_messages",
        lambda **kwargs: (_ for _ in ()).throw(QwenPawRequestError("history unavailable")),
    )
    monkeypatch.setattr(backend, "_delete_task_agent", lambda **kwargs: None)
    context = _context(tmp_path, backend="qwenpaw")

    backend.initialize_run(context)
    result = backend.execute_task(task=_task(), context=context, attempt_run_id="run_001-1")

    assert result["status"] == "success"
    assert result["backend_metadata"]["transcript_source"] == "qwenpaw_service_process_fallback"
    assert result["transcript"][0]["message"]["role"] == "user"
    assert result["transcript"][1]["message"]["content"] == [
        {"type": "text", "text": "fallback answer"}
    ]


def test_qwenpaw_backend_respects_delete_agent_flag(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from benchmark.backends.qwenpaw import QwenPawBackend

    _configure_qwenpaw_test_env(monkeypatch)
    monkeypatch.setenv("ACTBENCH_QWENPAW_DELETE_AGENT", "0")
    backend = QwenPawBackend()
    delete_calls: list[str] = []
    monkeypatch.setattr(backend, "_check_health", lambda config: None)
    monkeypatch.setattr(backend, "_create_task_agent", lambda **kwargs: "actbench-test-agent")
    monkeypatch.setattr(
        backend,
        "_post_agent_process",
        lambda **kwargs: {"output": [{"content": [{"type": "text", "text": "done"}]}]},
    )
    monkeypatch.setattr(
        backend,
        "_fetch_chat_history_messages",
        lambda **kwargs: [{"role": "assistant", "content": "done"}],
    )
    monkeypatch.setattr(backend, "_delete_task_agent", lambda **kwargs: delete_calls.append(kwargs["agent_id"]))
    context = _context(tmp_path, backend="qwenpaw")

    backend.initialize_run(context)
    result = backend.execute_task(task=_task(), context=context, attempt_run_id="run_001-1")

    assert result["status"] == "success"
    assert result["backend_metadata"]["delete_agent"] is False
    assert delete_calls == []


def test_openagent_backend_missing_api_key_is_controlled(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from benchmark.backends.openagent import OpenAgentBackend

    monkeypatch.delenv("OPENAGENT_API_KEY", raising=False)
    backend = OpenAgentBackend()
    context = _context(tmp_path, backend="openagent")

    with pytest.raises(BackendInitializationError, match="OPENAGENT_API_KEY"):
        backend.initialize_run(context)


def test_openagent_backend_returns_backend_compatible_result(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from benchmark.backends.openagent import OpenAgentBackend

    monkeypatch.setenv("OPENAGENT_API_KEY", "test-key")
    monkeypatch.setenv("OPENAGENT_BASE_URL", "http://openagent.test")
    monkeypatch.setenv("OPENAGENT_ENABLE_ACTBENCH_MCP", "0")
    backend = OpenAgentBackend()
    monkeypatch.setattr(backend, "_check_health", lambda config: None)
    calls: list[list[dict[str, str]]] = []

    def fake_completion(**kwargs):
        calls.append([dict(message) for message in kwargs["messages"]])
        return {
            "choices": [{"message": {"role": "assistant", "content": "done"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        }

    monkeypatch.setattr(backend, "_post_chat_completion", fake_completion)
    context = _context(tmp_path, backend="openagent")
    task = _task(frontmatter={"sessions": ["first", {"prompt": "second"}]})

    backend.initialize_run(context)
    result = backend.execute_task(task=task, context=context, attempt_run_id="run_001-1")

    assert result["status"] == "success"
    assert result["backend"] == "openagent"
    assert result["backend_metadata"]["endpoint"] == "/api/v1/chat/completions"
    assert result["backend_metadata"]["transcript_source"] == "openagent_openai_compatible"
    assert result["usage"]["input_tokens"] == 20
    assert result["usage"]["output_tokens"] == 10
    assert result["usage"]["total_tokens"] == 30
    assert result["usage"]["request_count"] == 2
    assert len(result["transcript"]) == 4
    assert calls[1] == [
        {"role": "user", "content": "first"},
        {"role": "assistant", "content": "done"},
        {"role": "user", "content": "second"},
    ]
    assert (Path(result["workspace"]) / "README.md").read_text(encoding="utf-8") == "hello"


def test_openagent_backend_http_failure_returns_error_result(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from benchmark.backends.openagent import OpenAgentBackend, OpenAgentRequestError

    monkeypatch.setenv("OPENAGENT_API_KEY", "test-key")
    monkeypatch.setenv("OPENAGENT_ENABLE_ACTBENCH_MCP", "0")
    backend = OpenAgentBackend()
    monkeypatch.setattr(backend, "_check_health", lambda config: None)
    monkeypatch.setattr(
        backend,
        "_post_chat_completion",
        lambda **kwargs: (_ for _ in ()).throw(OpenAgentRequestError("openagent boom")),
    )
    context = _context(tmp_path, backend="openagent")

    backend.initialize_run(context)
    result = backend.execute_task(task=_task(), context=context, attempt_run_id="run_001-1")

    assert result["status"] == "error"
    assert result["backend"] == "openagent"
    assert "openagent boom" in result["stderr"]


def test_hermes_backend_missing_binary_is_controlled(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import benchmark.backends.hermes as hermes_module
    from benchmark.backends.hermes import HermesBackend

    _configure_hermes_test_env(monkeypatch, mcp_enabled=False)
    monkeypatch.setattr(hermes_module.shutil, "which", lambda _: None)
    backend = HermesBackend()
    context = _context(tmp_path, backend="hermes")

    with pytest.raises(BackendInitializationError, match="ACTBENCH_HERMES_BIN"):
        backend.initialize_run(context)


def test_hermes_backend_returns_backend_compatible_result(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import benchmark.backends.hermes as hermes_module
    from benchmark.backends.hermes import HermesBackend

    _configure_hermes_test_env(monkeypatch, mcp_enabled=False)
    monkeypatch.setattr(hermes_module.shutil, "which", lambda _: "/usr/bin/hermes")
    backend = HermesBackend()
    calls: list[dict] = []

    def fake_run(**kwargs):
        calls.append(kwargs)
        kwargs["usage_file"].write_text(
            json.dumps(
                {
                    "input_tokens": 10,
                    "output_tokens": 5,
                    "cache_read_tokens": 2,
                    "cache_write_tokens": 1,
                    "total_tokens": 18,
                    "estimated_cost_usd": 0.125,
                    "api_calls": 3,
                }
            ),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(
            args=["hermes"], returncode=0, stdout="done\n", stderr=""
        )

    monkeypatch.setattr(backend, "_run_hermes_subprocess", fake_run)
    context = _context(tmp_path, backend="hermes")
    task = _task(frontmatter={"sessions": ["first", {"prompt": "second"}]})

    backend.initialize_run(context)
    result = backend.execute_task(task=task, context=context, attempt_run_id="run_001-1")

    assert result["status"] == "success"
    assert result["backend"] == "hermes"
    assert (
        result["backend_metadata"]["transcript_source"]
        == "hermes_sessions_export_empty_fallback_stdout"
    )
    assert result["backend_metadata"]["provider"] == "test-provider"
    assert result["backend_metadata"]["mcp_enabled"] is False
    assert result["usage"]["input_tokens"] == 10
    assert result["usage"]["output_tokens"] == 5
    assert result["usage"]["cache_read_tokens"] == 2
    assert result["usage"]["cache_write_tokens"] == 1
    assert result["usage"]["total_tokens"] == 18
    assert result["usage"]["cost_usd"] == 0.125
    assert result["usage"]["request_count"] == 3
    assert "Session 1:" in calls[0]["prompt"]
    assert "Session 2:" in calls[0]["prompt"]
    assert calls[0]["workspace"] == Path(result["workspace"])
    assert (Path(result["workspace"]) / "README.md").read_text(encoding="utf-8") == "hello"


def test_hermes_backend_nonzero_exit_returns_error_result(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import benchmark.backends.hermes as hermes_module
    from benchmark.backends.hermes import HermesBackend

    _configure_hermes_test_env(monkeypatch, mcp_enabled=False)
    monkeypatch.setattr(hermes_module.shutil, "which", lambda _: "/usr/bin/hermes")
    backend = HermesBackend()
    monkeypatch.setattr(
        backend,
        "_run_hermes_subprocess",
        lambda **kwargs: subprocess.CompletedProcess(
            args=["hermes"], returncode=2, stdout="", stderr="hermes boom"
        ),
    )
    context = _context(tmp_path, backend="hermes")

    backend.initialize_run(context)
    result = backend.execute_task(task=_task(), context=context, attempt_run_id="run_001-1")

    assert result["status"] == "error"
    assert result["backend"] == "hermes"
    assert result["exit_code"] == 2
    assert "hermes boom" in result["stderr"]


def test_hermes_backend_timeout_returns_timeout_result(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import benchmark.backends.hermes as hermes_module
    from benchmark.backends.hermes import HermesBackend

    _configure_hermes_test_env(monkeypatch, mcp_enabled=False)
    monkeypatch.setattr(hermes_module.shutil, "which", lambda _: "/usr/bin/hermes")
    backend = HermesBackend()

    def fake_timeout(**kwargs):
        raise subprocess.TimeoutExpired(
            cmd="hermes", timeout=kwargs["timeout_seconds"], output="partial", stderr="stderr"
        )

    monkeypatch.setattr(backend, "_run_hermes_subprocess", fake_timeout)
    context = _context(tmp_path, backend="hermes")

    backend.initialize_run(context)
    result = backend.execute_task(task=_task(), context=context, attempt_run_id="run_001-1")

    assert result["status"] == "timeout"
    assert result["timed_out"] is True
    assert result["exit_code"] == -1
    assert "timed out" in result["stderr"]
    assert result["stdout"] == "partial"


def test_opencode_backend_missing_binary_is_controlled(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import benchmark.backends.opencode as opencode_module
    from benchmark.backends.opencode import OpenCodeBackend

    _configure_opencode_test_env(monkeypatch, mcp_enabled=False)
    monkeypatch.setattr(opencode_module.shutil, "which", lambda _: None)
    backend = OpenCodeBackend()
    context = _context(tmp_path, backend="opencode")

    with pytest.raises(BackendInitializationError, match="ACTBENCH_OPENCODE_BIN"):
        backend.initialize_run(context)


def test_opencode_transcript_helpers_normalize_export_messages() -> None:
    from benchmark.backends.opencode import (
        _extract_session_id_from_run_stdout,
        _normalize_opencode_export_to_transcript,
        _usage_from_opencode_export,
    )

    export_payload = {
        "info": {"id": "ses_1"},
        "messages": [
            {
                "info": {"role": "user", "id": "msg_user", "sessionID": "ses_1"},
                "parts": [{"type": "text", "id": "prt_user", "text": "Read the file."}],
            },
            {
                "info": {
                    "role": "assistant",
                    "id": "msg_assistant",
                    "sessionID": "ses_1",
                    "tokens": {
                        "input": 10,
                        "output": 5,
                        "reasoning": 1,
                        "cache": {"read": 2, "write": 3},
                    },
                    "cost": 0.125,
                },
                "parts": [
                    {"type": "text", "id": "txt_1", "text": "I will inspect it."},
                    {
                        "type": "tool",
                        "id": "prt_tool_1",
                        "callID": "tool_1",
                        "tool": "actbench_read_file",
                        "state": {
                            "status": "completed",
                            "input": {
                                "path": "README.md",
                                "context_id": "ctx-secret",
                                "headers": {"Authorization": "Bearer should-not-leak"},
                            },
                            "output": "hello",
                        },
                    },
                ],
            },
            {"type": "shell", "callID": "shell_1", "command": "ls", "output": "README.md\n"},
        ],
    }

    transcript = _normalize_opencode_export_to_transcript(export_payload)

    assert transcript[0] == {
        "type": "message",
        "message": {"role": "user", "content": ["Read the file."]},
    }
    tool_call_blocks = [
        item
        for entry in transcript
        for item in entry.get("message", {}).get("content", [])
        if isinstance(item, dict) and item.get("type") == "toolCall"
    ]
    tool_result_blocks = [
        item
        for entry in transcript
        for item in entry.get("message", {}).get("content", [])
        if isinstance(item, dict) and item.get("type") == "toolResult"
    ]
    assert tool_call_blocks[0] == {
        "type": "toolCall",
        "name": "actbench_read_file",
        "arguments": {
            "path": "README.md",
            "headers": {"Authorization": "[redacted]"},
        },
        "id": "tool_1",
    }
    assert tool_result_blocks[0] == {
        "type": "toolResult",
        "text": "hello",
        "tool_call_id": "tool_1",
        "name": "actbench_read_file",
        "isError": False,
    }
    assert tool_call_blocks[1] == {
        "type": "toolCall",
        "name": "shell",
        "arguments": {"command": "ls"},
        "id": "shell_1",
    }
    usage = _usage_from_opencode_export(export_payload)
    assert usage["input_tokens"] == 10
    assert usage["output_tokens"] == 6
    assert usage["cache_read_tokens"] == 2
    assert usage["cache_write_tokens"] == 3
    assert usage["total_tokens"] == 16
    assert usage["cost_usd"] == 0.125
    assert usage["request_count"] == 1
    assert _extract_session_id_from_run_stdout('{"type":"text","sessionID":"ses_1"}\n') == "ses_1"
    assert _extract_session_id_from_run_stdout('[{"sessionID":"ses_list"}]\n') == "ses_list"


def test_opencode_mcp_disabled_ignores_stale_mcp_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import benchmark.backends.opencode as opencode_module
    from benchmark.backends.opencode import OpenCodeBackend

    _configure_opencode_test_env(monkeypatch, mcp_enabled=False)
    monkeypatch.setenv("ACTBENCH_MCP_PORT", "not-a-port")
    monkeypatch.setattr(opencode_module.shutil, "which", lambda _: "/usr/bin/opencode")
    backend = OpenCodeBackend()

    backend.initialize_run(_context(tmp_path, backend="opencode"))

    assert backend._config is not None
    assert backend._config.mcp_enabled is False


def test_opencode_backend_returns_backend_compatible_result(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import benchmark.backends.opencode as opencode_module
    from benchmark.backends.opencode import OpenCodeBackend

    _configure_opencode_test_env(monkeypatch, mcp_enabled=False)
    monkeypatch.setattr(opencode_module.shutil, "which", lambda _: "/usr/bin/opencode")
    backend = OpenCodeBackend()
    calls: list[dict] = []

    def fake_run(**kwargs):
        calls.append(kwargs)
        return subprocess.CompletedProcess(
            args=["opencode"],
            returncode=0,
            stdout=(
                '{"type":"text","sessionID":"ses_1",'
                '"part":{"type":"text","text":"done","time":{"end":1}}}\n'
            ),
            stderr="",
        )

    def fake_export(**kwargs):
        return subprocess.CompletedProcess(
            args=["opencode", "export", kwargs["session_id"]],
            returncode=0,
            stdout=json.dumps(
                {
                    "info": {"id": kwargs["session_id"]},
                    "messages": [
                        {
                            "info": {"role": "user", "id": "msg_user", "sessionID": kwargs["session_id"]},
                            "parts": [{"type": "text", "id": "prt_user", "text": "Say hello."}],
                        },
                        {
                            "info": {
                                "role": "assistant",
                                "id": "msg_assistant",
                                "sessionID": kwargs["session_id"],
                                "tokens": {
                                    "input": 10,
                                    "output": 5,
                                    "reasoning": 0,
                                    "cache": {"read": 2, "write": 1},
                                },
                                "cost": 0.125,
                            },
                            "parts": [{"type": "text", "id": "txt_1", "text": "done"}],
                        },
                    ],
                }
            ),
            stderr="",
        )

    monkeypatch.setattr(backend, "_run_opencode_subprocess", fake_run)
    monkeypatch.setattr(backend, "_run_opencode_export", fake_export)
    context = _context(tmp_path, backend="opencode")
    task = _task(frontmatter={"sessions": ["first", {"prompt": "second"}]})

    backend.initialize_run(context)
    result = backend.execute_task(task=task, context=context, attempt_run_id="run_001-1")

    assert result["status"] == "success"
    assert result["backend"] == "opencode"
    assert result["backend_metadata"]["transcript_source"] == "opencode_export"
    assert result["backend_metadata"]["opencode_session_id"] == "ses_1"
    assert result["backend_metadata"]["mcp_enabled"] is False
    assert result["usage"]["input_tokens"] == 10
    assert result["usage"]["output_tokens"] == 5
    assert result["usage"]["cache_read_tokens"] == 2
    assert result["usage"]["cache_write_tokens"] == 1
    assert result["usage"]["total_tokens"] == 15
    assert result["usage"]["cost_usd"] == 0.125
    assert result["usage"]["request_count"] == 1
    assert "Session 1:" in calls[0]["prompt"]
    assert "Session 2:" in calls[0]["prompt"]
    assert calls[0]["workspace"] == Path(result["workspace"])
    assert (Path(result["workspace"]) / "README.md").read_text(encoding="utf-8") == "hello"


def test_claudecode_backend_missing_binary_is_controlled(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import benchmark.backends.claudecode as claudecode_module
    from benchmark.backends.claudecode import ClaudeCodeBackend

    _configure_claudecode_test_env(monkeypatch, mcp_enabled=False)
    monkeypatch.setattr(claudecode_module.shutil, "which", lambda _: None)
    backend = ClaudeCodeBackend()
    context = _context(tmp_path, backend="claudecode")

    with pytest.raises(BackendInitializationError, match="ACTBENCH_CLAUDECODE_BIN"):
        backend.initialize_run(context)


def test_claudecode_transcript_helpers_normalize_stream_json() -> None:
    from benchmark.backends.claudecode import (
        _extract_claudecode_transcript,
        _has_usable_transcript,
        _usage_from_claudecode_stream,
    )

    stdout = "\n".join(
        [
            "not-json",
            json.dumps(
                {
                    "type": "assistant",
                    "message": {
                        "role": "assistant",
                        "content": [
                            {"type": "thinking", "thinking": "private"},
                            {"type": "text", "text": "I will inspect it."},
                            {
                                "type": "tool_use",
                                "id": "tool_1",
                                "name": "mcp__actbench__actbench_read_file",
                                "input": {
                                    "path": "README.md",
                                    "context_id": "ctx-secret",
                                    "headers": {"Authorization": "Bearer should-not-leak"},
                                },
                            },
                        ],
                        "usage": {"input_tokens": 2, "output_tokens": 1},
                    },
                }
            ),
            json.dumps(
                {
                    "type": "user",
                    "message": {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": "tool_1",
                                "content": [{"type": "text", "text": "hello"}],
                            }
                        ],
                    },
                }
            ),
            json.dumps(
                {
                    "type": "result",
                    "num_turns": 2,
                    "total_cost_usd": 0.25,
                    "usage": {
                        "input_tokens": 10,
                        "output_tokens": 5,
                        "cache_read_input_tokens": 2,
                        "cache_creation_input_tokens": 3,
                    },
                }
            ),
        ]
    )

    transcript, source, metadata, usage = _extract_claudecode_transcript(
        effective_prompt="Read the file.",
        stdout=stdout,
        redactions=["ctx-secret"],
    )

    assert source == "claudecode_stream_json"
    assert metadata["event_counts"] == {"assistant": 1, "user": 1, "result": 1}
    assert metadata["non_json_lines"] == 1
    assert _has_usable_transcript(transcript) is True
    tool_call_blocks = [
        item
        for entry in transcript
        for item in entry.get("message", {}).get("content", [])
        if isinstance(item, dict) and item.get("type") == "toolCall"
    ]
    tool_result_blocks = [
        item
        for entry in transcript
        for item in entry.get("message", {}).get("content", [])
        if isinstance(item, dict) and item.get("type") == "toolResult"
    ]
    assert tool_call_blocks == [
        {
            "type": "toolCall",
            "name": "mcp__actbench__actbench_read_file",
            "arguments": {
                "path": "README.md",
                "headers": {"Authorization": "[redacted]"},
            },
            "id": "tool_1",
        }
    ]
    assert tool_result_blocks == [
        {
            "type": "toolResult",
            "text": "hello",
            "tool_call_id": "tool_1",
            "name": "mcp__actbench__actbench_read_file",
            "isError": False,
        }
    ]
    assert "private" not in json.dumps(transcript)
    assert "ctx-secret" not in json.dumps(transcript)
    assert "should-not-leak" not in json.dumps(transcript)
    assert usage == _usage_from_claudecode_stream(stdout)
    assert usage["input_tokens"] == 10
    assert usage["output_tokens"] == 5
    assert usage["cache_read_tokens"] == 2
    assert usage["cache_write_tokens"] == 3
    assert usage["total_tokens"] == 15
    assert usage["cost_usd"] == 0.25
    assert usage["request_count"] == 2


def test_claudecode_mcp_disabled_ignores_stale_mcp_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import benchmark.backends.claudecode as claudecode_module
    from benchmark.backends.claudecode import ClaudeCodeBackend

    _configure_claudecode_test_env(monkeypatch, mcp_enabled=False)
    monkeypatch.setenv("ACTBENCH_MCP_PORT", "not-a-port")
    monkeypatch.setattr(claudecode_module.shutil, "which", lambda _: "/usr/bin/claude")
    backend = ClaudeCodeBackend()

    backend.initialize_run(_context(tmp_path, backend="claudecode"))

    assert backend._config is not None
    assert backend._config.mcp_enabled is False
    assert "Read" in backend._config.allowed_tools
    assert backend._config.builtin_tools is None
    assert (backend._config.claudecode_home / "actbench-claudecode.json").exists()


def test_claudecode_subprocess_uses_headless_flags_allowed_tools_and_isolated_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import benchmark.backends.claudecode as claudecode_module
    from benchmark.backends.claudecode import ClaudeCodeBackend, ClaudeCodeConfig

    monkeypatch.setenv("ACTBENCH_MCP_ADMIN_TOKEN", "secret-token")
    captured: dict[str, object] = {}

    def fake_subprocess_run(cmd, **kwargs):
        captured["cmd"] = cmd
        captured.update(kwargs)
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(claudecode_module.subprocess, "run", fake_subprocess_run)
    config = ClaudeCodeConfig(
        executable="/usr/bin/claude",
        model="claude-opus-4-8",
        timeout_seconds=None,
        claudecode_home=tmp_path / "claudecode_home",
        permission_mode="dontAsk",
        allowed_tools=("mcp__actbench__actbench_read_file",),
        builtin_tools="",
        mcp_enabled=True,
        mcp_autostart=False,
        mcp_host="127.0.0.1",
        mcp_port=8765,
        mcp_public_url="http://mcp.test/mcp",
        mcp_admin_token="secret-token",
    )
    mcp_config_path = tmp_path / "mcp.json"

    ClaudeCodeBackend()._run_claudecode_subprocess(
        config=config,
        prompt="Prompt text",
        workspace=tmp_path,
        session_id="00000000-0000-4000-8000-000000000003",
        mcp_config_path=mcp_config_path,
        timeout_seconds=12.0,
    )

    cmd = captured["cmd"]
    assert isinstance(cmd, list)
    assert cmd[:3] == ["/usr/bin/claude", "--bare", "-p"]
    assert "--output-format" in cmd and cmd[cmd.index("--output-format") + 1] == "stream-json"
    assert "--verbose" in cmd
    assert "--permission-mode" in cmd and cmd[cmd.index("--permission-mode") + 1] == "dontAsk"
    assert "--session-id" in cmd
    assert cmd[cmd.index("--session-id") + 1] == "00000000-0000-4000-8000-000000000003"
    assert "--tools" in cmd and cmd[cmd.index("--tools") + 1] == ""
    assert "--allowedTools" in cmd
    assert cmd[cmd.index("--allowedTools") + 1] == "mcp__actbench__actbench_read_file"
    assert "--mcp-config" in cmd and cmd[cmd.index("--mcp-config") + 1] == str(mcp_config_path)
    assert "--strict-mcp-config" in cmd
    env = captured["env"]
    assert isinstance(env, dict)
    assert env["HOME"] == str(config.home_dir)
    assert env["CLAUDE_CONFIG_DIR"] == str(config.config_dir)
    assert "ACTBENCH_MCP_ADMIN_TOKEN" not in env


def test_claudecode_backend_returns_backend_compatible_result(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import benchmark.backends.claudecode as claudecode_module
    from benchmark.backends.claudecode import ClaudeCodeBackend

    _configure_claudecode_test_env(monkeypatch, mcp_enabled=False)
    monkeypatch.setattr(claudecode_module.shutil, "which", lambda _: "/usr/bin/claude")
    monkeypatch.setattr(
        claudecode_module.uuid,
        "uuid4",
        lambda: "00000000-0000-4000-8000-000000000001",
    )
    backend = ClaudeCodeBackend()
    calls: list[dict] = []

    def fake_run(**kwargs):
        calls.append(kwargs)
        return subprocess.CompletedProcess(
            args=["claude"],
            returncode=0,
            stdout="\n".join(
                [
                    json.dumps(
                        {
                            "type": "assistant",
                            "message": {
                                "role": "assistant",
                                "content": [{"type": "text", "text": "done"}],
                                "usage": {"input_tokens": 10, "output_tokens": 5},
                            },
                        }
                    ),
                    json.dumps(
                        {
                            "type": "result",
                            "num_turns": 1,
                            "total_cost_usd": 0.125,
                            "usage": {"input_tokens": 10, "output_tokens": 5},
                        }
                    ),
                ]
            ),
            stderr="",
        )

    monkeypatch.setattr(backend, "_run_claudecode_subprocess", fake_run)
    context = _context(tmp_path, backend="claudecode")
    task = _task(frontmatter={"sessions": ["first", {"prompt": "second"}]})

    backend.initialize_run(context)
    result = backend.execute_task(task=task, context=context, attempt_run_id="run_001-1")

    assert result["status"] == "success"
    assert result["backend"] == "claudecode"
    assert result["backend_metadata"]["transcript_source"] == "claudecode_stream_json"
    assert result["backend_metadata"]["claudecode_session_id"] == "00000000-0000-4000-8000-000000000001"
    assert result["backend_metadata"]["permission_mode"] == "dontAsk"
    assert result["backend_metadata"]["mcp_enabled"] is False
    assert result["usage"]["input_tokens"] == 10
    assert result["usage"]["output_tokens"] == 5
    assert result["usage"]["total_tokens"] == 15
    assert result["usage"]["cost_usd"] == 0.125
    assert "Session 1:" in calls[0]["prompt"]
    assert "Session 2:" in calls[0]["prompt"]
    assert calls[0]["workspace"] == Path(result["workspace"])
    assert calls[0]["mcp_config_path"] is None
    assert (Path(result["workspace"]) / "README.md").read_text(encoding="utf-8") == "hello"


def test_claudecode_success_without_usable_transcript_becomes_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import benchmark.backends.claudecode as claudecode_module
    from benchmark.backends.claudecode import ClaudeCodeBackend

    _configure_claudecode_test_env(monkeypatch, mcp_enabled=False)
    monkeypatch.setattr(claudecode_module.shutil, "which", lambda _: "/usr/bin/claude")
    backend = ClaudeCodeBackend()
    monkeypatch.setattr(
        backend,
        "_run_claudecode_subprocess",
        lambda **kwargs: subprocess.CompletedProcess(
            args=["claude"], returncode=0, stdout="", stderr=""
        ),
    )
    context = _context(tmp_path, backend="claudecode")

    backend.initialize_run(context)
    result = backend.execute_task(task=_task(), context=context, attempt_run_id="run_001-1")

    assert result["status"] == "error"
    assert result["exit_code"] == -1
    assert "produced no transcript" in result["stderr"]


def test_claudecode_mcp_registers_context_writes_config_and_appends_traces(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import benchmark.backends.claudecode as claudecode_module
    from benchmark.backends.claudecode import ClaudeCodeBackend

    _configure_claudecode_test_env(monkeypatch, mcp_enabled=True)
    monkeypatch.setenv("ACTBENCH_MCP_AUTOSTART", "0")
    monkeypatch.setenv("ACTBENCH_MCP_ADMIN_TOKEN", "secret-token")
    monkeypatch.setenv("ACTBENCH_MCP_URL", "http://host.docker.internal:8765/mcp")
    monkeypatch.setattr(claudecode_module.shutil, "which", lambda _: "/usr/bin/claude")
    monkeypatch.setattr(claudecode_module.secrets, "token_urlsafe", lambda _: "ctx-123")
    monkeypatch.setattr(
        claudecode_module.uuid,
        "uuid4",
        lambda: "00000000-0000-4000-8000-000000000002",
    )
    monkeypatch.setattr(claudecode_module, "check_gateway_health", lambda **kwargs: None)
    registered: list[dict] = []
    unregistered: list[dict] = []
    monkeypatch.setattr(
        claudecode_module,
        "register_gateway_context",
        lambda **kwargs: registered.append(kwargs) or {"status": "ok"},
    )
    monkeypatch.setattr(
        claudecode_module,
        "unregister_gateway_context",
        lambda **kwargs: unregistered.append(kwargs) or {"status": "ok", "removed": True},
    )

    def fake_get_traces(**kwargs):
        return {
            "status": "ok",
            "context_id": "ctx-123",
            "traces": [
                {
                    "sequence": 3,
                    "name": "actbench_read_file",
                    "arguments": {
                        "path": "README.md",
                        "context_id": "ctx-123",
                        "headers": {"Authorization": "Bearer should-not-leak"},
                    },
                    "result": {
                        "content": [
                            {"type": "text", "text": '{"path":"README.md","content":"hello"}'}
                        ]
                    },
                    "isError": False,
                }
            ],
        }

    monkeypatch.setattr(claudecode_module, "get_gateway_context_traces", fake_get_traces)
    backend = ClaudeCodeBackend()
    prompts: list[str] = []
    mcp_config_paths: list[Path] = []

    def fake_run(**kwargs):
        prompts.append(kwargs["prompt"])
        mcp_config_paths.append(kwargs["mcp_config_path"])
        return subprocess.CompletedProcess(
            args=["claude"],
            returncode=0,
            stdout=json.dumps(
                {
                    "type": "assistant",
                    "message": {
                        "role": "assistant",
                        "content": [{"type": "text", "text": "done"}],
                    },
                }
            ),
            stderr="",
        )

    monkeypatch.setattr(backend, "_run_claudecode_subprocess", fake_run)
    context = _context(tmp_path, backend="claudecode")

    backend.initialize_run(context)
    result = backend.execute_task(task=_task(), context=context, attempt_run_id="run_001-1")

    assert result["status"] == "success"
    assert registered[0]["context_id"] == "ctx-123"
    assert registered[0]["workspace"] == Path(result["workspace"])
    assert "ctx-123" in prompts[0]
    assert "http://host.docker.internal:8765/mcp" in prompts[0]
    assert mcp_config_paths and mcp_config_paths[0].is_file()
    mcp_config = json.loads(mcp_config_paths[0].read_text(encoding="utf-8"))
    assert mcp_config == {
        "mcpServers": {
            "actbench": {"type": "http", "url": "http://host.docker.internal:8765/mcp"}
        }
    }
    assert unregistered == [
        {
            "mcp_url": "http://127.0.0.1:8765/mcp",
            "context_id": "ctx-123",
            "admin_token": "secret-token",
        }
    ]
    assert result["backend_metadata"]["mcp_enabled"] is True
    assert result["backend_metadata"]["mcp_public_url"] == "http://host.docker.internal:8765/mcp"
    assert result["backend_metadata"]["transcript_extraction"]["mcp_trace_messages_appended"] == 2
    tool_call_blocks = [
        item
        for entry in result["transcript"]
        for item in entry.get("message", {}).get("content", [])
        if isinstance(item, dict) and item.get("type") == "toolCall"
    ]
    assert any(block["name"] == "actbench_read_file" for block in tool_call_blocks)
    result_text = json.dumps(result, sort_keys=True)
    assert "secret-token" not in result_text
    assert "ctx-123" not in result_text
    assert "should-not-leak" not in result_text



def test_opencode_mcp_registers_context_and_prepends_prompt_instruction(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import benchmark.backends.opencode as opencode_module
    from benchmark.backends.opencode import OpenCodeBackend

    _configure_opencode_test_env(monkeypatch, mcp_enabled=True)
    monkeypatch.setenv("ACTBENCH_MCP_AUTOSTART", "0")
    monkeypatch.setenv("ACTBENCH_MCP_ADMIN_TOKEN", "secret-token")
    monkeypatch.setenv("ACTBENCH_MCP_URL", "http://host.docker.internal:8765/mcp")
    monkeypatch.setattr(opencode_module.shutil, "which", lambda _: "/usr/bin/opencode")
    monkeypatch.setattr(opencode_module.secrets, "token_urlsafe", lambda _: "ctx-123")
    monkeypatch.setattr(opencode_module, "check_gateway_health", lambda **kwargs: None)
    registered: list[dict] = []
    unregistered: list[dict] = []
    monkeypatch.setattr(
        opencode_module,
        "register_gateway_context",
        lambda **kwargs: registered.append(kwargs) or {"status": "ok"},
    )
    monkeypatch.setattr(
        opencode_module,
        "unregister_gateway_context",
        lambda **kwargs: unregistered.append(kwargs) or {"status": "ok", "removed": True},
    )
    monkeypatch.setattr(
        opencode_module,
        "get_gateway_context_traces",
        lambda **kwargs: {"status": "ok", "traces": []},
    )
    backend = OpenCodeBackend()
    prompts: list[str] = []

    def fake_run(**kwargs):
        prompts.append(kwargs["prompt"])
        return subprocess.CompletedProcess(
            args=["opencode"],
            returncode=0,
            stdout='{"type":"text","sessionID":"ses_mcp","part":{"type":"text","text":"done"}}\n',
            stderr="",
        )

    def fake_export(**kwargs):
        return subprocess.CompletedProcess(
            args=["opencode", "export", kwargs["session_id"]],
            returncode=0,
            stdout=json.dumps(
                {
                    "info": {"id": kwargs["session_id"]},
                    "messages": [
                        {
                            "info": {"role": "user", "id": "msg_user", "sessionID": kwargs["session_id"]},
                            "parts": [{"type": "text", "id": "prt_user", "text": "Say hello."}],
                        },
                        {
                            "info": {
                                "role": "assistant",
                                "id": "msg_assistant",
                                "sessionID": kwargs["session_id"],
                            },
                            "parts": [{"type": "text", "id": "txt_1", "text": "done"}],
                        },
                    ],
                }
            ),
            stderr="",
        )

    monkeypatch.setattr(backend, "_run_opencode_subprocess", fake_run)
    monkeypatch.setattr(backend, "_run_opencode_export", fake_export)
    context = _context(tmp_path, backend="opencode")

    backend.initialize_run(context)
    result = backend.execute_task(task=_task(), context=context, attempt_run_id="run_001-1")

    assert result["status"] == "success"
    assert len(registered) == 1
    assert registered[0]["context_id"] == "ctx-123"
    assert registered[0]["workspace"] == Path(result["workspace"])
    assert registered[0]["ttl_seconds"] >= 60
    assert "ctx-123" in prompts[0]
    assert "http://host.docker.internal:8765/mcp" in prompts[0]
    assert unregistered == [
        {
            "mcp_url": "http://127.0.0.1:8765/mcp",
            "context_id": "ctx-123",
            "admin_token": "secret-token",
        }
    ]
    assert result["backend_metadata"]["mcp_enabled"] is True
    assert result["backend_metadata"]["mcp_public_url"] == "http://host.docker.internal:8765/mcp"
    result_text = json.dumps(result, sort_keys=True)
    assert "secret-token" not in result_text
    assert "ctx-123" not in result_text


def test_hermes_mcp_initialize_autostarts_gateway(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import benchmark.backends.hermes as hermes_module
    from benchmark.backends.hermes import HermesBackend

    _configure_hermes_test_env(monkeypatch, mcp_enabled=True)
    monkeypatch.setenv("ACTBENCH_MCP_PORT", "9877")
    monkeypatch.setattr(hermes_module.shutil, "which", lambda _: "/usr/bin/hermes")
    monkeypatch.setattr(
        hermes_module,
        "check_gateway_health",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("not running")),
    )
    started: list[dict] = []

    def fake_start_gateway_subprocess(**kwargs):
        started.append(kwargs)
        return hermes_module.ActBenchMcpGatewayProcess(
            process=None,
            host=kwargs["host"],
            port=kwargs["port"],
            mcp_url=f"http://{kwargs['host']}:{kwargs['port']}/mcp",
            admin_token=kwargs.get("admin_token"),
        )

    monkeypatch.setattr(hermes_module, "start_gateway_subprocess", fake_start_gateway_subprocess)
    backend = HermesBackend()

    backend.initialize_run(_context(tmp_path, backend="hermes"))

    assert started == [
        {
            "host": "127.0.0.1",
            "port": 9877,
            "admin_token": backend._config.mcp_admin_token,
        }
    ]
    assert backend._config.mcp_admin_token


def test_hermes_mcp_initialize_checks_external_gateway(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import benchmark.backends.hermes as hermes_module
    from benchmark.backends.hermes import HermesBackend

    _configure_hermes_test_env(monkeypatch, mcp_enabled=True)
    monkeypatch.setenv("ACTBENCH_MCP_AUTOSTART", "0")
    monkeypatch.setattr(hermes_module.shutil, "which", lambda _: "/usr/bin/hermes")
    checked: list[dict] = []
    monkeypatch.setattr(
        hermes_module, "check_gateway_health", lambda **kwargs: checked.append(kwargs)
    )
    monkeypatch.setattr(
        hermes_module,
        "start_gateway_subprocess",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("should not autostart")),
    )
    backend = HermesBackend()

    backend.initialize_run(_context(tmp_path, backend="hermes"))

    assert checked == [{"host": "127.0.0.1", "port": 8765}]
    assert backend._mcp_gateway is not None
    assert backend._mcp_gateway.process is None


def test_hermes_mcp_registers_context_and_prepends_prompt_instruction(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import benchmark.backends.hermes as hermes_module
    from benchmark.backends.hermes import HermesBackend

    _configure_hermes_test_env(monkeypatch, mcp_enabled=True)
    monkeypatch.setenv("ACTBENCH_MCP_AUTOSTART", "0")
    monkeypatch.setenv("ACTBENCH_MCP_ADMIN_TOKEN", "secret-token")
    monkeypatch.setenv("ACTBENCH_MCP_URL", "http://host.docker.internal:8765/mcp")
    monkeypatch.setattr(hermes_module.shutil, "which", lambda _: "/usr/bin/hermes")
    monkeypatch.setattr(hermes_module.secrets, "token_urlsafe", lambda _: "ctx-123")
    monkeypatch.setattr(hermes_module, "check_gateway_health", lambda **kwargs: None)
    registered: list[dict] = []
    unregistered: list[dict] = []
    monkeypatch.setattr(
        hermes_module,
        "register_gateway_context",
        lambda **kwargs: registered.append(kwargs) or {"status": "ok"},
    )
    monkeypatch.setattr(
        hermes_module,
        "unregister_gateway_context",
        lambda **kwargs: unregistered.append(kwargs) or {"status": "ok", "removed": True},
    )
    prompts: list[str] = []
    backend = HermesBackend()

    def fake_run(**kwargs):
        prompts.append(kwargs["prompt"])
        kwargs["usage_file"].write_text(json.dumps({"api_calls": 1}), encoding="utf-8")
        return subprocess.CompletedProcess(args=["hermes"], returncode=0, stdout="done", stderr="")

    monkeypatch.setattr(backend, "_run_hermes_subprocess", fake_run)
    context = _context(tmp_path, backend="hermes")

    backend.initialize_run(context)
    result = backend.execute_task(task=_task(), context=context, attempt_run_id="run_001-1")

    assert result["status"] == "success"
    assert len(registered) == 1
    assert registered[0]["context_id"] == "ctx-123"
    assert registered[0]["workspace"] == Path(result["workspace"])
    assert registered[0]["api_endpoints"] == {}
    assert registered[0]["ttl_seconds"] >= 60
    assert "ctx-123" in prompts[0]
    assert "http://host.docker.internal:8765/mcp" in prompts[0]
    assert "Say hello." in prompts[0]
    assert unregistered == [
        {
            "mcp_url": "http://127.0.0.1:8765/mcp",
            "context_id": "ctx-123",
            "admin_token": "secret-token",
        }
    ]
    assert result["backend_metadata"]["mcp_enabled"] is True
    assert result["backend_metadata"]["mcp_public_url"] == "http://host.docker.internal:8765/mcp"
    metadata_text = json.dumps(result["backend_metadata"], sort_keys=True)
    assert "secret-token" not in metadata_text
    assert "fixture" not in metadata_text.lower()


def test_hermes_mcp_unregisters_on_subprocess_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import benchmark.backends.hermes as hermes_module
    from benchmark.backends.hermes import HermesBackend

    _configure_hermes_test_env(monkeypatch, mcp_enabled=True)
    monkeypatch.setenv("ACTBENCH_MCP_AUTOSTART", "0")
    monkeypatch.setattr(hermes_module.shutil, "which", lambda _: "/usr/bin/hermes")
    monkeypatch.setattr(hermes_module.secrets, "token_urlsafe", lambda _: "ctx-error")
    monkeypatch.setattr(hermes_module, "check_gateway_health", lambda **kwargs: None)
    monkeypatch.setattr(
        hermes_module, "register_gateway_context", lambda **kwargs: {"status": "ok"}
    )
    unregistered: list[dict] = []
    monkeypatch.setattr(
        hermes_module,
        "unregister_gateway_context",
        lambda **kwargs: unregistered.append(kwargs) or {"status": "ok", "removed": True},
    )
    backend = HermesBackend()
    monkeypatch.setattr(
        backend,
        "_run_hermes_subprocess",
        lambda **kwargs: subprocess.CompletedProcess(
            args=["hermes"], returncode=1, stdout="", stderr="boom"
        ),
    )
    context = _context(tmp_path, backend="hermes")

    backend.initialize_run(context)
    result = backend.execute_task(task=_task(), context=context, attempt_run_id="run_001-1")

    assert result["status"] == "error"
    assert "boom" in result["stderr"]
    assert unregistered == [
        {
            "mcp_url": "http://127.0.0.1:8765/mcp",
            "context_id": "ctx-error",
            "admin_token": None,
        }
    ]


def test_hermes_mcp_result_endpoints_are_sanitized_when_services_declared(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import benchmark.backends.hermes as hermes_module
    from benchmark.backends.hermes import HermesBackend

    _configure_hermes_test_env(monkeypatch, mcp_enabled=True)
    monkeypatch.setenv("ACTBENCH_MCP_AUTOSTART", "0")
    monkeypatch.setattr(hermes_module.shutil, "which", lambda _: "/usr/bin/hermes")
    monkeypatch.setattr(hermes_module, "check_gateway_health", lambda **kwargs: None)
    monkeypatch.setattr(
        hermes_module, "register_gateway_context", lambda **kwargs: {"status": "ok"}
    )
    monkeypatch.setattr(
        hermes_module, "unregister_gateway_context", lambda **kwargs: {"status": "ok"}
    )
    backend = HermesBackend()
    monkeypatch.setattr(
        backend,
        "_run_hermes_subprocess",
        lambda **kwargs: subprocess.CompletedProcess(
            args=["hermes"], returncode=0, stdout="done", stderr=""
        ),
    )
    task = _task(frontmatter={"mock_services": ["mailbox"]})

    backend.initialize_run(_context(tmp_path, backend="hermes"))
    result = backend.execute_task(
        task=task, context=_context(tmp_path, backend="hermes"), attempt_run_id="run_001-1"
    )

    assert result["api_endpoints"] == {
        "mailbox": {
            "business_paths": [
                "/mailbox/messages",
                "/mailbox/messages/get",
                "/mailbox/messages/send",
                "/mailbox/drafts/save",
            ]
        }
    }
    endpoint_text = json.dumps(result["api_endpoints"], sort_keys=True)
    assert "127.0.0.1" not in endpoint_text
    assert "audit" not in endpoint_text
    assert "reset" not in endpoint_text
    assert "health" not in endpoint_text
    assert "fixture" not in endpoint_text.lower()


def test_openagent_mcp_initialize_autostarts_gateway(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import benchmark.backends.openagent as openagent_module
    from benchmark.backends.openagent import OpenAgentBackend

    monkeypatch.setenv("OPENAGENT_API_KEY", "test-key")
    monkeypatch.setenv("ACTBENCH_MCP_PORT", "9876")
    backend = OpenAgentBackend()
    monkeypatch.setattr(backend, "_check_health", lambda config: None)
    monkeypatch.setattr(
        openagent_module,
        "check_gateway_health",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("not running")),
    )
    started: list[dict] = []

    def fake_start_gateway_subprocess(**kwargs):
        started.append(kwargs)
        return openagent_module.ActBenchMcpGatewayProcess(
            process=None,
            host=kwargs["host"],
            port=kwargs["port"],
            mcp_url=f"http://{kwargs['host']}:{kwargs['port']}/mcp",
            admin_token=kwargs.get("admin_token"),
        )

    monkeypatch.setattr(openagent_module, "start_gateway_subprocess", fake_start_gateway_subprocess)

    backend.initialize_run(_context(tmp_path, backend="openagent"))

    assert started == [
        {
            "host": "127.0.0.1",
            "port": 9876,
            "admin_token": backend._config.mcp_admin_token,
        }
    ]
    assert backend._config.mcp_admin_token


def test_openagent_mcp_initialize_checks_external_gateway(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import benchmark.backends.openagent as openagent_module
    from benchmark.backends.openagent import OpenAgentBackend

    monkeypatch.setenv("OPENAGENT_API_KEY", "test-key")
    monkeypatch.setenv("ACTBENCH_MCP_AUTOSTART", "0")
    backend = OpenAgentBackend()
    monkeypatch.setattr(backend, "_check_health", lambda config: None)
    checked: list[dict] = []
    monkeypatch.setattr(
        openagent_module,
        "check_gateway_health",
        lambda **kwargs: checked.append(kwargs),
    )
    monkeypatch.setattr(
        openagent_module,
        "start_gateway_subprocess",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("should not autostart")),
    )

    backend.initialize_run(_context(tmp_path, backend="openagent"))

    assert checked == [{"host": "127.0.0.1", "port": 8765}]
    assert backend._mcp_gateway is not None
    assert backend._mcp_gateway.process is None


def test_openagent_mcp_result_endpoints_are_sanitized_when_services_declared(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import benchmark.backends.openagent as openagent_module
    from benchmark.backends.openagent import OpenAgentBackend

    monkeypatch.setenv("OPENAGENT_API_KEY", "test-key")
    monkeypatch.setenv("ACTBENCH_MCP_AUTOSTART", "0")
    backend = OpenAgentBackend()
    monkeypatch.setattr(backend, "_check_health", lambda config: None)
    monkeypatch.setattr(openagent_module, "check_gateway_health", lambda **kwargs: None)
    monkeypatch.setattr(
        openagent_module, "register_gateway_context", lambda **kwargs: {"status": "ok"}
    )
    monkeypatch.setattr(
        openagent_module, "unregister_gateway_context", lambda **kwargs: {"status": "ok"}
    )
    monkeypatch.setattr(
        openagent_module, "get_gateway_context_traces", lambda **kwargs: {"status": "ok", "traces": []}
    )
    monkeypatch.setattr(
        backend,
        "_post_chat_completion",
        lambda **kwargs: {"choices": [{"message": {"role": "assistant", "content": "done"}}]},
    )
    task = _task(frontmatter={"mock_services": ["mailbox"]})

    backend.initialize_run(_context(tmp_path, backend="openagent"))
    result = backend.execute_task(
        task=task, context=_context(tmp_path, backend="openagent"), attempt_run_id="run_001-1"
    )

    assert result["api_endpoints"] == {
        "mailbox": {
            "business_paths": [
                "/mailbox/messages",
                "/mailbox/messages/get",
                "/mailbox/messages/send",
                "/mailbox/drafts/save",
            ]
        }
    }
    endpoint_text = json.dumps(result["api_endpoints"], sort_keys=True)
    assert "127.0.0.1" not in endpoint_text
    assert "audit" not in endpoint_text
    assert "reset" not in endpoint_text
    assert "health" not in endpoint_text
    assert "fixture" not in endpoint_text.lower()


def test_openagent_mcp_registers_context_and_prepends_system_message(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import benchmark.backends.openagent as openagent_module
    from benchmark.backends.openagent import OpenAgentBackend

    monkeypatch.setenv("OPENAGENT_API_KEY", "test-key")
    monkeypatch.setenv("OPENAGENT_BASE_URL", "http://openagent.test")
    monkeypatch.setenv("ACTBENCH_MCP_AUTOSTART", "0")
    monkeypatch.setenv("ACTBENCH_MCP_ADMIN_TOKEN", "secret-token")
    monkeypatch.setenv("ACTBENCH_MCP_URL", "http://host.docker.internal:8765/mcp")
    monkeypatch.setattr(openagent_module.secrets, "token_urlsafe", lambda _: "ctx-123")
    backend = OpenAgentBackend()
    monkeypatch.setattr(backend, "_check_health", lambda config: None)
    monkeypatch.setattr(openagent_module, "check_gateway_health", lambda **kwargs: None)
    registered: list[dict] = []
    unregistered: list[dict] = []
    monkeypatch.setattr(
        openagent_module,
        "register_gateway_context",
        lambda **kwargs: registered.append(kwargs) or {"status": "ok"},
    )
    monkeypatch.setattr(
        openagent_module,
        "unregister_gateway_context",
        lambda **kwargs: unregistered.append(kwargs) or {"status": "ok", "removed": True},
    )
    monkeypatch.setattr(
        openagent_module,
        "get_gateway_context_traces",
        lambda **kwargs: {"status": "ok", "traces": []},
    )
    requests: list[list[dict]] = []

    def fake_completion(**kwargs):
        requests.append([dict(message) for message in kwargs["messages"]])
        return {
            "choices": [{"message": {"role": "assistant", "content": "done"}}],
            "usage": {"prompt_tokens": "10", "completion_tokens": "5", "cost": "0.125"},
        }

    monkeypatch.setattr(backend, "_post_chat_completion", fake_completion)
    context = _context(tmp_path, backend="openagent")

    backend.initialize_run(context)
    result = backend.execute_task(task=_task(), context=context, attempt_run_id="run_001-1")

    assert result["status"] == "success"
    assert len(registered) == 1
    assert registered[0]["context_id"] == "ctx-123"
    assert registered[0]["workspace"] == Path(result["workspace"])
    assert registered[0]["api_endpoints"] == {}
    assert registered[0]["ttl_seconds"] >= 60
    assert requests[0][0]["role"] == "system"
    assert "ctx-123" in requests[0][0]["content"]
    assert "http://host.docker.internal:8765/mcp" in requests[0][0]["content"]
    assert requests[0][1] == {"role": "user", "content": "Say hello."}
    assert unregistered == [
        {
            "mcp_url": "http://127.0.0.1:8765/mcp",
            "context_id": "ctx-123",
            "admin_token": "secret-token",
        }
    ]
    assert result["backend_metadata"]["mcp_enabled"] is True
    assert result["backend_metadata"]["mcp_public_url"] == "http://host.docker.internal:8765/mcp"
    assert result["api_endpoints"] == {}
    metadata_text = json.dumps(result["backend_metadata"], sort_keys=True)
    assert "secret-token" not in metadata_text
    assert "fixture" not in metadata_text.lower()
    assert result["usage"]["cost_usd"] == 0.125


def test_openagent_mcp_appends_gateway_traces_to_transcript(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import benchmark.backends.openagent as openagent_module
    from benchmark.backends.openagent import OpenAgentBackend
    from lib_reward import _transcript_to_text

    monkeypatch.setenv("OPENAGENT_API_KEY", "test-key")
    monkeypatch.setenv("ACTBENCH_MCP_AUTOSTART", "0")
    monkeypatch.setenv("ACTBENCH_MCP_ADMIN_TOKEN", "secret-token")
    monkeypatch.setattr(openagent_module.secrets, "token_urlsafe", lambda _: "ctx-trace")
    backend = OpenAgentBackend()
    monkeypatch.setattr(backend, "_check_health", lambda config: None)
    monkeypatch.setattr(openagent_module, "check_gateway_health", lambda **kwargs: None)
    events: list[str] = []
    trace_calls: list[dict] = []
    monkeypatch.setattr(
        openagent_module,
        "register_gateway_context",
        lambda **kwargs: events.append("register") or {"status": "ok"},
    )

    def fake_get_traces(**kwargs):
        events.append("get_traces")
        trace_calls.append(kwargs)
        return {
            "status": "ok",
            "context_id": "ctx-trace",
            "traces": [
                {
                    "sequence": 7,
                    "name": "actbench_read_file",
                    "arguments": {
                        "path": "README.md",
                        "context_id": "ctx-trace",
                        "headers": {"Authorization": "Bearer should-not-leak"},
                    },
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": '{"path":"README.md","content":"hello"}',
                            }
                        ],
                        "isError": False,
                    },
                    "isError": False,
                }
            ],
        }

    monkeypatch.setattr(openagent_module, "get_gateway_context_traces", fake_get_traces)
    monkeypatch.setattr(
        openagent_module,
        "unregister_gateway_context",
        lambda **kwargs: events.append("unregister") or {"status": "ok", "removed": True},
    )
    monkeypatch.setattr(
        backend,
        "_post_chat_completion",
        lambda **kwargs: {"choices": [{"message": {"role": "assistant", "content": "done"}}]},
    )
    context = _context(tmp_path, backend="openagent")

    backend.initialize_run(context)
    result = backend.execute_task(task=_task(), context=context, attempt_run_id="run_001-1")

    assert result["status"] == "success"
    assert events == ["register", "get_traces", "unregister"]
    assert trace_calls == [
        {
            "mcp_url": "http://127.0.0.1:8765/mcp",
            "context_id": "ctx-trace",
            "admin_token": "secret-token",
        }
    ]
    tool_call_blocks = [
        item
        for entry in result["transcript"]
        for item in entry.get("message", {}).get("content", [])
        if isinstance(item, dict) and item.get("type") == "toolCall"
    ]
    tool_result_blocks = [
        item
        for entry in result["transcript"]
        for item in entry.get("message", {}).get("content", [])
        if isinstance(item, dict) and item.get("type") == "toolResult"
    ]
    assert tool_call_blocks == [
        {
            "type": "toolCall",
            "name": "actbench_read_file",
            "arguments": {
                "path": "README.md",
                "headers": {"Authorization": "[redacted]"},
            },
            "id": "actbench-mcp-7",
        }
    ]
    assert tool_result_blocks == [
        {
            "type": "toolResult",
            "text": '{"path":"README.md","content":"hello"}',
            "tool_call_id": "actbench-mcp-7",
            "name": "actbench_read_file",
            "isError": False,
        }
    ]
    transcript_text = _transcript_to_text(result["transcript"])
    assert "toolCall" in transcript_text
    assert "actbench_read_file" in transcript_text
    assert "README.md" in transcript_text
    assert "toolResult" in transcript_text
    result_text = json.dumps(result, sort_keys=True)
    assert "secret-token" not in result_text
    assert "ctx-trace" not in result_text
    assert "should-not-leak" not in result_text


def test_openagent_mcp_trace_retrieval_failure_does_not_fail_task(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import benchmark.backends.openagent as openagent_module
    from benchmark.backends.openagent import OpenAgentBackend
    from lib_mcp_gateway import ActBenchMcpError

    monkeypatch.setenv("OPENAGENT_API_KEY", "test-key")
    monkeypatch.setenv("ACTBENCH_MCP_AUTOSTART", "0")
    monkeypatch.setattr(openagent_module.secrets, "token_urlsafe", lambda _: "ctx-trace-error")
    backend = OpenAgentBackend()
    monkeypatch.setattr(backend, "_check_health", lambda config: None)
    monkeypatch.setattr(openagent_module, "check_gateway_health", lambda **kwargs: None)
    monkeypatch.setattr(
        openagent_module, "register_gateway_context", lambda **kwargs: {"status": "ok"}
    )
    unregistered: list[dict] = []
    monkeypatch.setattr(
        openagent_module,
        "unregister_gateway_context",
        lambda **kwargs: unregistered.append(kwargs) or {"status": "ok", "removed": True},
    )
    monkeypatch.setattr(
        openagent_module,
        "get_gateway_context_traces",
        lambda **kwargs: (_ for _ in ()).throw(ActBenchMcpError("trace boom")),
    )
    monkeypatch.setattr(
        backend,
        "_post_chat_completion",
        lambda **kwargs: {"choices": [{"message": {"role": "assistant", "content": "done"}}]},
    )
    context = _context(tmp_path, backend="openagent")

    backend.initialize_run(context)
    result = backend.execute_task(task=_task(), context=context, attempt_run_id="run_001-1")

    assert result["status"] == "success"
    assert len(result["transcript"]) == 2
    assert unregistered == [
        {
            "mcp_url": "http://127.0.0.1:8765/mcp",
            "context_id": "ctx-trace-error",
            "admin_token": None,
        }
    ]


def test_openagent_mcp_unregisters_on_request_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import benchmark.backends.openagent as openagent_module
    from benchmark.backends.openagent import OpenAgentBackend, OpenAgentRequestError

    monkeypatch.setenv("OPENAGENT_API_KEY", "test-key")
    monkeypatch.setenv("ACTBENCH_MCP_AUTOSTART", "0")
    monkeypatch.setattr(openagent_module.secrets, "token_urlsafe", lambda _: "ctx-error")
    backend = OpenAgentBackend()
    monkeypatch.setattr(backend, "_check_health", lambda config: None)
    monkeypatch.setattr(openagent_module, "check_gateway_health", lambda **kwargs: None)
    monkeypatch.setattr(
        openagent_module, "register_gateway_context", lambda **kwargs: {"status": "ok"}
    )
    unregistered: list[dict] = []
    monkeypatch.setattr(
        openagent_module,
        "unregister_gateway_context",
        lambda **kwargs: unregistered.append(kwargs) or {"status": "ok", "removed": True},
    )
    monkeypatch.setattr(
        openagent_module,
        "get_gateway_context_traces",
        lambda **kwargs: {"status": "ok", "traces": []},
    )
    monkeypatch.setattr(
        backend,
        "_post_chat_completion",
        lambda **kwargs: (_ for _ in ()).throw(OpenAgentRequestError("openagent boom")),
    )
    context = _context(tmp_path, backend="openagent")

    backend.initialize_run(context)
    result = backend.execute_task(task=_task(), context=context, attempt_run_id="run_001-1")

    assert result["status"] == "error"
    assert "openagent boom" in result["stderr"]
    assert unregistered == [
        {
            "mcp_url": "http://127.0.0.1:8765/mcp",
            "context_id": "ctx-error",
            "admin_token": None,
        }
    ]


def test_run_benchmark_with_fake_backend_writes_backend_schema(tmp_path: Path) -> None:
    tasks_dir = tmp_path / "tasks"
    _write_minimal_task(tasks_dir)
    output_dir = tmp_path / "results"

    run_benchmark(
        Namespace(
            tasks_dir=str(tasks_dir),
            model="test/model",
            backend="fake",
            suite="task_fake",
            output_dir=str(output_dir),
            timeout_multiplier=1.0,
            runs=1,
            judge_model=None,
            verbose=False,
            no_fail_fast=True,
            skip_baseline_gen=True,
            training_artifact_dir=None,
            no_training_artifacts=True,
        )
    )

    result_files = sorted(output_dir.glob("????_test-model.json"))
    assert len(result_files) == 1
    payload = json.loads(result_files[0].read_text(encoding="utf-8"))
    assert payload["backend"] == "fake"
    assert payload["backend_metadata"]["name"] == "fake"
    task_entry = payload["tasks"][0]
    assert task_entry["backend"] == "fake"
    assert task_entry["agent_feedback"]["backend"] == "fake"
    assert task_entry["openclaw_feedback"]["backend"] == "fake"
