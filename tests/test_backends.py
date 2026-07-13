from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from argparse import Namespace
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

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
from lib_reward import RewardResult  # noqa: E402
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


def _context(
    tmp_path: Path,
    backend: str = "fake",
    metadata: dict | None = None,
) -> BackendRunContext:
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
        metadata=metadata or {},
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
    monkeypatch.delenv("ACTBENCH_CLAUDECODE_ALLOWED_TOOLS", raising=False)
    monkeypatch.delenv("ACTBENCH_CLAUDECODE_TOOLS", raising=False)
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
    monkeypatch.setenv("ACTBENCH_QWENPAW_USAGE_DELTA", "0")


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
    monkeypatch.setattr(
        sys, "argv", ["actbench", "--backend", "opencode", "--model", "opencode/test"]
    )

    args = _parse_args()

    assert args.backend == "opencode"
    assert args.model == "opencode/test"


def test_cli_accepts_claudecode_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        sys, "argv", ["actbench", "--backend", "claudecode", "--model", "claude/test"]
    )

    args = _parse_args()

    assert args.backend == "claudecode"
    assert args.model == "claude/test"


def test_cli_accepts_parallel_run_workers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["actbench", "--run-workers", "3"])

    args = _parse_args()

    assert args.run_workers == 3

    monkeypatch.setattr(sys, "argv", ["actbench", "--parallel-runs", "2"])

    args = _parse_args()

    assert args.run_workers == 2


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
    qwenpaw_backend = get_backend("qwenpaw")
    assert qwenpaw_backend.name == "qwenpaw"
    assert qwenpaw_backend.supports_parallel_runs is True
    assert get_backend("openagent").name == "openagent"
    assert get_backend("hermes").name == "hermes"
    assert get_backend("opencode").name == "opencode"
    assert get_backend("claudecode").name == "claudecode"
    with pytest.raises(ValueError, match="unknown backend"):
        get_backend("missing")


def _openclaw_success_result(**kwargs) -> dict:
    return {
        "agent_id": kwargs["agent_id"],
        "task_id": kwargs["task"].task_id,
        "status": "success",
        "transcript": [{"role": "assistant", "content": "done"}],
        "usage": {},
        "workspace": f"/workspace/{kwargs['agent_id']}/{kwargs['run_id']}",
        "exit_code": 0,
        "timed_out": False,
        "execution_time": 0.0,
        "stdout": "",
        "stderr": "",
        "api_audit": {},
        "api_endpoints": {},
    }


def _repeat_metadata(run_workers: int = 2) -> dict:
    return {
        "runs_per_task": 3,
        "run_workers": run_workers,
        "requested_run_workers": run_workers,
        "command": "actbench test",
    }


def test_openclaw_backend_delegates_to_existing_helpers(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import benchmark.backends.openclaw as openclaw_module

    calls: list[tuple[str, object]] = []
    execute_calls: list[dict] = []

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

    def fake_execute_openclaw_task(**kwargs):
        execute_calls.append(kwargs)
        return _openclaw_success_result(**kwargs)

    monkeypatch.setattr(openclaw_module, "execute_openclaw_task", fake_execute_openclaw_task)

    backend = OpenClawBackend()
    context = _context(tmp_path, backend="openclaw")

    backend.initialize_run(context)
    result = backend.execute_task(task=_task(), context=context, attempt_run_id="run_001-1")

    assert calls == [
        ("ensure", (context.agent_id, context.model, context.agent_workspace)),
        ("cleanup", context.agent_id),
    ]
    assert [call["agent_id"] for call in execute_calls] == [context.agent_id]
    assert "-rep" not in execute_calls[0]["agent_id"]
    assert result["backend"] == "openclaw"
    assert result["backend_metadata"]["agent_id"] == context.agent_id
    assert "openclaw_lane_id" not in result["backend_metadata"]


def test_openclaw_backend_initializes_repeat_lanes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import benchmark.backends.openclaw as openclaw_module

    acquire_calls: list[tuple[str, dict]] = []
    release_calls: list[str] = []
    ensure_calls: list[tuple[str, str, Path]] = []
    cleanup_calls: list[str] = []

    monkeypatch.setattr(
        openclaw_module,
        "acquire_gateway_lock",
        lambda agent_id, **kwargs: acquire_calls.append((agent_id, kwargs)),
    )
    monkeypatch.setattr(
        openclaw_module,
        "release_gateway_lock",
        lambda agent_id: release_calls.append(agent_id),
    )
    monkeypatch.setattr(
        openclaw_module,
        "ensure_agent_exists",
        lambda agent_id, model, workspace: ensure_calls.append((agent_id, model, workspace)),
    )
    monkeypatch.setattr(
        openclaw_module,
        "cleanup_agent_sessions",
        lambda agent_id: cleanup_calls.append(agent_id),
    )

    backend = OpenClawBackend()
    context = _context(tmp_path, backend="openclaw", metadata=_repeat_metadata(run_workers=2))

    backend.initialize_run(context)

    rep1_workspace = context.run_root / context.run_id / "agent_workspaces" / "rep1"
    rep2_workspace = context.run_root / context.run_id / "agent_workspaces" / "rep2"
    assert acquire_calls == [
        (
            "bench-test-model-rep1",
            {
                "role": "actbench",
                "model": context.model,
                "worker_id": 1,
                "command": "actbench test",
            },
        ),
        (
            "bench-test-model-rep2",
            {
                "role": "actbench",
                "model": context.model,
                "worker_id": 2,
                "command": "actbench test",
            },
        ),
    ]
    assert ensure_calls == [
        ("bench-test-model-rep1", context.model, rep1_workspace),
        ("bench-test-model-rep2", context.model, rep2_workspace),
    ]
    assert cleanup_calls == ["bench-test-model-rep1", "bench-test-model-rep2"]

    backend.finalize_run(context)

    assert release_calls == ["bench-test-model-rep1", "bench-test-model-rep2"]


def test_openclaw_lane_lock_release_continues_after_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import benchmark.backends.openclaw as openclaw_module

    release_calls: list[str] = []

    def fake_release(agent_id: str) -> None:
        release_calls.append(agent_id)
        if agent_id.endswith("rep1"):
            raise OSError("release failed")

    monkeypatch.setattr(openclaw_module, "release_gateway_lock", fake_release)

    backend = OpenClawBackend()
    backend._lane_gateway_locks.extend(["bench-test-model-rep1", "bench-test-model-rep2"])

    backend.finalize_run(_context(tmp_path, backend="openclaw"))

    assert release_calls == ["bench-test-model-rep1", "bench-test-model-rep2"]
    assert backend._lane_gateway_locks == []
    assert backend._lanes == {}


def test_openclaw_backend_routes_parallel_attempts_to_repeat_lanes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import benchmark.backends.openclaw as openclaw_module

    execute_calls: list[dict] = []

    monkeypatch.setattr(openclaw_module, "acquire_gateway_lock", lambda *args, **kwargs: None)
    monkeypatch.setattr(openclaw_module, "release_gateway_lock", lambda *args, **kwargs: None)
    monkeypatch.setattr(openclaw_module, "ensure_agent_exists", lambda *args, **kwargs: None)
    monkeypatch.setattr(openclaw_module, "cleanup_agent_sessions", lambda *args, **kwargs: None)

    def fake_execute_openclaw_task(**kwargs):
        execute_calls.append(kwargs)
        return _openclaw_success_result(**kwargs)

    monkeypatch.setattr(openclaw_module, "execute_openclaw_task", fake_execute_openclaw_task)

    backend = OpenClawBackend()
    base_context = _context(tmp_path, backend="openclaw", metadata=_repeat_metadata(run_workers=2))
    backend.initialize_run(base_context)

    results = []
    for run_index, worker_id in enumerate([1, 2, 1], start=1):
        metadata = {
            **_repeat_metadata(run_workers=2),
            "attempt_run_id": f"run_001-{run_index}",
            "run_index": run_index,
            "run_number": run_index,
            "run_worker_id": worker_id,
            "run_worker_label": f"w{worker_id}",
        }
        attempt_context = _context(tmp_path, backend="openclaw", metadata=metadata)
        results.append(
            backend.execute_task(
                task=_task(),
                context=attempt_context,
                attempt_run_id=f"run_001-{run_index}",
            )
        )

    assert [call["agent_id"] for call in execute_calls] == [
        "bench-test-model-rep1",
        "bench-test-model-rep2",
        "bench-test-model-rep1",
    ]
    assert [call["run_id"] for call in execute_calls] == ["run_001-1", "run_001-2", "run_001-3"]
    assert [result["backend_metadata"]["agent_id"] for result in results] == [
        "bench-test-model-rep1",
        "bench-test-model-rep2",
        "bench-test-model-rep1",
    ]
    assert [result["backend_metadata"]["openclaw_lane_id"] for result in results] == [
        "rep1",
        "rep2",
        "rep1",
    ]
    assert results[0]["backend_metadata"]["openclaw_base_agent_id"] == "bench-test-model"
    assert results[0]["backend_metadata"]["openclaw_lane_workspace"].endswith(
        "/run_001/agent_workspaces/rep1"
    )


def test_openclaw_backend_serializes_same_lane_execution(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import benchmark.backends.openclaw as openclaw_module

    active = 0
    max_active = 0
    active_lock = threading.Lock()
    entered = threading.Event()

    monkeypatch.setattr(openclaw_module, "acquire_gateway_lock", lambda *args, **kwargs: None)
    monkeypatch.setattr(openclaw_module, "release_gateway_lock", lambda *args, **kwargs: None)
    monkeypatch.setattr(openclaw_module, "ensure_agent_exists", lambda *args, **kwargs: None)
    monkeypatch.setattr(openclaw_module, "cleanup_agent_sessions", lambda *args, **kwargs: None)

    def fake_execute_openclaw_task(**kwargs):
        nonlocal active, max_active
        with active_lock:
            active += 1
            max_active = max(max_active, active)
        entered.set()
        time.sleep(0.05)
        with active_lock:
            active -= 1
        return _openclaw_success_result(**kwargs)

    monkeypatch.setattr(openclaw_module, "execute_openclaw_task", fake_execute_openclaw_task)

    backend = OpenClawBackend()
    metadata = {
        **_repeat_metadata(run_workers=2),
        "attempt_run_id": "run_001-1",
        "run_index": 1,
        "run_number": 1,
        "run_worker_id": 1,
        "run_worker_label": "w1",
    }
    base_context = _context(tmp_path, backend="openclaw", metadata=_repeat_metadata(run_workers=2))
    attempt_context = _context(tmp_path, backend="openclaw", metadata=metadata)
    backend.initialize_run(base_context)

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(
            backend.execute_task,
            task=_task(),
            context=attempt_context,
            attempt_run_id="run_001-1",
        )
        assert entered.wait(timeout=1.0)
        second = executor.submit(
            backend.execute_task,
            task=_task(),
            context=attempt_context,
            attempt_run_id="run_001-3",
        )
        first.result(timeout=1.0)
        second.result(timeout=1.0)

    assert max_active == 1


def test_openclaw_artifact_keys_are_attempt_unique(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import lib_agent

    monkeypatch.setattr(lib_agent, "cleanup_agent_sessions", lambda agent_id: None)
    monkeypatch.setattr(
        lib_agent, "prepare_task_workspace", lambda *args, **kwargs: tmp_path / "workspace"
    )
    monkeypatch.setattr(lib_agent, "_build_clean_cwd", lambda *args, **kwargs: tmp_path)
    monkeypatch.setattr(lib_agent, "_load_transcript", lambda *args, **kwargs: [])
    monkeypatch.setattr(
        lib_agent.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args=[], returncode=0, stdout="done", stderr=""
        ),
    )
    monkeypatch.setattr(lib_agent.uuid, "uuid4", lambda: SimpleNamespace(hex="fixeduuid"))

    first = lib_agent.execute_openclaw_task(
        task=_task(),
        agent_id="bench-test-model-rep1",
        model_id="test/model",
        run_id="run_001-1",
        timeout_multiplier=1.0,
        skill_dir=ROOT,
    )
    second = lib_agent.execute_openclaw_task(
        task=_task(),
        agent_id="bench-test-model-rep2",
        model_id="test/model",
        run_id="run_001-2",
        timeout_multiplier=1.0,
        skill_dir=ROOT,
    )

    assert first["training_artifact_key"] != second["training_artifact_key"]
    assert "run_001-1" in first["training_artifact_key"]
    assert "run_001-2" in second["training_artifact_key"]


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
    history_calls: list[dict] = []
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
                "request_count": 1,
            },
        }

    def fake_history(**kwargs):
        history_calls.append(kwargs)
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
    assert result["backend_metadata"]["usage_source"] == "qwenpaw_event"
    assert result["backend_metadata"]["usage_delta_contamination_risk"] is False
    assert result["usage"]["input_tokens"] == 20
    assert result["usage"]["output_tokens"] == 10
    assert result["usage"]["total_tokens"] == 30
    assert result["usage"]["cost_usd"] == 0.25
    assert result["usage"]["request_count"] == 2
    assert result["transcript"][1]["message"]["content"][0]["type"] == "toolCall"
    assert [call["prompt"] for call in process_calls] == ["first", "second"]
    assert len({call["session_id"] for call in process_calls}) == 1
    assert all(call["agent_id"] == "actbench-test-agent" for call in process_calls)
    chat_scope = process_calls[0]["chat_scope"]
    assert all(call["chat_scope"] == chat_scope for call in process_calls)
    assert history_calls[0]["chat_scope"] == chat_scope
    assert result["backend_metadata"]["qwenpaw_user_id"] == chat_scope.user_id
    assert result["backend_metadata"]["qwenpaw_channel"] == chat_scope.channel
    assert chat_scope.user_id != "actbench"
    assert chat_scope.channel != "console"
    workspace = Path(result["workspace"])
    assert create_calls[0]["workspace"] == workspace
    assert (workspace / "README.md").read_text(encoding="utf-8") == "hello"
    assert (workspace / ".bootstrap_completed").exists()
    assert not (workspace / "BOOTSTRAP.md").exists()
    assert delete_calls == ["actbench-test-agent"]


