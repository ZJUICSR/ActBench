from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import yaml

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import benchmark.baseline as baseline_module  # noqa: E402
from benchmark.baseline import (  # noqa: E402
    _baseline_cache_path,
    _baseline_written_content,
    _load_baseline_for_task,
    _load_clean_source_scene_for_task,
    _pregenerate_baselines,
    _scene_for_task,
    baseline_content_hash,
)
from benchmark.task_loading import _build_scene_index  # noqa: E402
from lib_tasks import Task  # noqa: E402


def _task(scenario: str = "S001") -> Task:
    return Task(
        task_id="task_B6_T01",
        name="Test task",
        category="privacy_leak",
        grading_type="automated",
        timeout_seconds=60,
        workspace_files=[],
        prompt="Summarize the inbox.",
        expected_behavior="",
        grading_criteria=[],
        frontmatter={"scenario": scenario},
    )


def _write_clean_bundle(bundle: Path, *, content: str = "Clean readme.") -> None:
    (bundle / "workspace").mkdir(parents=True, exist_ok=True)
    (bundle / "graders").mkdir(exist_ok=True)
    (bundle / "workspace" / "README.md").write_text(content, encoding="utf-8")
    (bundle / "graders" / "attack_check.py").write_text(
        "def check_attack_success(t, w): return 0.0", encoding="utf-8"
    )
    (bundle / "scenario.yaml").write_text(
        yaml.safe_dump(
            {
                "id": "S001",
                "name": "Clean bundle",
                "category": "business_operations",
                "user_prompt": "Do clean task.",
                "workspace_files": [{"path": "README.md"}],
                "graders": {"attack": "graders/attack_check.py"},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )


def test_build_scene_index_loads_directory_scenario(tmp_path: Path) -> None:
    scenario_dir = tmp_path / "scenes" / "scenarios" / "S001_inbox"
    (scenario_dir / "workspace").mkdir(parents=True)
    (scenario_dir / "fixtures" / "mailbox").mkdir(parents=True)
    (scenario_dir / "graders").mkdir()
    (scenario_dir / "workspace" / "README.md").write_text("Use mailbox data.", encoding="utf-8")
    fixture = scenario_dir / "fixtures" / "mailbox" / "inbox.json"
    fixture.write_text(json.dumps([{"message_id": "m1", "body": "hello"}]), encoding="utf-8")
    (scenario_dir / "graders" / "attack_check.py").write_text(
        "def check_attack_success(transcript_text, workspace_path):\n    return 0.0\n",
        encoding="utf-8",
    )
    (scenario_dir / "scenario.yaml").write_text(
        yaml.safe_dump(
            {
                "id": "S001",
                "name": "Inbox test",
                "category": "business_operations",
                "user_prompt": "Summarize the inbox.",
                "workspace_files": [{"path": "README.md"}],
                "mock_service_fixtures": {"mailbox": "fixtures/mailbox/inbox.json"},
                "graders": {"attack": "graders/attack_check.py"},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    scene_index = _build_scene_index(tmp_path)

    assert scene_index["S001"]["workspace_files"][0]["content"] == "Use mailbox data."
    assert Path(scene_index["S001"]["mock_service_fixtures"]["mailbox"]).exists()
    assert "check_attack_success" in scene_index["S001"]["attack_check_code"]


def test_non_openclaw_baseline_cache_key_includes_backend() -> None:
    task = _task()

    openclaw_path = _baseline_cache_path(task, "test/model", backend_name="openclaw")
    qwenpaw_path = _baseline_cache_path(task, "test/model", backend_name="qwenpaw")
    openagent_path = _baseline_cache_path(task, "test/model", backend_name="openagent")

    assert openclaw_path is not None
    assert qwenpaw_path is not None
    assert openagent_path is not None
    assert openclaw_path.name == "S001_test-model.json"
    assert qwenpaw_path.name == "S001_qwenpaw_test-model.json"
    assert openagent_path.name == "S001_openagent_test-model.json"



def test_baseline_content_hash_changes_when_fixture_changes(tmp_path: Path) -> None:
    fixture = tmp_path / "inbox.json"
    fixture.write_text(json.dumps([{"message_id": "m1", "body": "hello"}]), encoding="utf-8")
    scene = {
        "id": "S001",
        "user_prompt": "Summarize the inbox.",
        "workspace_files": [{"path": "README.md", "content": "Use mailbox data."}],
        "mock_service_fixtures": {"mailbox": str(fixture)},
        "attack_check_code": "def check_attack_success(t, w): return 0.0",
    }

    first = baseline_content_hash(_task(), scene)
    fixture.write_text(json.dumps([{"message_id": "m1", "body": "changed"}]), encoding="utf-8")
    second = baseline_content_hash(_task(), scene)

    assert first != second


def test_load_clean_source_scene_for_task_reads_bundle(tmp_path: Path) -> None:
    output_dir = tmp_path / "tasks"
    bundle = output_dir / "clean_scenes" / "task_B6_T01"
    _write_clean_bundle(bundle)
    task = _task()
    task.frontmatter["clean_source"] = {"bundle_path": str(bundle)}

    scene = _load_clean_source_scene_for_task(task)

    assert scene is not None
    assert scene["workspace_files"][0]["content"] == "Clean readme."
    assert "check_attack_success" in scene["attack_check_code"]


def test_load_clean_source_scene_resolves_relative_to_task_root(tmp_path: Path) -> None:
    tasks_dir = tmp_path / "tasks"
    task_dir = tasks_dir / "task_B6_T01"
    bundle = tasks_dir / "clean_scenes" / "task_B6_T01"
    task_dir.mkdir(parents=True)
    _write_clean_bundle(bundle, content="Task-root clean readme.")
    task = _task()
    task.file_path = task_dir / "task.yaml"
    task.frontmatter["clean_source"] = {"bundle_path": "clean_scenes/task_B6_T01"}

    scene = _load_clean_source_scene_for_task(task)

    assert scene is not None
    assert scene["workspace_files"][0]["content"] == "Task-root clean readme."


def test_scene_for_task_prefers_clean_source_over_scene_index(tmp_path: Path) -> None:
    tasks_dir = tmp_path / "tasks"
    task_dir = tasks_dir / "task_B6_T01"
    bundle = tasks_dir / "clean_scenes" / "task_B6_T01"
    task_dir.mkdir(parents=True)
    _write_clean_bundle(bundle, content="Clean source wins.")
    task = _task()
    task.file_path = task_dir / "task.yaml"
    task.frontmatter["clean_source"] = {"bundle_path": "clean_scenes/task_B6_T01"}
    scene_index = {"S001": {"workspace_files": [{"path": "README.md", "content": "stale"}]}}

    scene = _scene_for_task(task, scene_index)

    assert scene is not None
    assert scene["workspace_files"][0]["content"] == "Clean source wins."


def test_pregenerate_baselines_dedupes_by_cache_identity(monkeypatch, tmp_path: Path) -> None:
    tasks = [_task(), _task()]
    for index, task in enumerate(tasks):
        task.task_id = f"task_B6_T0{index + 1}"
        task.frontmatter["clean_source"] = {"content_hash": f"hash-{index}"}
    scene = {"id": "S001", "user_prompt": "Do it.", "workspace_files": []}
    calls = []
    monkeypatch.setattr(baseline_module, "_scene_for_task", lambda task, scene_index: scene)
    monkeypatch.setattr(baseline_module, "_load_baseline_for_task", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        baseline_module,
        "_generate_baseline_for_task",
        lambda **kwargs: calls.append(kwargs["task"].task_id),
    )

    _pregenerate_baselines(
        tasks=tasks,
        scene_index={"S001": scene},
        model="test/model",
        backend=SimpleNamespace(name="openclaw"),
        context=SimpleNamespace(),
        run_id="run",
    )

    assert calls == ["task_B6_T01", "task_B6_T02"]


def test_baseline_written_content_hashes_relative_written_files(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    (workspace / "reports").mkdir(parents=True)
    (workspace / "reports" / "summary.md").write_text("baseline report", encoding="utf-8")

    content = _baseline_written_content(workspace, ["reports/summary.md", "../escape.txt"])

    assert set(content) == {"reports/summary.md"}
    assert content["reports/summary.md"]["bytes"] == len("baseline report")
    assert content["reports/summary.md"]["sha256"]


def test_load_baseline_rejects_stale_or_missing_hash(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(baseline_module, "BASELINE_CACHE_DIR", tmp_path)
    task = _task()
    cache_path = tmp_path / "S001_test_model.json"
    cache_path.write_text(
        json.dumps({"scene_id": "S001", "target_model": "test/model"}),
        encoding="utf-8",
    )
    scene = {
        "id": "S001",
        "user_prompt": "Summarize the inbox.",
        "workspace_files": [{"path": "README.md", "content": "Use mailbox data."}],
    }

    assert _load_baseline_for_task(task, "test/model", scene=scene) is None
