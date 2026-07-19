from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import benchmark.offline_scoring as offline_scoring  # noqa: E402
from benchmark.trajectories import TRAJECTORY_SCHEMA_VERSION  # noqa: E402
from benchmark.utility_prep import (  # noqa: E402
    EXCLUDED_BASELINE_CACHE_ONLY,
    UTILITY_INPUT_SCHEMA_VERSION,
    UTILITY_PREP_MANIFEST_SCHEMA_VERSION,
    UTILITY_PREP_SUMMARY_SCHEMA_VERSION,
    main as utility_prep_main,
    prepare_utility_records,
)

FORBIDDEN_ATTACK_SCORE_KEYS = {
    "ags",
    "asr",
    "attack_success",
    "attack_success_count",
    "attack_pass",
    "attack_reproduced",
    "mean_attack_success",
    "pass@k",
    "pass@k1",
    "pass@k2",
    "pass@k3",
}


def _write_trajectory(
    tmp_path: Path,
    *,
    trajectory_id: str = "attempt-one",
    schema_version: str = TRAJECTORY_SCHEMA_VERSION,
    role: str = "attacked_attempt",
    suite: str = "B6",
    task_id: str = "task_fake",
    run_number: int = 1,
    backend_name: str = "openclaw",
    model: str = "test/model",
    status: str = "success",
    exit_code: int | None = 0,
    timed_out: bool = False,
    create_workspace: bool = True,
    canonical: bool = False,
    superseded: bool = False,
) -> Path:
    artifacts_root = tmp_path / "artifacts"
    run_dir = artifacts_root / "runs" / trajectory_id
    workspace = run_dir / "workspace_after"
    run_dir.mkdir(parents=True, exist_ok=True)
    if create_workspace:
        workspace.mkdir(parents=True)
        (workspace / "result.txt").write_text("utility evidence\n", encoding="utf-8")
    api_dir = run_dir / "api"
    api_dir.mkdir(parents=True, exist_ok=True)
    (api_dir / "audit.json").write_text("{}\n", encoding="utf-8")
    (api_dir / "endpoints.json").write_text("{}\n", encoding="utf-8")
    trajectory: dict[str, Any] = {
        "schema_version": schema_version,
        "trajectory_id": trajectory_id,
        "role": role,
        "run": {
            "run_id": "run_001",
            "attempt_run_id": "run_001-1",
            "run_index": run_number,
            "run_number": run_number,
            "runs_per_task": 2,
            "run_worker_id": 1,
            "run_worker_label": "w1",
            "run_workers": 2,
            "requested_run_workers": 2,
            "training_artifact_key": trajectory_id,
            "context_metadata": {"suite": suite},
        },
        "backend": {
            "name": backend_name,
            "model": model,
            "agent_id": "bench-test-model",
            "backend_metadata": {},
        },
        "task": {
            "task_id": task_id,
            "name": "Fake Utility Task",
            "category": "utility",
            "grading_type": "automated",
            "prompt": "Complete the fake utility task.",
            "expected_behavior": "Finish the requested benign task.",
            "grading_criteria": ["The benign task is complete."],
            "frontmatter": {
                "behavior_id": suite,
                "prompt": "Complete the fake utility task.",
            },
        },
        "execution": {
            "status": status,
            "exit_code": exit_code,
            "timed_out": timed_out,
            "execution_time": 1.25,
            "stdout": "Done with the fake utility task.",
            "stderr": "",
            "workspace": str(tmp_path / "ephemeral_workspace"),
            "api_audit": {
                "taskboard": {
                    "calls": [
                        {
                            "endpoint": "/taskboard/tasks/update",
                            "request_body": {"task_id": "T-1"},
                        }
                    ],
                    "updated_tasks": [{"task_id": "T-1"}],
                }
            },
            "training_artifact_key": trajectory_id,
            "extra": {
                "execution_retry": {
                    "enabled": True,
                    "status": status,
                    "will_retry": superseded,
                    "superseded": superseded,
                }
            },
        },
        "transcript": {
            "entries": [
                {
                    "type": "message",
                    "message": {
                        "role": "user",
                        "content": ["Complete the fake utility task."],
                    },
                },
                {
                    "type": "message",
                    "message": {
                        "role": "assistant",
                        "content": [{"type": "text", "text": "Done."}],
                    },
                },
            ],
            "source": {"kind": "sessions_json", "fallback_used": False},
        },
        "artifacts": {
            "artifact_root": str(artifacts_root),
            "workspace_after": f"runs/{trajectory_id}/workspace_after",
            "workspace_after_absolute": str(workspace),
            "api_audit": f"runs/{trajectory_id}/api/audit.json",
            "api_endpoints": f"runs/{trajectory_id}/api/endpoints.json",
            "trajectory": f"runs/{trajectory_id}/trajectory.json",
        },
        "scoring_inputs": {
            "replay_workspace_path": f"runs/{trajectory_id}/workspace_after",
            "replay_workspace_absolute_path": str(workspace),
            "execution_feedback_snapshot": {
                "status": status,
                "exit_code": exit_code,
                "timed_out": timed_out,
            },
        },
    }
    if canonical:
        trajectory["canonical"] = {
            "slot_id": f"{suite}/{task_id}/run_{run_number}",
            "suite": suite,
            "task_id": task_id,
            "run_number": run_number,
            "role": role,
            "trajectory_path": f"trajectories/{suite}/{task_id}/runs/run_{run_number}/trajectory.json",
            "metadata_path": f"trajectories/{suite}/{task_id}/runs/run_{run_number}/metadata.json",
        }
        trajectory["artifacts"]["canonical_slot_id"] = trajectory["canonical"]["slot_id"]
    path = run_dir / "trajectory.json"
    path.write_text(json.dumps(trajectory), encoding="utf-8")
    return path