def test_qwenpaw_process_and_history_use_attempt_scoped_chat_scope(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import benchmark.backends.qwenpaw as qwenpaw_module
    from benchmark.backends.qwenpaw import QwenPawBackend, QwenPawChatScope, QwenPawConfig

    backend = QwenPawBackend()
    config = QwenPawConfig(
        base_url="http://qwenpaw.test",
        api_key="token",
        timeout_seconds=None,
        agent_prefix="actbench",
        delete_agent=True,
        headless_tool_guard=None,
        usage_delta_enabled=True,
    )
    chat_scope = QwenPawChatScope(
        user_id="actbench-run-001-1-task-fake-scope",
        channel="console-run-001-1-scope",
    )
    process_payloads: list[dict] = []
    requested_urls: list[str] = []

    def fake_post_sse_json(url, **kwargs):
        process_payloads.append(kwargs["payload"])
        return {"output": [{"content": [{"type": "text", "text": "answer"}]}]}

    def fake_request_json(url, **kwargs):
        requested_urls.append(url)
        if url.endswith("/chats/quoted-chat"):
            return {"messages": [{"role": "assistant", "content": "answer"}]}
        return [{"id": "quoted-chat", "session_id": "session-1"}]

    monkeypatch.setattr(qwenpaw_module, "_post_sse_json", fake_post_sse_json)
    monkeypatch.setattr(qwenpaw_module, "_request_json", fake_request_json)

    backend._post_agent_process(
        config=config,
        agent_id="agent-1",
        task=_task(),
        session_id="session-1",
        chat_scope=chat_scope,
        prompt="hello",
        timeout_seconds=1.0,
    )
    messages = backend._fetch_chat_history_messages(
        config=config,
        agent_id="agent-1",
        session_id="session-1",
        chat_scope=chat_scope,
        timeout_seconds=1.0,
    )

    assert process_payloads[0]["user_id"] == chat_scope.user_id
    assert process_payloads[0]["channel"] == chat_scope.channel
    assert process_payloads[0]["request_context"]["user_id"] == chat_scope.user_id
    assert process_payloads[0]["request_context"]["channel"] == chat_scope.channel
    assert messages == [{"role": "assistant", "content": "answer"}]
    assert requested_urls[0].startswith("http://qwenpaw.test/api/agents/agent-1/chats")
    assert f"user_id={chat_scope.user_id}" in requested_urls[0]
    assert f"channel={chat_scope.channel}" in requested_urls[0]


def test_qwenpaw_backend_uses_token_usage_delta_when_event_usage_missing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import benchmark.backends.qwenpaw as qwenpaw_module
    from benchmark.backends.qwenpaw import QwenPawBackend

    _configure_qwenpaw_test_env(monkeypatch)
    monkeypatch.setenv("ACTBENCH_QWENPAW_USAGE_DELTA", "1")
    backend = QwenPawBackend()
    monkeypatch.setattr(backend, "_check_health", lambda config: None)
    monkeypatch.setattr(backend, "_create_task_agent", lambda **kwargs: "actbench-test-agent")
    monkeypatch.setattr(
        backend,
        "_post_agent_process",
        lambda **kwargs: {"output": [{"content": [{"type": "text", "text": "answer"}]}]},
    )
    monkeypatch.setattr(
        backend,
        "_fetch_chat_history_messages",
        lambda **kwargs: [{"role": "assistant", "content": "answer"}],
    )
    monkeypatch.setattr(backend, "_delete_task_agent", lambda **kwargs: None)
    snapshots = [
        [
            {
                "date": "2026-07-12",
                "provider_id": "test",
                "model": "model",
                "prompt_tokens": 100,
                "completion_tokens": 50,
                "call_count": 10,
            }
        ],
        [
            {
                "date": "2026-07-12",
                "provider_id": "test",
                "model": "model",
                "prompt_tokens": 125,
                "completion_tokens": 60,
                "call_count": 11,
            }
        ],
    ]

    def fake_request_json(url, **kwargs):
        assert url.startswith("http://qwenpaw.test/api/token-usage/details")
        return snapshots.pop(0)

    monkeypatch.setattr(qwenpaw_module, "_request_json", fake_request_json)
    context = _context(tmp_path, backend="qwenpaw")

    backend.initialize_run(context)
    result = backend.execute_task(task=_task(), context=context, attempt_run_id="run_001-1")

    assert result["status"] == "success"
    assert result["usage"]["input_tokens"] == 25
    assert result["usage"]["output_tokens"] == 10
    assert result["usage"]["total_tokens"] == 35
    assert result["usage"]["request_count"] == 1
    assert result["backend_metadata"]["usage_source"] == "qwenpaw_token_usage_delta"
    assert result["backend_metadata"]["usage_delta_contamination_risk"] is True
    assert snapshots == []


def test_qwenpaw_backend_succeeds_when_token_usage_delta_unavailable(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import benchmark.backends.qwenpaw as qwenpaw_module
    from benchmark.backends.qwenpaw import QwenPawBackend, QwenPawRequestError

    _configure_qwenpaw_test_env(monkeypatch)
    monkeypatch.setenv("ACTBENCH_QWENPAW_USAGE_DELTA", "1")
    backend = QwenPawBackend()
    monkeypatch.setattr(backend, "_check_health", lambda config: None)
    monkeypatch.setattr(backend, "_create_task_agent", lambda **kwargs: "actbench-test-agent")
    monkeypatch.setattr(
        backend,
        "_post_agent_process",
        lambda **kwargs: {"output": [{"content": [{"type": "text", "text": "answer"}]}]},
    )
    monkeypatch.setattr(
        backend,
        "_fetch_chat_history_messages",
        lambda **kwargs: [{"role": "assistant", "content": "answer"}],
    )
    monkeypatch.setattr(backend, "_delete_task_agent", lambda **kwargs: None)
    monkeypatch.setattr(
        qwenpaw_module,
        "_request_json",
        lambda *args, **kwargs: (_ for _ in ()).throw(QwenPawRequestError("usage down")),
    )
    context = _context(tmp_path, backend="qwenpaw")

    backend.initialize_run(context)
    result = backend.execute_task(task=_task(), context=context, attempt_run_id="run_001-1")

    assert result["status"] == "success"
    assert result["usage"]["total_tokens"] == 0
    assert result["usage"]["request_count"] == 1
    assert result["backend_metadata"]["usage_source"] == "unavailable"


def test_qwenpaw_backend_disables_token_usage_delta_under_parallel_workers(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import benchmark.backends.qwenpaw as qwenpaw_module
    from benchmark.backends.qwenpaw import QwenPawBackend

    _configure_qwenpaw_test_env(monkeypatch)
    monkeypatch.setenv("ACTBENCH_QWENPAW_USAGE_DELTA", "1")
    backend = QwenPawBackend()
    monkeypatch.setattr(backend, "_check_health", lambda config: None)
    monkeypatch.setattr(backend, "_create_task_agent", lambda **kwargs: "actbench-test-agent")
    monkeypatch.setattr(
        backend,
        "_post_agent_process",
        lambda **kwargs: {"output": [{"content": [{"type": "text", "text": "answer"}]}]},
    )
    monkeypatch.setattr(
        backend,
        "_fetch_chat_history_messages",
        lambda **kwargs: [{"role": "assistant", "content": "answer"}],
    )
    monkeypatch.setattr(backend, "_delete_task_agent", lambda **kwargs: None)

    usage_snapshot_calls: list[str] = []

    def fake_request_json(url, **kwargs):
        usage_snapshot_calls.append(url)
        raise AssertionError("aggregate usage snapshot should be disabled under parallel workers")

    monkeypatch.setattr(qwenpaw_module, "_request_json", fake_request_json)
    context = _context(
        tmp_path,
        backend="qwenpaw",
        metadata={
            "run_workers": 2,
            "run_worker_id": 1,
            "run_worker_label": "w1",
            "run_index": 1,
        },
    )

    backend.initialize_run(context)
    result = backend.execute_task(task=_task(), context=context, attempt_run_id="run_001-1")

    assert result["status"] == "success"
    assert usage_snapshot_calls == []
    assert result["usage"]["total_tokens"] == 0
    assert result["usage"]["request_count"] == 1
    assert result["backend_metadata"]["usage_source"] == "unavailable"
    assert result["backend_metadata"]["usage_delta_contamination_risk"] is False
    assert result["backend_metadata"]["usage_delta_disabled_reason"] == "parallel_run_workers"


def test_qwenpaw_backend_keeps_event_usage_under_parallel_workers(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import benchmark.backends.qwenpaw as qwenpaw_module
    from benchmark.backends.qwenpaw import QwenPawBackend

    _configure_qwenpaw_test_env(monkeypatch)
    monkeypatch.setenv("ACTBENCH_QWENPAW_USAGE_DELTA", "1")
    backend = QwenPawBackend()
    monkeypatch.setattr(backend, "_check_health", lambda config: None)
    monkeypatch.setattr(backend, "_create_task_agent", lambda **kwargs: "actbench-test-agent")
    monkeypatch.setattr(
        backend,
        "_post_agent_process",
        lambda **kwargs: {
            "output": [{"content": [{"type": "text", "text": "answer"}]}],
            "usage": {
                "prompt_tokens": 11,
                "completion_tokens": 7,
                "total_tokens": 18,
                "call_count": 1,
            },
        },
    )
    monkeypatch.setattr(
        backend,
        "_fetch_chat_history_messages",
        lambda **kwargs: [{"role": "assistant", "content": "answer"}],
    )
    monkeypatch.setattr(backend, "_delete_task_agent", lambda **kwargs: None)

    usage_snapshot_calls: list[str] = []

    def fake_request_json(url, **kwargs):
        usage_snapshot_calls.append(url)
        raise AssertionError("aggregate usage snapshot should be disabled under parallel workers")

    monkeypatch.setattr(qwenpaw_module, "_request_json", fake_request_json)
    context = _context(
        tmp_path,
        backend="qwenpaw",
        metadata={
            "run_workers": 2,
            "run_worker_id": 2,
            "run_worker_label": "w2",
            "run_index": 2,
        },
    )

    backend.initialize_run(context)
    result = backend.execute_task(task=_task(), context=context, attempt_run_id="run_001-2")

    assert result["status"] == "success"
    assert usage_snapshot_calls == []
    assert result["usage"]["input_tokens"] == 11
    assert result["usage"]["output_tokens"] == 7
    assert result["usage"]["total_tokens"] == 18
    assert result["usage"]["request_count"] == 1
    assert result["backend_metadata"]["usage_source"] == "qwenpaw_event"
    assert result["backend_metadata"]["usage_delta_disabled_reason"] == "parallel_run_workers"


def test_qwenpaw_usage_parsing_accepts_nested_and_aggregate_shapes() -> None:
    from benchmark.backends.qwenpaw import (
        _event_usage,
        _normalize_qwenpaw_usage,
        _qwenpaw_usage_rows,
        _sum_usage_rows,
        _usage_row_matches_model,
    )

    assert _event_usage({"metadata": {"usage": {"prompt_tokens": 1}}}) == {"prompt_tokens": 1}
    assert _event_usage({"output": [{"usage": {"completion_tokens": 2}}]}) == {
        "completion_tokens": 2
    }
    combined = _event_usage(
        {
            "output": [
                {"usage": {"prompt_tokens": 1, "total_tokens": 1}},
                {"usage": {"completion_tokens": 2, "total_tokens": 2}},
            ]
        }
    )
    assert combined is not None
    assert combined["input_tokens"] == 1
    assert combined["output_tokens"] == 2
    assert combined["total_tokens"] == 3
    normalized = _normalize_qwenpaw_usage(
        {"inputTokens": "3", "outputTokens": "4", "totalTokens": "7", "callCount": "2"},
        request_count=1,
    )
    assert normalized["input_tokens"] == 3
    assert normalized["output_tokens"] == 4
    assert normalized["total_tokens"] == 7
    assert normalized["request_count"] == 2

    rows = _qwenpaw_usage_rows(
        {
            "by_model": {
                "test:model": {
                    "provider_id": "test",
                    "model": "model",
                    "prompt_tokens": 10,
                    "completion_tokens": 5,
                    "call_count": 1,
                }
            }
        }
    )
    assert _usage_row_matches_model(rows[0], provider_id="test", model="model")
    assert not _usage_row_matches_model(
        {"model_key": "other/model", "prompt_tokens": 99}, provider_id="test", model="model"
    )
    summed = _sum_usage_rows(rows)
    assert summed["input_tokens"] == 10
    assert summed["output_tokens"] == 5
    assert summed["total_tokens"] == 15
    assert summed["request_count"] == 1

    nested_rows = _qwenpaw_usage_rows(
        {"by_model": {}, "data": [{"model": "model", "prompt_tokens": 3, "completion_tokens": 4}]}
    )
    assert nested_rows == [{"model": "model", "prompt_tokens": 3, "completion_tokens": 4}]


class _FakeSseResponse:
    def __init__(self, lines: list[str]) -> None:
        self._lines = lines

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def __iter__(self):
        return iter(line.encode("utf-8") for line in self._lines)


def test_qwenpaw_sse_keeps_early_text_and_usage(monkeypatch: pytest.MonkeyPatch) -> None:
    import benchmark.backends.qwenpaw as qwenpaw_module
    from benchmark.backends.qwenpaw import _event_usage, _extract_output_text, _post_sse_json

    lines = [
        f"data: {json.dumps({'text': 'early '})}\n",
        f"data: {json.dumps({'usage': {'prompt_tokens': 2, 'total_tokens': 2}})}\n",
        f"data: {json.dumps({'usage': {'completion_tokens': 3, 'total_tokens': 3}})}\n",
        f"data: {json.dumps({'status': 'done'})}\n",
    ]
    monkeypatch.setattr(
        qwenpaw_module.urllib.request,
        "urlopen",
        lambda *args, **kwargs: _FakeSseResponse(lines),
    )

    event = _post_sse_json(
        "http://qwenpaw.test/api/agent/process",
        timeout_seconds=10.0,
        api_key=None,
        payload={"task": "hello"},
    )

    assert _extract_output_text(event) == "early "
    usage = _event_usage(event)
    assert usage is not None
    assert usage["input_tokens"] == 2
    assert usage["output_tokens"] == 3
    assert usage["total_tokens"] == 5


def test_qwenpaw_sse_enforces_total_deadline(monkeypatch: pytest.MonkeyPatch) -> None:
    import benchmark.backends.qwenpaw as qwenpaw_module
    from benchmark.backends.qwenpaw import QwenPawTimeoutError, _post_sse_json

    monotonic_values = iter([0.0, 0.5, 1.1])
    monkeypatch.setattr(qwenpaw_module.time, "monotonic", lambda: next(monotonic_values))
    monkeypatch.setattr(
        qwenpaw_module.urllib.request,
        "urlopen",
        lambda *args, **kwargs: _FakeSseResponse([f"data: {json.dumps({'text': 'still running'})}\n"]),
    )

    with pytest.raises(QwenPawTimeoutError):
        _post_sse_json(
            "http://qwenpaw.test/api/agent/process",
            timeout_seconds=1.0,
            api_key=None,
            payload={"task": "hello"},
        )


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
        usage_delta_enabled=True,
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


def test_qwenpaw_process_fallback_preserves_prompt_output_alignment(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from benchmark.backends.qwenpaw import QwenPawBackend, QwenPawRequestError

    _configure_qwenpaw_test_env(monkeypatch)
    backend = QwenPawBackend()
    monkeypatch.setattr(backend, "_check_health", lambda config: None)
    monkeypatch.setattr(backend, "_create_task_agent", lambda **kwargs: "actbench-test-agent")

    def fake_process(**kwargs):
        if kwargs["prompt"] == "first":
            return {"output": []}
        return {"output": [{"content": [{"type": "text", "text": "second answer"}]}]}

    monkeypatch.setattr(backend, "_post_agent_process", fake_process)
    monkeypatch.setattr(
        backend,
        "_fetch_chat_history_messages",
        lambda **kwargs: (_ for _ in ()).throw(QwenPawRequestError("history unavailable")),
    )
    monkeypatch.setattr(backend, "_delete_task_agent", lambda **kwargs: None)
    context = _context(tmp_path, backend="qwenpaw")
    task = _task(frontmatter={"sessions": ["first", "second"]})

    backend.initialize_run(context)
    result = backend.execute_task(task=task, context=context, attempt_run_id="run_001-1")

    assert result["status"] == "success"
    assert [entry["message"]["role"] for entry in result["transcript"]] == [
        "user",
        "user",
        "assistant",
    ]
    assert result["transcript"][0]["message"]["content"] == ["first"]
    assert result["transcript"][1]["message"]["content"] == ["second"]
    assert result["transcript"][2]["message"]["content"] == [
        {"type": "text", "text": "second answer"}
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
    monkeypatch.setattr(
        backend, "_delete_task_agent", lambda **kwargs: delete_calls.append(kwargs["agent_id"])
    )
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
    assert result["backend_metadata"]["hermes_home"] == str(calls[0]["config"].hermes_home)
    assert calls[0]["config"].hermes_home == Path(result["workspace"]).parent / "hermes_home"
    assert (calls[0]["config"].hermes_home / "config.yaml").exists()
    assert (Path(result["workspace"]) / "README.md").read_text(encoding="utf-8") == "hello"


def test_hermes_backend_uses_attempt_scoped_home(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import benchmark.backends.hermes as hermes_module
    from benchmark.backends.hermes import HermesBackend

    _configure_hermes_test_env(monkeypatch, mcp_enabled=False)
    monkeypatch.setenv("ACTBENCH_HERMES_HOME_ROOT", str(tmp_path / "hermes_homes"))
    monkeypatch.setattr(hermes_module.shutil, "which", lambda _: "/usr/bin/hermes")
    backend = HermesBackend()
    calls: list[dict] = []

    def fake_run(**kwargs):
        calls.append(kwargs)
        kwargs["usage_file"].write_text(
            json.dumps({"input_tokens": 1, "output_tokens": 1}),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(
            args=["hermes"], returncode=0, stdout="done\n", stderr=""
        )

    monkeypatch.setattr(backend, "_run_hermes_subprocess", fake_run)
    context = _context(tmp_path, backend="hermes")

    backend.initialize_run(context)
    first_task = _task()
    second_task = _task()
    second_task.task_id = "task/fake:two"
    first = backend.execute_task(task=first_task, context=context, attempt_run_id="run_001-1")
    second = backend.execute_task(task=second_task, context=context, attempt_run_id="run_001-1")

    homes = [call["config"].hermes_home for call in calls]
    usage_files = [call["usage_file"] for call in calls]
    assert len(set(homes)) == 2
    assert len(set(usage_files)) == 2
    assert homes == [
        tmp_path / "hermes_homes" / "run_001" / "task_fake" / "run_001-1" / "hermes_home",
        tmp_path / "hermes_homes" / "run_001" / "task_fake_two" / "run_001-1" / "hermes_home",
    ]
    assert [
        first["backend_metadata"]["hermes_home"],
        second["backend_metadata"]["hermes_home"],
    ] == [
        str(homes[0]),
        str(homes[1]),
    ]
    assert all((home / "config.yaml").exists() for home in homes)


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
    export_calls: list[dict] = []

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
        export_calls.append(kwargs)
        return subprocess.CompletedProcess(
            args=["opencode", "export", kwargs["session_id"]],
            returncode=0,
            stdout=json.dumps(
                {
                    "info": {"id": kwargs["session_id"]},
                    "messages": [
                        {
                            "info": {
                                "role": "user",
                                "id": "msg_user",
                                "sessionID": kwargs["session_id"],
                            },
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
    assert export_calls[0]["config"].opencode_home == calls[0]["config"].opencode_home
    assert result["backend_metadata"]["opencode_home"] == str(calls[0]["config"].opencode_home)
    assert result["backend_metadata"]["opencode_db"] == str(calls[0]["config"].db_path)
    assert calls[0]["config"].opencode_home == Path(result["workspace"]).parent / "opencode_home"
    assert (calls[0]["config"].opencode_home / "actbench-config.json").exists()
    assert (Path(result["workspace"]) / "README.md").read_text(encoding="utf-8") == "hello"


def test_opencode_backend_uses_attempt_scoped_home(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import benchmark.backends.opencode as opencode_module
    from benchmark.backends.opencode import OpenCodeBackend

    _configure_opencode_test_env(monkeypatch, mcp_enabled=False)
    monkeypatch.setenv("ACTBENCH_OPENCODE_HOME_ROOT", str(tmp_path / "opencode_homes"))
    monkeypatch.setattr(opencode_module.shutil, "which", lambda _: "/usr/bin/opencode")
    backend = OpenCodeBackend()
    calls: list[dict] = []
    export_calls: list[dict] = []

    def fake_run(**kwargs):
        calls.append(kwargs)
        session_id = f"ses_{len(calls)}"
        return subprocess.CompletedProcess(
            args=["opencode"],
            returncode=0,
            stdout=(
                f'{{"type":"text","sessionID":"{session_id}",'
                '"part":{"type":"text","text":"done"}}\n'
            ),
            stderr="",
        )

    def fake_export(**kwargs):
        export_calls.append(kwargs)
        return subprocess.CompletedProcess(
            args=["opencode", "export", kwargs["session_id"]],
            returncode=0,
            stdout=json.dumps(
                {
                    "info": {"id": kwargs["session_id"]},
                    "messages": [
                        {
                            "info": {
                                "role": "assistant",
                                "id": "msg_assistant",
                                "sessionID": kwargs["session_id"],
                            },
                            "parts": [{"type": "text", "id": "txt_1", "text": "done"}],
                        }
                    ],
                }
            ),
            stderr="",
        )

    monkeypatch.setattr(backend, "_run_opencode_subprocess", fake_run)
    monkeypatch.setattr(backend, "_run_opencode_export", fake_export)
    context = _context(tmp_path, backend="opencode")

    backend.initialize_run(context)
    first_task = _task()
    second_task = _task()
    second_task.task_id = "task/fake:two"
    first = backend.execute_task(task=first_task, context=context, attempt_run_id="run_001-1")
    second = backend.execute_task(task=second_task, context=context, attempt_run_id="run_001-1")

    homes = [call["config"].opencode_home for call in calls]
    dbs = [call["config"].db_path for call in calls]
    assert len(set(homes)) == 2
    assert len(set(dbs)) == 2
    assert homes == [
        tmp_path / "opencode_homes" / "run_001" / "task_fake" / "run_001-1" / "opencode_home",
        tmp_path / "opencode_homes" / "run_001" / "task_fake_two" / "run_001-1" / "opencode_home",
    ]
    assert [
        first["backend_metadata"]["opencode_home"],
        second["backend_metadata"]["opencode_home"],
    ] == [
        str(homes[0]),
        str(homes[1]),
    ]
    assert [export_call["config"].opencode_home for export_call in export_calls] == homes
    assert all((home / "actbench-config.json").exists() for home in homes)


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


def test_claudecode_transcript_fallback_does_not_persist_thinking_only_stream() -> None:
    from benchmark.backends.claudecode import _extract_claudecode_transcript

    stdout = json.dumps(
        {
            "type": "assistant",
            "message": {
                "role": "assistant",
                "content": [{"type": "thinking", "thinking": "private reasoning"}],
            },
        }
    )

    transcript, source, metadata, usage = _extract_claudecode_transcript(
        effective_prompt="Think privately.",
        stdout=stdout,
        redactions=[],
    )

    assert source == "claudecode_stream_json"
    assert metadata["fallback_reason"] == "unusable_stream_transcript"
    assert metadata["transcript_messages"] == 1
    assert usage["request_count"] == 1
    assert "private reasoning" not in json.dumps(transcript)


def test_claudecode_transcript_helpers_handle_terminal_errors_and_edge_shapes() -> None:
    from benchmark.backends.claudecode import (
        _extract_claudecode_transcript,
        _normalize_claudecode_stream_to_transcript,
        _redact_text_values,
    )

    stdout = "\n".join(
        [
            json.dumps(
                {
                    "type": "assistant",
                    "message": {
                        "role": "assistant",
                        "content": [
                            {
                                "type": "tool_use",
                                "id": "tool_1",
                                "name": "mcp__actbench__actbench_read_file",
                                "input": '["not", "an", "object"]',
                            }
                        ],
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
                                "is_error": "false",
                                "content": "ok",
                            }
                        ],
                    },
                }
            ),
            json.dumps(
                {
                    "type": "result",
                    "subtype": "error_max_turns",
                    "is_error": True,
                    "message": "limit reached",
                    "num_turns": 2,
                }
            ),
        ]
    )

    transcript, source, metadata, _usage = _extract_claudecode_transcript(
        effective_prompt="Read the file.",
        stdout=stdout,
        redactions=[],
    )
    assert source == "claudecode_stream_json"
    assert metadata["terminal_error"] == "error_max_turns: limit reached"
    tool_call_blocks = [
        item
        for entry in transcript
        for item in entry.get("message", {}).get("content", [])
        if isinstance(item, dict) and item.get("type") == "toolCall"
    ]
    assert tool_call_blocks[0]["arguments"] == {"raw": ["not", "an", "object"]}
    tool_result_blocks = [
        item
        for entry in transcript
        for item in entry.get("message", {}).get("content", [])
        if isinstance(item, dict) and item.get("type") == "toolResult"
    ]
    assert tool_result_blocks[0]["isError"] is False

    direct_transcript = _normalize_claudecode_stream_to_transcript(
        effective_prompt="Call tool.",
        events=[
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {
                            "type": "tool_use",
                            "name": "mcp__actbench__actbench_write_file",
                            "input": ["raw", "list"],
                        }
                    ]
                },
            }
        ],
    )
    direct_call = direct_transcript[1]["message"]["content"][0]
    assert direct_call["arguments"] == {"raw": ["raw", "list"]}

    raw = '{"headers":{"Authorization":"Bearer should-not-leak"}}'
    redacted = _redact_text_values(raw, [])
    assert "should-not-leak" not in redacted
    assert "Bearer [redacted]" in redacted


def test_claudecode_test_env_clears_tool_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ACTBENCH_CLAUDECODE_ALLOWED_TOOLS", "Read")
    monkeypatch.setenv("ACTBENCH_CLAUDECODE_TOOLS", "Read")

    _configure_claudecode_test_env(monkeypatch, mcp_enabled=True)

    assert "ACTBENCH_CLAUDECODE_ALLOWED_TOOLS" not in os.environ
    assert "ACTBENCH_CLAUDECODE_TOOLS" not in os.environ


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
    assert not (backend._config.claudecode_home / "actbench-claudecode.json").exists()


def test_claudecode_mcp_enabled_disables_builtin_tools_by_default(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import benchmark.backends.claudecode as claudecode_module
    from benchmark.backends.claudecode import ClaudeCodeBackend

    _configure_claudecode_test_env(monkeypatch, mcp_enabled=True)
    monkeypatch.setattr(claudecode_module.shutil, "which", lambda _: "/usr/bin/claude")
    backend = ClaudeCodeBackend()

    config = backend._load_config(_context(tmp_path, backend="claudecode"))

    assert config.mcp_enabled is True
    assert config.builtin_tools == ""

    monkeypatch.setenv("ACTBENCH_CLAUDECODE_TOOLS", "Read,Grep")
    config = backend._load_config(_context(tmp_path, backend="claudecode"))
    assert config.builtin_tools == "Read,Grep"


def test_claudecode_subprocess_uses_headless_flags_allowed_tools_and_isolated_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import benchmark.backends.claudecode as claudecode_module
    from benchmark.backends.claudecode import ClaudeCodeBackend, ClaudeCodeConfig

    monkeypatch.setenv("ACTBENCH_MCP_ADMIN_TOKEN", "secret-token")
    captured: dict[str, object] = {}

    def fake_run_with_process_group(cmd, **kwargs):
        captured["cmd"] = cmd
        captured.update(kwargs)
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(
        claudecode_module, "_run_subprocess_with_process_group", fake_run_with_process_group
    )
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
    assert "Prompt text" not in cmd
    assert captured["input_text"] == "Prompt text"
    assert "--input-format" in cmd and cmd[cmd.index("--input-format") + 1] == "text"
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
    assert (
        result["backend_metadata"]["claudecode_session_id"]
        == "00000000-0000-4000-8000-000000000001"
    )
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
    assert result["backend_metadata"]["claudecode_home"] == str(calls[0]["config"].claudecode_home)
    assert result["backend_metadata"]["claudecode_config_dir"] == str(calls[0]["config"].config_dir)
    assert (
        calls[0]["config"].claudecode_home == Path(result["workspace"]).parent / "claudecode_home"
    )
    assert (calls[0]["config"].claudecode_home / "actbench-claudecode.json").exists()
    assert (Path(result["workspace"]) / "README.md").read_text(encoding="utf-8") == "hello"


def test_claudecode_backend_uses_attempt_scoped_home(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import benchmark.backends.claudecode as claudecode_module
    from benchmark.backends.claudecode import ClaudeCodeBackend

    _configure_claudecode_test_env(monkeypatch, mcp_enabled=False)
    monkeypatch.setenv("ACTBENCH_CLAUDECODE_HOME_ROOT", str(tmp_path / "claudecode_homes"))
    monkeypatch.setattr(claudecode_module.shutil, "which", lambda _: "/usr/bin/claude")
    backend = ClaudeCodeBackend()
    calls: list[dict] = []

    def fake_run(**kwargs):
        calls.append(kwargs)
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
    first_task = _task()
    second_task = _task()
    second_task.task_id = "task/fake:two"
    first = backend.execute_task(task=first_task, context=context, attempt_run_id="run_001-1")
    second = backend.execute_task(task=second_task, context=context, attempt_run_id="run_001-1")

    homes = [call["config"].claudecode_home for call in calls]
    config_dirs = [call["config"].config_dir for call in calls]
    assert len(set(homes)) == 2
    assert len(set(config_dirs)) == 2
    assert homes == [
        tmp_path / "claudecode_homes" / "run_001" / "task_fake" / "run_001-1" / "claudecode_home",
        tmp_path
        / "claudecode_homes"
        / "run_001"
        / "task_fake_two"
        / "run_001-1"
        / "claudecode_home",
    ]
    assert [
        first["backend_metadata"]["claudecode_home"],
        second["backend_metadata"]["claudecode_home"],
    ] == [
        str(homes[0]),
        str(homes[1]),
    ]
    assert all((home / "actbench-claudecode.json").exists() for home in homes)


def test_claudecode_terminal_result_error_becomes_backend_error(
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
            args=["claude"],
            returncode=0,
            stdout="\n".join(
                [
                    json.dumps(
                        {
                            "type": "assistant",
                            "message": {"content": [{"type": "text", "text": "partial"}]},
                        }
                    ),
                    json.dumps(
                        {
                            "type": "result",
                            "subtype": "error_during_execution",
                            "is_error": True,
                            "message": "boom",
                        }
                    ),
                ]
            ),
            stderr="",
        ),
    )
    context = _context(tmp_path, backend="claudecode")

    backend.initialize_run(context)
    result = backend.execute_task(task=_task(), context=context, attempt_run_id="run_001-1")

    assert result["status"] == "error"
    assert result["exit_code"] == -1
    assert "error_during_execution" in result["stderr"]
    assert result["backend_metadata"]["transcript_extraction"]["terminal_error"] == (
        "error_during_execution: boom"
    )


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
    monkeypatch.setattr(claudecode_module, "check_gateway_admin_health", lambda **kwargs: None)
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
    configs: list[object] = []

    def fake_run(**kwargs):
        prompts.append(kwargs["prompt"])
        mcp_config_paths.append(kwargs["mcp_config_path"])
        configs.append(kwargs["config"])
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
        "mcpServers": {"actbench": {"type": "http", "url": "http://host.docker.internal:8765/mcp"}}
    }
    assert unregistered == [
        {
            "mcp_url": "http://127.0.0.1:8765/mcp",
            "context_id": "ctx-123",
            "admin_token": "secret-token",
        }
    ]
    assert mcp_config_paths[0].parent == configs[0].mcp_config_dir
    assert result["backend_metadata"]["claudecode_home"] == str(configs[0].claudecode_home)
    assert result["backend_metadata"]["mcp_config_path"] == str(mcp_config_paths[0])
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


def test_opencode_mcp_missing_trace_recovery_keeps_existing_results() -> None:
    from benchmark.backends.opencode import (
        _mcp_gateway_traces_to_transcript,
        _missing_mcp_trace_transcript,
    )

    trace_transcript = _mcp_gateway_traces_to_transcript(
        [
            {"sequence": 1, "name": "actbench_read_file", "result": {"text": "already there"}},
            {"sequence": 2, "name": "actbench_write_file", "result": {"text": "missing"}},
        ]
    )
    existing = [trace_transcript[1]]

    missing = _missing_mcp_trace_transcript(
        transcript=existing,
        trace_transcript=trace_transcript,
    )

    assert missing == trace_transcript[2:]


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
    monkeypatch.setattr(opencode_module, "check_gateway_admin_health", lambda **kwargs: None)
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
                            "info": {
                                "role": "user",
                                "id": "msg_user",
                                "sessionID": kwargs["session_id"],
                            },
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
    admin_checked: list[dict] = []
    monkeypatch.setattr(
        hermes_module, "check_gateway_health", lambda **kwargs: checked.append(kwargs)
    )
    monkeypatch.setattr(
        hermes_module,
        "check_gateway_admin_health",
        lambda **kwargs: admin_checked.append(kwargs),
    )
    monkeypatch.setattr(
        hermes_module,
        "start_gateway_subprocess",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("should not autostart")),
    )
    backend = HermesBackend()

    backend.initialize_run(_context(tmp_path, backend="hermes"))

    assert checked == [{"host": "127.0.0.1", "port": 8765}]
    assert admin_checked == [{"mcp_url": "http://127.0.0.1:8765/mcp", "admin_token": None}]
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
    monkeypatch.setattr(hermes_module, "check_gateway_admin_health", lambda **kwargs: None)
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
    monkeypatch.setattr(
        hermes_module,
        "get_gateway_context_traces",
        lambda **kwargs: {"status": "ok", "traces": []},
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
    monkeypatch.setattr(hermes_module, "check_gateway_admin_health", lambda **kwargs: None)
    monkeypatch.setattr(
        hermes_module, "register_gateway_context", lambda **kwargs: {"status": "ok"}
    )
    unregistered: list[dict] = []
    monkeypatch.setattr(
        hermes_module,
        "unregister_gateway_context",
        lambda **kwargs: unregistered.append(kwargs) or {"status": "ok", "removed": True},
    )
    monkeypatch.setattr(
        hermes_module,
        "get_gateway_context_traces",
        lambda **kwargs: {"status": "ok", "traces": []},
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
    monkeypatch.setattr(hermes_module, "check_gateway_admin_health", lambda **kwargs: None)
    monkeypatch.setattr(
        hermes_module, "register_gateway_context", lambda **kwargs: {"status": "ok"}
    )
    monkeypatch.setattr(
        hermes_module, "unregister_gateway_context", lambda **kwargs: {"status": "ok"}
    )
    monkeypatch.setattr(
        hermes_module,
        "get_gateway_context_traces",
        lambda **kwargs: {"status": "ok", "traces": []},
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
    admin_checked: list[dict] = []
    monkeypatch.setattr(
        openagent_module,
        "check_gateway_health",
        lambda **kwargs: checked.append(kwargs),
    )
    monkeypatch.setattr(
        openagent_module,
        "check_gateway_admin_health",
        lambda **kwargs: admin_checked.append(kwargs),
    )
    monkeypatch.setattr(
        openagent_module,
        "start_gateway_subprocess",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("should not autostart")),
    )

    backend.initialize_run(_context(tmp_path, backend="openagent"))

    assert checked == [{"host": "127.0.0.1", "port": 8765}]
    assert admin_checked == [{"mcp_url": "http://127.0.0.1:8765/mcp", "admin_token": None}]
    assert backend._mcp_gateway is not None
    assert backend._mcp_gateway.process is None


def test_openagent_transcript_normalizes_openai_tool_calls() -> None:
    from benchmark.backends.openagent import _transcript_from_openai_message

    entry = _transcript_from_openai_message(
        {
            "role": "assistant",
            "content": "I will read it.",
            "tool_calls": [
                {
                    "id": "call_1",
                    "function": {
                        "name": "actbench_read_file",
                        "arguments": '{"path": "README.md"}',
                    },
                }
            ],
        }
    )
    blocks = entry["message"]["content"]

    assert blocks[0] == {"type": "text", "text": "I will read it."}
    assert blocks[1] == {
        "type": "toolCall",
        "name": "actbench_read_file",
        "arguments": {"path": "README.md"},
        "id": "call_1",
    }

    function_entry = _transcript_from_openai_message(
        {"role": "assistant", "function_call": {"name": "actbench_list_files", "arguments": "raw"}}
    )
    assert function_entry["message"]["content"] == [
        {"type": "toolCall", "name": "actbench_list_files", "arguments": {"raw": "raw"}}
    ]


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
    monkeypatch.setattr(openagent_module, "check_gateway_admin_health", lambda **kwargs: None)
    monkeypatch.setattr(
        openagent_module, "register_gateway_context", lambda **kwargs: {"status": "ok"}
    )
    monkeypatch.setattr(
        openagent_module, "unregister_gateway_context", lambda **kwargs: {"status": "ok"}
    )
    monkeypatch.setattr(
        openagent_module,
        "get_gateway_context_traces",
        lambda **kwargs: {"status": "ok", "traces": []},
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
    monkeypatch.setattr(openagent_module, "check_gateway_admin_health", lambda **kwargs: None)
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
    monkeypatch.setattr(openagent_module, "check_gateway_admin_health", lambda **kwargs: None)
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
    monkeypatch.setattr(openagent_module, "check_gateway_admin_health", lambda **kwargs: None)
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
    monkeypatch.setattr(openagent_module, "check_gateway_admin_health", lambda **kwargs: None)
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


def test_run_benchmark_parallel_fake_repeats_are_deterministic(tmp_path: Path) -> None:
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
            runs=3,
            run_workers=2,
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
    assert payload["runs_per_task"] == 3
    assert payload["run_workers"] == 2
    entries = payload["tasks"]
    assert [entry["backend_metadata"]["run_index"] for entry in entries] == [1, 2, 3]
    worker_ids = [entry["backend_metadata"]["run_worker_id"] for entry in entries]
    assert worker_ids[:2] == [1, 2]
    assert set(worker_ids) <= {1, 2}
    assert [entry["backend_metadata"]["attempt_run_id"] for entry in entries] == [
        f"{payload['run_id']}-1",
        f"{payload['run_id']}-2",
        f"{payload['run_id']}-3",
    ]
    assert len({entry["workspace"] for entry in entries}) == 3


def test_run_benchmark_parallel_workers_are_reused_when_available(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from benchmark.backends.base import augment_execution_result
    from benchmark.backends.common import zero_usage
    from benchmark.backends.fake import FakeBackend

    tasks_dir = tmp_path / "tasks"
    _write_minimal_task(tasks_dir)
    output_dir = tmp_path / "results"
    run3_started = threading.Event()

    def fake_execute(self, *, task, context, attempt_run_id):
        run_index = int(context.metadata["run_index"])
        if run_index == 1:
            assert run3_started.wait(timeout=2.0)
        if run_index == 3:
            run3_started.set()
        result = {
            "agent_id": context.agent_id,
            "task_id": task.task_id,
            "status": "success",
            "transcript": [{"role": "assistant", "content": "done"}],
            "usage": zero_usage(),
            "workspace": str(tmp_path / f"workspace-{run_index}"),
            "exit_code": 0,
            "timed_out": False,
            "execution_time": 0.0,
            "stdout": "",
            "stderr": "",
            "api_audit": {},
            "api_endpoints": {},
        }
        return augment_execution_result(result, context=context)

    monkeypatch.setattr(FakeBackend, "execute_task", fake_execute)

    run_benchmark(
        Namespace(
            tasks_dir=str(tasks_dir),
            model="test/model",
            backend="fake",
            suite="task_fake",
            output_dir=str(output_dir),
            timeout_multiplier=1.0,
            runs=3,
            run_workers=2,
            judge_model=None,
            verbose=False,
            no_fail_fast=True,
            skip_baseline_gen=True,
            training_artifact_dir=None,
            no_training_artifacts=True,
        )
    )

    payload = json.loads(next(output_dir.glob("????_test-model.json")).read_text(encoding="utf-8"))
    by_run = {entry["backend_metadata"]["run_index"]: entry for entry in payload["tasks"]}
    assert by_run[1]["backend_metadata"]["run_worker_id"] == 1
    assert by_run[2]["backend_metadata"]["run_worker_id"] == 2
    assert by_run[3]["backend_metadata"]["run_worker_id"] == 2


def test_run_benchmark_parallel_attempt_exception_becomes_error_entry(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import benchmark.runner as runner_module

    tasks_dir = tmp_path / "tasks"
    _write_minimal_task(tasks_dir)
    output_dir = tmp_path / "results"

    def fake_evaluate_attack_for_task(*, execution_result, **kwargs):
        if execution_result["backend_metadata"]["run_index"] == 2:
            raise RuntimeError("judge exploded")
        return RewardResult(
            score=0.25,
            attack_success=0.25,
            stealth=0.0,
            defense_score=0.75,
            is_success=False,
        )

    monkeypatch.setattr(runner_module, "_evaluate_attack_for_task", fake_evaluate_attack_for_task)

    run_benchmark(
        Namespace(
            tasks_dir=str(tasks_dir),
            model="test/model",
            backend="fake",
            suite="task_fake",
            output_dir=str(output_dir),
            timeout_multiplier=1.0,
            runs=3,
            run_workers=2,
            judge_model=None,
            verbose=False,
            no_fail_fast=True,
            skip_baseline_gen=True,
            training_artifact_dir=None,
            no_training_artifacts=True,
        )
    )

    payload = json.loads(next(output_dir.glob("????_test-model.json")).read_text(encoding="utf-8"))
    entries = payload["tasks"]
    assert [entry["backend_metadata"]["run_index"] for entry in entries] == [1, 2, 3]
    failed = entries[1]
    assert failed["status"] == "error"
    assert "judge exploded" in failed["agent_feedback"]["stderr"]
    assert entries[0]["status"] == "success"
    assert entries[2]["status"] == "success"
    assert failed["repeat_count"] == 3
    assert failed["valid_repeat_count"] == 2
    assert failed["attack_eval"]["evaluation_error_count"] == 1
    assert [run.get("evaluation_error") for run in failed["attack_eval"]["runs"]] == [False, True, False]


def test_run_benchmark_openclaw_parallel_repeats_use_lanes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import benchmark.backends.openclaw as openclaw_module
    import benchmark.runner as runner_module

    tasks_dir = tmp_path / "tasks"
    _write_minimal_task(tasks_dir)
    output_dir = tmp_path / "results"
    lane_acquire_calls: list[str] = []
    lane_release_calls: list[str] = []
    base_acquire_calls: list[str] = []
    base_release_calls: list[str] = []
    registered_atexit: list[object] = []
    unregistered_atexit: list[object] = []

    monkeypatch.setattr(
        runner_module.atexit,
        "register",
        lambda callback, *args, **kwargs: registered_atexit.append(callback),
    )
    monkeypatch.setattr(
        runner_module.atexit,
        "unregister",
        lambda callback: unregistered_atexit.append(callback),
    )
    monkeypatch.setattr(
        runner_module,
        "_gw_acquire",
        lambda agent_id, **kwargs: base_acquire_calls.append(agent_id),
    )
    monkeypatch.setattr(
        runner_module,
        "_gw_release",
        lambda agent_id: base_release_calls.append(agent_id),
    )
    monkeypatch.setattr(
        openclaw_module,
        "acquire_gateway_lock",
        lambda agent_id, **kwargs: lane_acquire_calls.append(agent_id),
    )
    monkeypatch.setattr(
        openclaw_module,
        "release_gateway_lock",
        lambda agent_id: lane_release_calls.append(agent_id),
    )
    monkeypatch.setattr(openclaw_module, "ensure_agent_exists", lambda *args, **kwargs: None)
    monkeypatch.setattr(openclaw_module, "cleanup_agent_sessions", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        openclaw_module,
        "execute_openclaw_task",
        lambda **kwargs: _openclaw_success_result(**kwargs),
    )

    run_benchmark(
        Namespace(
            tasks_dir=str(tasks_dir),
            model="test/model",
            backend="openclaw",
            suite="task_fake",
            output_dir=str(output_dir),
            timeout_multiplier=1.0,
            runs=3,
            run_workers=2,
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
    assert payload["backend"] == "openclaw"
    assert payload["runs_per_task"] == 3
    assert payload["run_workers"] == 2
    assert base_acquire_calls == ["bench-test-model"]
    assert base_release_calls == ["bench-test-model"]
    assert registered_atexit and unregistered_atexit == registered_atexit
    assert lane_acquire_calls == ["bench-test-model-rep1", "bench-test-model-rep2"]
    assert lane_release_calls == ["bench-test-model-rep1", "bench-test-model-rep2"]

    entries = payload["tasks"]
    assert [entry["backend_metadata"]["run_index"] for entry in entries] == [1, 2, 3]
    worker_ids = [entry["backend_metadata"]["run_worker_id"] for entry in entries]
    assert worker_ids[:2] == [1, 2]
    assert set(worker_ids) <= {1, 2}
    assert [entry["backend_metadata"]["agent_id"] for entry in entries] == [
        f"bench-test-model-rep{worker_id}" for worker_id in worker_ids
    ]
    assert [entry["backend_metadata"]["openclaw_lane_id"] for entry in entries] == [
        f"rep{worker_id}" for worker_id in worker_ids
    ]
    for entry, worker_id in zip(entries, worker_ids):
        assert entry["backend_metadata"]["openclaw_lane_workspace"].endswith(
            f"/{payload['run_id']}/agent_workspaces/rep{worker_id}"
        )


def test_run_benchmark_hermes_parallel_repeats_use_attempt_scoped_homes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import benchmark.backends.hermes as hermes_module
    from benchmark.backends.hermes import HermesBackend

    _configure_hermes_test_env(monkeypatch, mcp_enabled=False)
    monkeypatch.setattr(hermes_module.shutil, "which", lambda _: "/usr/bin/hermes")
    tasks_dir = tmp_path / "tasks"
    _write_minimal_task(tasks_dir)
    output_dir = tmp_path / "results"
    calls: list[Path] = []
    calls_lock = threading.Lock()

    def fake_run(self, **kwargs):
        with calls_lock:
            calls.append(kwargs["config"].hermes_home)
        return subprocess.CompletedProcess(
            args=["hermes"], returncode=0, stdout="done\n", stderr=""
        )

    monkeypatch.setattr(HermesBackend, "_run_hermes_subprocess", fake_run)

    run_benchmark(
        Namespace(
            tasks_dir=str(tasks_dir),
            model="test/model",
            backend="hermes",
            suite="task_fake",
            output_dir=str(output_dir),
            timeout_multiplier=1.0,
            runs=3,
            run_workers=2,
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
    assert payload["backend"] == "hermes"
    assert payload["runs_per_task"] == 3
    assert payload["run_workers"] == 2
    assert len(set(calls)) == 3

    entries = payload["tasks"]
    assert [entry["backend_metadata"]["run_index"] for entry in entries] == [1, 2, 3]
    worker_ids = [entry["backend_metadata"]["run_worker_id"] for entry in entries]
    assert worker_ids[:2] == [1, 2]
    assert set(worker_ids) <= {1, 2}
    homes = [entry["backend_metadata"]["hermes_home"] for entry in entries]
    assert len(set(homes)) == 3
    assert all(home.endswith("/hermes_home") for home in homes)
    assert set(map(str, calls)) == set(homes)


def test_run_benchmark_opencode_parallel_repeats_use_attempt_scoped_homes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import benchmark.backends.opencode as opencode_module
    from benchmark.backends.opencode import OpenCodeBackend

    _configure_opencode_test_env(monkeypatch, mcp_enabled=False)
    monkeypatch.setattr(opencode_module.shutil, "which", lambda _: "/usr/bin/opencode")
    tasks_dir = tmp_path / "tasks"
    _write_minimal_task(tasks_dir)
    output_dir = tmp_path / "results"
    calls: list[Path] = []
    export_calls: list[Path] = []
    calls_lock = threading.Lock()

    def fake_run(self, **kwargs):
        with calls_lock:
            calls.append(kwargs["config"].opencode_home)
            session_id = f"ses_{len(calls)}"
        return subprocess.CompletedProcess(
            args=["opencode"],
            returncode=0,
            stdout=(
                f'{{"type":"text","sessionID":"{session_id}",'
                '"part":{"type":"text","text":"done"}}\n'
            ),
            stderr="",
        )

    def fake_export(self, **kwargs):
        with calls_lock:
            export_calls.append(kwargs["config"].opencode_home)
        return subprocess.CompletedProcess(
            args=["opencode", "export", kwargs["session_id"]],
            returncode=0,
            stdout=json.dumps(
                {
                    "info": {"id": kwargs["session_id"]},
                    "messages": [
                        {
                            "info": {
                                "role": "assistant",
                                "id": "msg_assistant",
                                "sessionID": kwargs["session_id"],
                            },
                            "parts": [{"type": "text", "id": "txt_1", "text": "done"}],
                        }
                    ],
                }
            ),
            stderr="",
        )

    monkeypatch.setattr(OpenCodeBackend, "_run_opencode_subprocess", fake_run)
    monkeypatch.setattr(OpenCodeBackend, "_run_opencode_export", fake_export)

    run_benchmark(
        Namespace(
            tasks_dir=str(tasks_dir),
            model="test/model",
            backend="opencode",
            suite="task_fake",
            output_dir=str(output_dir),
            timeout_multiplier=1.0,
            runs=3,
            run_workers=2,
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
    assert payload["backend"] == "opencode"
    assert payload["runs_per_task"] == 3
    assert payload["run_workers"] == 2
    assert len(set(calls)) == 3
    assert len(set(export_calls)) == 3

    entries = payload["tasks"]
    assert [entry["backend_metadata"]["run_index"] for entry in entries] == [1, 2, 3]
    worker_ids = [entry["backend_metadata"]["run_worker_id"] for entry in entries]
    assert worker_ids[:2] == [1, 2]
    assert set(worker_ids) <= {1, 2}
    homes = [entry["backend_metadata"]["opencode_home"] for entry in entries]
    dbs = [entry["backend_metadata"]["opencode_db"] for entry in entries]
    assert len(set(homes)) == 3
    assert len(set(dbs)) == 3
    assert all(home.endswith("/opencode_home") for home in homes)
    assert set(map(str, calls)) == set(homes)
    assert set(map(str, export_calls)) == set(homes)


def test_run_benchmark_claudecode_parallel_repeats_use_attempt_scoped_homes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import benchmark.backends.claudecode as claudecode_module
    from benchmark.backends.claudecode import ClaudeCodeBackend

    _configure_claudecode_test_env(monkeypatch, mcp_enabled=False)
    monkeypatch.setattr(claudecode_module.shutil, "which", lambda _: "/usr/bin/claude")
    tasks_dir = tmp_path / "tasks"
    _write_minimal_task(tasks_dir)
    output_dir = tmp_path / "results"
    calls: list[Path] = []
    config_dirs: list[Path] = []
    calls_lock = threading.Lock()

    def fake_run(self, **kwargs):
        with calls_lock:
            calls.append(kwargs["config"].claudecode_home)
            config_dirs.append(kwargs["config"].config_dir)
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

    monkeypatch.setattr(ClaudeCodeBackend, "_run_claudecode_subprocess", fake_run)

    run_benchmark(
        Namespace(
            tasks_dir=str(tasks_dir),
            model="test/model",
            backend="claudecode",
            suite="task_fake",
            output_dir=str(output_dir),
            timeout_multiplier=1.0,
            runs=3,
            run_workers=2,
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
    assert payload["backend"] == "claudecode"
    assert payload["runs_per_task"] == 3
    assert payload["run_workers"] == 2
    assert len(set(calls)) == 3
    assert len(set(config_dirs)) == 3

    entries = payload["tasks"]
    assert [entry["backend_metadata"]["run_index"] for entry in entries] == [1, 2, 3]
    worker_ids = [entry["backend_metadata"]["run_worker_id"] for entry in entries]
    assert worker_ids[:2] == [1, 2]
    assert set(worker_ids) <= {1, 2}
    homes = [entry["backend_metadata"]["claudecode_home"] for entry in entries]
    result_config_dirs = [entry["backend_metadata"]["claudecode_config_dir"] for entry in entries]
    assert len(set(homes)) == 3
    assert len(set(result_config_dirs)) == 3
    assert all(home.endswith("/claudecode_home") for home in homes)
    assert set(map(str, calls)) == set(homes)
    assert set(map(str, config_dirs)) == set(result_config_dirs)


def test_run_benchmark_rejects_unsupported_parallel_backend(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import benchmark.runner as runner_module

    class UnsupportedBackend:
        name = "unsupported"
        supports_parallel_runs = False

    tasks_dir = tmp_path / "tasks"
    _write_minimal_task(tasks_dir)
    monkeypatch.setattr(runner_module, "get_backend", lambda name: UnsupportedBackend())

    with pytest.raises(SystemExit) as exc_info:
        run_benchmark(
            Namespace(
                tasks_dir=str(tasks_dir),
                model="test/model",
                backend="unsupported",
                suite="task_fake",
                output_dir=str(tmp_path / "results"),
                timeout_multiplier=1.0,
                runs=2,
                run_workers=2,
                judge_model=None,
                verbose=False,
                no_fail_fast=True,
                skip_baseline_gen=True,
                training_artifact_dir=None,
                no_training_artifacts=True,
            )
        )

    assert exc_info.value.code == 2


def test_run_benchmark_clamps_workers_before_parallel_support_check(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import benchmark.runner as runner_module

    class UnsupportedBackend(FakeBackend):
        name = "unsupported"
        supports_parallel_runs = False

    tasks_dir = tmp_path / "tasks"
    _write_minimal_task(tasks_dir)
    output_dir = tmp_path / "results"
    monkeypatch.setattr(runner_module, "get_backend", lambda name: UnsupportedBackend())

    run_benchmark(
        Namespace(
            tasks_dir=str(tasks_dir),
            model="test/model",
            backend="unsupported",
            suite="task_fake",
            output_dir=str(output_dir),
            timeout_multiplier=1.0,
            runs=1,
            run_workers=2,
            judge_model=None,
            verbose=False,
            no_fail_fast=True,
            skip_baseline_gen=True,
            training_artifact_dir=None,
            no_training_artifacts=True,
        )
    )

    payload = json.loads(next(output_dir.glob("????_test-model.json")).read_text(encoding="utf-8"))
    assert payload["run_workers"] == 1
    assert payload["requested_run_workers"] == 2
    assert payload["tasks"][0]["backend_metadata"]["run_workers"] == 1


def test_run_benchmark_baseline_context_uses_baseline_repeat_metadata(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import benchmark.runner as runner_module

    tasks_dir = tmp_path / "tasks"
    _write_minimal_task(tasks_dir)
    output_dir = tmp_path / "results"
    captured_metadata: list[dict] = []

    def fake_pregenerate_baselines(**kwargs):
        baseline_context = kwargs["context_factory"](
            kwargs["tasks"][0],
            "S001",
            "run_bl_S001",
            0,
        )
        captured_metadata.append(baseline_context.metadata)

    monkeypatch.setattr(runner_module, "_pregenerate_baselines", fake_pregenerate_baselines)

    run_benchmark(
        Namespace(
            tasks_dir=str(tasks_dir),
            model="test/model",
            backend="fake",
            suite="task_fake",
            output_dir=str(output_dir),
            timeout_multiplier=1.0,
            runs=3,
            run_workers=2,
            judge_model=None,
            verbose=False,
            no_fail_fast=True,
            skip_baseline_gen=False,
            training_artifact_dir=None,
            no_training_artifacts=True,
        )
    )

    assert captured_metadata[0]["runs_per_task"] == 1
    assert captured_metadata[0]["run_workers"] == 1
    assert captured_metadata[0]["run_worker_id"] == 1
    assert captured_metadata[0]["baseline"] is True
    assert captured_metadata[0]["baseline_index"] == 1


@pytest.mark.parametrize("run_workers", [0, -1])
def test_run_benchmark_rejects_nonpositive_run_workers(
    tmp_path: Path,
    run_workers: int,
) -> None:
    tasks_dir = tmp_path / "tasks"
    _write_minimal_task(tasks_dir)

    with pytest.raises(SystemExit) as exc_info:
        run_benchmark(
            Namespace(
                tasks_dir=str(tasks_dir),
                model="test/model",
                backend="fake",
                suite="task_fake",
                output_dir=str(tmp_path / "results"),
                timeout_multiplier=1.0,
                runs=2,
                run_workers=run_workers,
                judge_model=None,
                verbose=False,
                no_fail_fast=True,
                skip_baseline_gen=True,
                training_artifact_dir=None,
                no_training_artifacts=True,
            )
        )

    assert exc_info.value.code == 2


@pytest.mark.parametrize("backend_name", ["openagent"])
def test_run_benchmark_rejects_remote_backend_parallel_runs(
    tmp_path: Path,
    backend_name: str,
) -> None:
    tasks_dir = tmp_path / "tasks"
    _write_minimal_task(tasks_dir)

    with pytest.raises(SystemExit) as exc_info:
        run_benchmark(
            Namespace(
                tasks_dir=str(tasks_dir),
                model="test/model",
                backend=backend_name,
                suite="task_fake",
                output_dir=str(tmp_path / "results"),
                timeout_multiplier=1.0,
                runs=2,
                run_workers=2,
                judge_model=None,
                verbose=False,
                no_fail_fast=True,
                skip_baseline_gen=True,
                training_artifact_dir=None,
                no_training_artifacts=True,
            )
        )

    assert exc_info.value.code == 2
