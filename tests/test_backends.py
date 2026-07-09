from __future__ import annotations

import json
import logging
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


def test_registry_resolves_backends_without_eager_optional_imports() -> None:
    assert available_backend_names() == ("openclaw", "qwenpaw", "openagent", "fake")
    assert get_backend("openclaw").name == "openclaw"
    assert get_backend("fake").name == "fake"
    assert get_backend("qwenpaw").name == "qwenpaw"
    assert get_backend("openagent").name == "openagent"
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


def test_qwenpaw_backend_missing_runtime_is_controlled(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from benchmark.backends.qwenpaw import QwenPawBackend

    backend = QwenPawBackend()
    context = _context(tmp_path, backend="qwenpaw")
    monkeypatch.setattr(
        backend,
        "_load_runtime",
        lambda: (_ for _ in ()).throw(BackendInitializationError("missing qwenpaw")),
    )

    with pytest.raises(BackendInitializationError, match="missing qwenpaw"):
        backend.initialize_run(context)


def test_qwenpaw_backend_allows_non_default_model_before_runtime_import(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    tmp_path: Path,
) -> None:
    from benchmark.backends.qwenpaw import QwenPawBackend

    tasks_dir = tmp_path / "tasks"
    _write_minimal_task(tasks_dir)
    monkeypatch.setattr(
        QwenPawBackend,
        "_load_runtime",
        lambda self: (_ for _ in ()).throw(BackendInitializationError("missing qwenpaw")),
    )

    with caplog.at_level(logging.ERROR, logger="benchmark"):
        with pytest.raises(SystemExit) as exc_info:
            run_benchmark(
                Namespace(
                    tasks_dir=str(tasks_dir),
                    model="other/model",
                    backend="qwenpaw",
                    suite="task_fake",
                    output_dir=str(tmp_path / "results"),
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

    assert exc_info.value.code == 2
    assert "missing qwenpaw" in caplog.text


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
    monkeypatch.setattr(openagent_module, "register_gateway_context", lambda **kwargs: {"status": "ok"})
    monkeypatch.setattr(openagent_module, "unregister_gateway_context", lambda **kwargs: {"status": "ok"})
    monkeypatch.setattr(
        backend,
        "_post_chat_completion",
        lambda **kwargs: {"choices": [{"message": {"role": "assistant", "content": "done"}}]},
    )
    task = _task(frontmatter={"mock_services": ["mailbox"]})

    backend.initialize_run(_context(tmp_path, backend="openagent"))
    result = backend.execute_task(task=task, context=_context(tmp_path, backend="openagent"), attempt_run_id="run_001-1")

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
    monkeypatch.setattr(openagent_module, "register_gateway_context", lambda **kwargs: {"status": "ok"})
    unregistered: list[dict] = []
    monkeypatch.setattr(
        openagent_module,
        "unregister_gateway_context",
        lambda **kwargs: unregistered.append(kwargs) or {"status": "ok", "removed": True},
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