def _all_json_keys(value: Any) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, dict):
        for key, child in value.items():
            keys.add(str(key))
            keys.update(_all_json_keys(child))
    elif isinstance(value, list):
        for child in value:
            keys.update(_all_json_keys(child))
    return keys


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_raw_manifest(dataset_dir: Path, *, backend: str = "openclaw", model: str = "test/model") -> None:
    dataset_dir.mkdir(parents=True, exist_ok=True)
    (dataset_dir / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "actbench.raw_by_task.v1",
                "name": dataset_dir.name,
                "backend": backend,
                "target_model": model,
                "copied_success_runs": 1,
                "task_count": 1,
                "suite_counts": {"B6": 1},
                "baseline_summary": {"baseline_count": 1},
            }
        ),
        encoding="utf-8",
    )


def _write_raw_trajectory(
    tmp_path: Path,
    dataset_dir: Path,
    *,
    role: str = "attacked_attempt",
    suite: str = "B6",
    task_id: str = "task_B6_T01",
    run_number: int = 1,
) -> Path:
    trajectory_task_id = f"{task_id}_baseline" if role == "benign_baseline" else task_id
    seed = _write_trajectory(
        tmp_path / f"seed_{dataset_dir.name}_{role}_{suite}_{task_id}_{run_number}",
        role=role,
        suite=suite,
        task_id=trajectory_task_id,
        run_number=run_number,
    )
    trajectory = _read_json(seed)
    trajectory["artifacts"] = {
        "workspace_after": "workspace_after",
        "api_audit": "api/audit.json",
        "api_endpoints": "api/endpoints.json",
        "trajectory": "trajectory.json",
    }
    trajectory["scoring_inputs"]["replay_workspace_path"] = "workspace_after"
    trajectory["scoring_inputs"].pop("replay_workspace_absolute_path", None)
    trajectory["execution"]["workspace"] = str(tmp_path / "ephemeral_workspace")
    if role == "benign_baseline":
        trajectory["source_task_id"] = task_id
        trajectory["clean_task_id"] = trajectory_task_id
        trajectory["run"].setdefault("context_metadata", {})["baseline_task_id"] = task_id
        run_dir = dataset_dir / "_baselines" / suite / task_id / "baseline"
    else:
        run_dir = dataset_dir / suite / task_id / f"run_{run_number}"
    workspace = run_dir / "workspace_after"
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "result.txt").write_text("utility evidence\n", encoding="utf-8")
    api_dir = run_dir / "api"
    api_dir.mkdir(parents=True, exist_ok=True)
    (api_dir / "audit.json").write_text("{}\n", encoding="utf-8")
    (api_dir / "endpoints.json").write_text("{}\n", encoding="utf-8")
    path = run_dir / "trajectory.json"
    path.write_text(json.dumps(trajectory), encoding="utf-8")
    return path


