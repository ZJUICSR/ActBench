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


def test_registry_resolves_backends_without_eager_qwenpaw_import() -> None:
    assert available_backend_names() == ("openclaw", "qwenpaw", "fake")
    assert get_backend("openclaw").name == "openclaw"
    assert get_backend("fake").name == "fake"
    assert get_backend("qwenpaw").name == "qwenpaw"
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