def test_cli_writes_separate_utility_bundle(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    trajectory_path = _write_trajectory(tmp_path)
    output_dir = tmp_path / "utility_prep"

    exit_code = utility_prep_main(
        ["--trajectory", str(trajectory_path), "--output-dir", str(output_dir)]
    )

    assert exit_code == 0
    stdout = json.loads(capsys.readouterr().out)
    assert stdout["prepared_count"] == 1
    summary = _read_json(output_dir / "utility_prep_summary.json")
    manifest = _read_json(output_dir / "utility_prep_manifest.json")
    assert summary["schema_version"] == UTILITY_PREP_SUMMARY_SCHEMA_VERSION
    assert manifest["schema_version"] == UTILITY_PREP_MANIFEST_SCHEMA_VERSION
    assert manifest["records"][0]["source_trajectory_path"] == str(trajectory_path)
    record_path = output_dir / manifest["records"][0]["record_path"]
    transcript_path = output_dir / manifest["records"][0]["transcript_path"]
    record = _read_json(record_path)
    transcript = _read_json(transcript_path)
    assert record["schema_version"] == UTILITY_INPUT_SCHEMA_VERSION
    assert record["future_grading"] == {
        "intended_uses": ["ugs", "tacc"],
        "requires_agent_rerun": False,
        "prepared_only": True,
    }
    assert transcript["entries"]


def test_utility_prep_cli_accepts_raw_by_task_attacked(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = tmp_path / "pack" / "raw_by_task"
    dataset = root / "dataset_one"
    _write_raw_manifest(dataset)
    _write_raw_trajectory(tmp_path, dataset, role="attacked_attempt")
    output_dir = tmp_path / "utility_raw_attacked"

    exit_code = utility_prep_main(
        [
            "--raw-by-task-root",
            str(root),
            "--raw-by-task-dataset",
            "dataset_one",
            "--role",
            "attacked",
            "--output-dir",
            str(output_dir),
        ]
    )

    stdout = json.loads(capsys.readouterr().out)
    manifest = _read_json(output_dir / "utility_prep_manifest.json")
    assert exit_code == 0
    assert stdout["prepared_count"] == 1
    assert manifest["source"]["raw_by_task"]["role"] == "attacked"
    assert manifest["records"][0]["role"] == "attacked_attempt"


def test_utility_prep_raw_by_task_benign_excludes_cache_only_baselines(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = tmp_path / "pack" / "raw_by_task"
    dataset = root / "dataset_one"
    _write_raw_manifest(dataset)
    _write_raw_trajectory(tmp_path, dataset, role="benign_baseline", task_id="task_B6_T01")
    cache_only = dataset / "_baselines" / "B6" / "task_B6_T02" / "baseline"
    cache_only.mkdir(parents=True)
    (cache_only / "baseline_cache.json").write_text("{}\n", encoding="utf-8")
    output_dir = tmp_path / "utility_raw_benign"

    exit_code = utility_prep_main(
        [
            "--raw-by-task-root",
            str(root),
            "--raw-by-task-dataset",
            "dataset_one",
            "--role",
            "benign",
            "--output-dir",
            str(output_dir),
        ]
    )

    stdout = json.loads(capsys.readouterr().out)
    manifest = _read_json(output_dir / "utility_prep_manifest.json")
    assert exit_code == 0
    assert stdout["prepared_count"] == 1
    assert stdout["counts_by_exclusion_reason"] == {EXCLUDED_BASELINE_CACHE_ONLY: 1}
    assert manifest["excluded"][0]["reason"] == EXCLUDED_BASELINE_CACHE_ONLY
    assert manifest["excluded"][0]["path"] == str(cache_only)
    record = _read_json(output_dir / manifest["records"][0]["record_path"])
    assert record["identity"]["role"] == "benign_baseline"
    assert record["identity"]["source_task_id"] == "task_B6_T01"
    assert record["identity"]["clean_task_id"] == "task_B6_T01_baseline"
    assert record["identity"]["comparison_task_id"] == "task_B6_T01"


def test_utility_prep_raw_by_task_default_collects_attacked_and_benign(tmp_path: Path) -> None:
    root = tmp_path / "pack" / "raw_by_task"
    dataset = root / "dataset_one"
    _write_raw_manifest(dataset)
    _write_raw_trajectory(tmp_path, dataset, role="attacked_attempt")
    _write_raw_trajectory(tmp_path, dataset, role="benign_baseline")

    payload = prepare_utility_records(
        [],
        raw_by_task_paths=[
            *dataset.glob("B6/task_B6_T01/run_1/trajectory.json"),
            *dataset.glob("_baselines/B6/task_B6_T01/baseline/trajectory.json"),
        ],
    )

    assert payload["summary"]["prepared_count"] == 2
    roles = {item["record"]["identity"]["role"] for item in payload["prepared_items"]}
    assert roles == {"attacked_attempt", "benign_baseline"}


def test_utility_prep_raw_by_task_suite_and_task_filters_are_structural(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = tmp_path / "pack" / "raw_by_task"
    dataset = root / "dataset_one"
    _write_raw_manifest(dataset)
    _write_raw_trajectory(tmp_path, dataset, role="attacked_attempt", suite="B6", task_id="task_B6_T01")
    _write_raw_trajectory(tmp_path, dataset, role="attacked_attempt", suite="B7", task_id="task_B7_T01")
    output_dir = tmp_path / "utility_filtered"

    exit_code = utility_prep_main(
        [
            "--raw-by-task-root",
            str(root),
            "--raw-by-task-dataset",
            "dataset_one",
            "--role",
            "attacked",
            "--suite",
            "B6",
            "--task-id",
            "task_B6_T01",
            "--output-dir",
            str(output_dir),
        ]
    )

    stdout = json.loads(capsys.readouterr().out)
    manifest = _read_json(output_dir / "utility_prep_manifest.json")
    assert exit_code == 0
    assert stdout["prepared_count"] == 1
    assert manifest["records"][0]["suite"] == "B6"
    assert manifest["records"][0]["task_id"] == "task_B6_T01"


def test_utility_outputs_do_not_emit_attack_score_keys(tmp_path: Path) -> None:
    _write_trajectory(tmp_path)
    output_dir = tmp_path / "utility_prep"

    payload = prepare_utility_records([str(tmp_path / "artifacts")])
    from benchmark.utility_prep import write_utility_prep_bundle

    write_utility_prep_bundle(payload, output_dir)

    for path in output_dir.rglob("*.json"):
        keys = _all_json_keys(_read_json(path))
        assert keys.isdisjoint(FORBIDDEN_ATTACK_SCORE_KEYS), path


def test_utility_prep_prefers_canonical_copy_over_legacy_duplicate(tmp_path: Path) -> None:
    legacy_path = _write_trajectory(tmp_path, canonical=True)
    trajectory = _read_json(legacy_path)
    canonical_path = (
        tmp_path
        / "artifacts"
        / "trajectories"
        / "B6"
        / "task_fake"
        / "runs"
        / "run_1"
        / "trajectory.json"
    )
    canonical_path.parent.mkdir(parents=True)
    canonical_path.write_text(json.dumps(trajectory), encoding="utf-8")

    payload = prepare_utility_records([str(tmp_path / "artifacts")])

    assert payload["summary"]["prepared_count"] == 1
    assert payload["summary"]["counts_by_exclusion_reason"] == {"deduped": 1}
    record = payload["prepared_items"][0]["record"]
    assert record["source"]["trajectory_path"] == str(canonical_path)
    assert record["source"]["canonical_slot_id"] == "B6/task_fake/run_1"


def test_superseded_retry_loses_to_non_superseded_duplicate(tmp_path: Path) -> None:
    old_path = _write_trajectory(tmp_path, trajectory_id="attempt-old", canonical=True, superseded=True)
    new_path = _write_trajectory(tmp_path, trajectory_id="attempt-new", canonical=True)
    old = _read_json(old_path)
    new = _read_json(new_path)
    old["canonical"] = new["canonical"]
    old["artifacts"]["canonical_slot_id"] = new["canonical"]["slot_id"]
    old_path.write_text(json.dumps(old), encoding="utf-8")

    payload = prepare_utility_records([str(old_path), str(new_path)])

    assert payload["summary"]["prepared_count"] == 1
    record = payload["prepared_items"][0]["record"]
    assert record["source"]["trajectory_id"] == "attempt-new"


@pytest.mark.parametrize(
    ("status", "exit_code", "timed_out"),
    [("error", 0, False), ("success", 2, False), ("success", 0, True)],
)
def test_execution_failures_are_excluded_by_default(
    tmp_path: Path,
    status: str,
    exit_code: int,
    timed_out: bool,
) -> None:
    path = _write_trajectory(tmp_path, status=status, exit_code=exit_code, timed_out=timed_out)

    payload = prepare_utility_records([str(path)])

    assert payload["summary"]["prepared_count"] == 0
    assert payload["summary"]["counts_by_exclusion_reason"] == {"execution_failure": 1}


def test_include_failed_keeps_record_with_quality_flag(tmp_path: Path) -> None:
    path = _write_trajectory(tmp_path, status="error", exit_code=0)

    payload = prepare_utility_records([str(path)], include_failed=True)

    assert payload["summary"]["prepared_count"] == 1
    record = payload["prepared_items"][0]["record"]
    assert record["execution"]["status"] == "error"
    assert record["quality_flags"] == ["execution_failure"]


def test_missing_workspace_excluded_by_default(tmp_path: Path) -> None:
    path = _write_trajectory(tmp_path, create_workspace=False)

    payload = prepare_utility_records([str(path)])

    assert payload["summary"]["prepared_count"] == 0
    assert payload["summary"]["counts_by_exclusion_reason"] == {"missing_workspace": 1}


def test_transcript_metrics_and_filters(tmp_path: Path) -> None:
    path = _write_trajectory(
        tmp_path,
        role="benign_baseline",
        suite="B1",
        backend_name="openagent",
        model="deepseek/test",
        task_id="task_B1_T01_baseline",
    )

    excluded = prepare_utility_records([str(path)], roles=["attacked_attempt"])
    assert excluded["summary"]["prepared_count"] == 0
    assert excluded["summary"]["counts_by_exclusion_reason"] == {"role_filter": 1}

    payload = prepare_utility_records(
        [str(path)],
        roles=["benign_baseline"],
        backends=["openagent"],
        models=["deepseek/test"],
        task_ids=["task_B1_T01_baseline"],
        suites=["B1"],
    )
    assert payload["summary"]["prepared_count"] == 1
    transcript = payload["prepared_items"][0]["record"]["transcript"]
    assert transcript["entry_count"] == 2
    assert transcript["message_count"] == 2
    assert transcript["message_text_chars"] > 0
    assert transcript["message_role_counts"] == {"assistant": 1, "user": 1}


def test_same_canonical_slot_is_preserved_across_source_roots(tmp_path: Path) -> None:
    first = _write_trajectory(tmp_path / "first", trajectory_id="attempt-one", canonical=True)
    second = _write_trajectory(tmp_path / "second", trajectory_id="attempt-two", canonical=True)

    payload = prepare_utility_records([str(first), str(second)])

    assert payload["summary"]["prepared_count"] == 2
    trajectory_ids = {
        item["record"]["source"]["trajectory_id"] for item in payload["prepared_items"]
    }
    assert trajectory_ids == {"attempt-one", "attempt-two"}


def test_dry_run_does_not_write_outputs(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = _write_trajectory(tmp_path)
    output_dir = tmp_path / "utility_prep"

    exit_code = utility_prep_main(
        ["--trajectory", str(path), "--output-dir", str(output_dir), "--dry-run"]
    )

    assert exit_code == 0
    stdout = json.loads(capsys.readouterr().out)
    assert stdout["prepared_count"] == 1
    assert stdout["dry_run"] is True
    assert not output_dir.exists()


def test_utility_prep_does_not_call_attack_scorers(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    path = _write_trajectory(tmp_path)

    def explode(*_args: object, **_kwargs: object) -> dict:
        raise AssertionError("attack scorer should not be called")

    monkeypatch.setattr(offline_scoring, "_run_automated_checks", explode)
    monkeypatch.setattr(offline_scoring, "evaluate_attack", explode)

    payload = prepare_utility_records([str(path)])

    assert payload["summary"]["prepared_count"] == 1
    assert payload["summary"]["attack_scoring_invoked"] is False
    assert payload["summary"]["grading_invoked"] is False
