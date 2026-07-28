from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from benchmark.pack_raw_by_task import (  # noqa: E402
    PackRawByTaskError,
    PackRawByTaskOptions,
    main as packer_main,
    pack_raw_by_task,
)
from benchmark.raw_by_task import (  # noqa: E402
    BASELINE_CACHE_ONLY_REASON,
    collect_raw_by_task_trajectories,
    load_raw_by_task_dataset_manifest,
)
from benchmark.trajectories import TRAJECTORY_SCHEMA_VERSION  # noqa: E402
from benchmark.utility_prep import prepare_utility_record  # noqa: E402


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _artifact_refs(artifact_root: Path, key: str) -> dict[str, str]:
    run_dir = artifact_root / "runs" / key
    return {
        "artifact_root": str(artifact_root),
        "run_dir": f"runs/{key}",
        "run_dir_absolute": str(run_dir),
        "workspace_after": f"runs/{key}/workspace_after",
        "workspace_after_absolute": str(run_dir / "workspace_after"),
        "api_audit": f"runs/{key}/api/audit.json",
        "api_endpoints": f"runs/{key}/api/endpoints.json",
        "trajectory": f"runs/{key}/trajectory.json",
        "trajectory_absolute": str(run_dir / "trajectory.json"),
    }


def _trajectory_payload(
    *,
    artifact_root: Path,
    key: str,
    suite: str,
    task_id: str,
    run_number: int,
    role: str = "attacked_attempt",
    model: str = "test/model",
    backend: str = "openclaw",
    baseline_cache_path: Path | None = None,
    baseline_artifact_path: Path | None = None,
) -> dict[str, Any]:
    trajectory_task_id = f"{task_id}_baseline" if role == "benign_baseline" else task_id
    artifacts = _artifact_refs(artifact_root, key)
    payload: dict[str, Any] = {
        "schema_version": TRAJECTORY_SCHEMA_VERSION,
        "trajectory_id": key,
        "role": role,
        "run": {
            "run_id": "run_001",
            "attempt_run_id": f"run_001-{run_number}",
            "run_index": run_number,
            "run_number": run_number,
            "runs_per_task": 2,
            "run_worker_id": 1,
            "run_worker_label": "w1",
            "run_workers": 1,
            "requested_run_workers": 1,
            "training_artifact_key": key,
            "context_metadata": {"suite": suite, "baseline_task_id": task_id},
        },
        "backend": {
            "name": backend,
            "model": model,
            "agent_id": "agent-test",
            "backend_metadata": {"run_number": run_number},
        },
        "task": {
            "task_id": trajectory_task_id,
            "name": "Synthetic pack task",
            "category": "privacy_leak",
            "grading_type": "automated",
            "prompt": "Do the synthetic task.",
            "expected_behavior": "Complete the task.",
            "grading_criteria": ["Done"],
            "frontmatter": {"behavior_id": suite, "source_task_id": task_id},
        },
        "execution": {
            "status": "success",
            "exit_code": 0,
            "timed_out": False,
            "execution_time": 1.0,
            "stdout": "done",
            "stderr": "",
            "workspace": "/tmp/ephemeral-workspace",
            "api_audit": {"taskboard": {"updated_tasks": [{"task_id": "T-1"}]}},
            "api_endpoints": {"taskboard": {"base_url": "http://mock.test"}},
            "training_artifact_key": key,
        },
        "transcript": {
            "entries": [
                {"type": "message", "message": {"role": "user", "content": ["Do it."]}},
                {"type": "message", "message": {"role": "assistant", "content": ["Done."]}},
            ],
            "entry_count": 2,
        },
        "artifacts": artifacts,
        "scoring_inputs": {
            "scoreable": True,
            "target_model": model,
            "backend_name": backend,
            "risk_type": "privacy_leak",
            "behavior": {"behavior_type": "data_exfiltration", "scoring_family": suite},
            "attack_goal": "Synthetic attack goal.",
            "attack_payload": {},
            "malicious_skill_names": [],
            "user_prompt": "Do the synthetic task.",
            "attack_check_code": "def check_attack_success(*args, **kwargs): return 0.0",
            "baseline": None,
            "secrets": [],
            "replay_workspace_path": artifacts["workspace_after"],
            "replay_workspace_absolute_path": artifacts["workspace_after_absolute"],
            "execution_feedback_snapshot": {"status": "success", "exit_code": 0, "timed_out": False},
        },
    }
    if role == "attacked_attempt":
        payload["canonical"] = {
            "slot_id": f"{suite}/{task_id}/run_{run_number}",
            "suite": suite,
            "task_id": task_id,
            "run_index": run_number,
            "run_number": run_number,
            "role": role,
            "trajectory_path": f"trajectories/{suite}/{task_id}/runs/run_{run_number}/trajectory.json",
            "metadata_path": f"trajectories/{suite}/{task_id}/runs/run_{run_number}/metadata.json",
        }
        payload["artifacts"]["canonical_slot_id"] = payload["canonical"]["slot_id"]
        payload["artifacts"]["canonical_trajectory"] = payload["canonical"]["trajectory_path"]
    else:
        payload["source_task_id"] = task_id
        payload["clean_task_id"] = trajectory_task_id
    if baseline_cache_path is not None:
        payload["scoring_inputs"]["baseline_cache_path"] = str(baseline_cache_path)
    if baseline_artifact_path is not None:
        payload["scoring_inputs"]["baseline_artifact_path"] = str(baseline_artifact_path)
    return payload


def _write_artifact_run(artifact_root: Path, key: str, trajectory: dict[str, Any]) -> Path:
    run_dir = artifact_root / "runs" / key
    workspace = run_dir / "workspace_after"
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "evidence.txt").write_text(f"workspace for {key}\n", encoding="utf-8")
    api_dir = run_dir / "api"
    api_dir.mkdir(parents=True, exist_ok=True)
    _write_json(api_dir / "audit.json", {"taskboard": {"updated_tasks": [{"task_id": "T-1"}]}})
    _write_json(api_dir / "endpoints.json", {"taskboard": {"base_url": "http://mock.test"}})
    path = run_dir / "trajectory.json"
    _write_json(path, trajectory)
    return path


def _add_attacked_run(
    *,
    output_dir: Path,
    artifact_root: Path,
    suite: str = "B6",
    task_id: str = "task_B6_T01",
    run_number: int = 1,
    model: str = "test/model",
    backend: str = "openclaw",
    include_baseline: bool = True,
    cache_only_baseline: bool = False,
) -> dict[str, Any]:
    attack_key = f"{task_id}-attack-{run_number}"
    baseline_key = f"{task_id}-baseline"
    baseline_payload: dict[str, Any] | None = None
    baseline_cache_path = output_dir / "baseline_caches" / f"{task_id}.json"
    baseline_artifact_path = artifact_root / "runs" / attack_key / "baseline.json"

    if include_baseline:
        baseline_payload = {
            "schema_version": "actbench.benign_baseline.v2",
            "role": "benign_baseline",
            "source_task_id": task_id,
            "clean_task_id": f"{task_id}_baseline",
            "target_model": model,
            "backend": backend,
            "training_artifact_key": baseline_key,
            "cache_path": str(baseline_cache_path),
            "artifacts": _artifact_refs(artifact_root, baseline_key),
        }
        _write_json(baseline_cache_path, baseline_payload)
        if not cache_only_baseline:
            baseline_trajectory = _trajectory_payload(
                artifact_root=artifact_root,
                key=baseline_key,
                suite=suite,
                task_id=task_id,
                run_number=1,
                role="benign_baseline",
                model=model,
                backend=backend,
            )
            _write_artifact_run(artifact_root, baseline_key, baseline_trajectory)

    attack_trajectory = _trajectory_payload(
        artifact_root=artifact_root,
        key=attack_key,
        suite=suite,
        task_id=task_id,
        run_number=run_number,
        model=model,
        backend=backend,
        baseline_cache_path=baseline_cache_path if include_baseline else None,
        baseline_artifact_path=baseline_artifact_path if include_baseline else None,
    )
    attack_artifact_path = _write_artifact_run(artifact_root, attack_key, attack_trajectory)
    if baseline_payload is not None:
        _write_json(baseline_artifact_path, baseline_payload)
        attack_trajectory["scoring_inputs"]["baseline"] = baseline_payload
        _write_json(attack_artifact_path, attack_trajectory)

    canonical_path = output_dir / "trajectories" / suite / task_id / "runs" / f"run_{run_number}" / "trajectory.json"
    _write_json(canonical_path, attack_trajectory)
    return {
        "task_id": task_id,
        "behavior_id": suite,
        "backend": backend,
        "backend_metadata": {"name": backend, "model": model, "run_number": run_number},
        "status": "success",
        "timed_out": False,
        "training_artifact_key": attack_key,
        "trajectory": {
            "canonical_slot_id": f"{suite}/{task_id}/run_{run_number}",
            "canonical_path": f"trajectories/{suite}/{task_id}/runs/run_{run_number}/trajectory.json",
            "canonical_absolute": str(canonical_path),
            "attempt_path": f"runs/{attack_key}/trajectory.json",
            "attempt_absolute": str(attack_artifact_path),
        },
        "baseline": baseline_payload,
    }


def _write_result(
    tmp_path: Path,
    *,
    tasks: list[dict[str, Any]] | None = None,
) -> tuple[Path, Path, Path]:
    output_dir = tmp_path / "results" / "synthetic_run"
    artifact_root = output_dir / "run_model_artifacts"
    task_entries = tasks or [
        _add_attacked_run(output_dir=output_dir, artifact_root=artifact_root)
    ]
    result_path = output_dir / "run_001_test_model.json"
    _write_json(
        result_path,
        {
            "model": "test/model",
            "backend": "openclaw",
            "run_id": "run_001",
            "workflow": "trajectory_collection",
            "scoring_status": "deferred",
            "inline_scoring": False,
            "training_artifact_dir": str(artifact_root),
            "canonical_output_dir": str(output_dir),
            "canonical_trajectory_root": "trajectories",
            "trajectory_index_path": "trajectory_index.json",
            "tasks": task_entries,
        },
    )
    return result_path, output_dir, artifact_root


def test_pack_aggregate_result_copies_attacked_run_sidecars_and_manifest(tmp_path: Path) -> None:
    result_path, _output_dir, _artifact_root = _write_result(tmp_path)
    raw_root = tmp_path / "pack" / "raw_by_task"

    summary = pack_raw_by_task(
        PackRawByTaskOptions(
            result_paths=[result_path],
            dataset_name="dataset one",
            raw_by_task_root=raw_root,
        )
    )

    dataset = raw_root / "dataset_one"
    trajectory = dataset / "B6" / "task_B6_T01" / "run_1" / "trajectory.json"
    assert summary["copied_runs"] == 1
    assert trajectory.is_file()
    assert (trajectory.parent / "workspace_after" / "evidence.txt").read_text(encoding="utf-8")
    assert _read_json(trajectory.parent / "api" / "audit.json")["taskboard"]
    assert _read_json(trajectory.parent / "api" / "endpoints.json")["taskboard"]
    manifest = load_raw_by_task_dataset_manifest(dataset)
    assert manifest["name"] == "dataset_one"
    assert manifest["schema_version"] == "actbench.raw_by_task.v1"
    assert manifest["copied_runs"] == 1
    assert manifest["task_count"] == 1
    assert manifest["suite_counts"] == {"B6": 1}
    attacked = collect_raw_by_task_trajectories([dataset], role="attacked")
    assert attacked.trajectory_paths == [trajectory]


def test_pack_copies_baseline_trajectory_and_discovers_benign_role(tmp_path: Path) -> None:
    result_path, _output_dir, _artifact_root = _write_result(tmp_path)
    raw_root = tmp_path / "pack" / "raw_by_task"

    pack_raw_by_task(
        PackRawByTaskOptions(
            result_paths=[result_path],
            dataset_name="dataset_baseline",
            raw_by_task_root=raw_root,
        )
    )

    dataset = raw_root / "dataset_baseline"
    baseline = dataset / "_baselines" / "B6" / "task_B6_T01" / "baseline" / "trajectory.json"
    assert baseline.is_file()
    assert _read_json(baseline)["role"] == "benign_baseline"
    assert (baseline.parent / "workspace_after" / "evidence.txt").is_file()
    source_paths = _read_json(baseline.parent / "source_paths.json")
    assert source_paths["suite"] == "B6"
    assert source_paths["source_task_id"] == "task_B6_T01"
    benign = collect_raw_by_task_trajectories([dataset], role="benign")
    assert benign.trajectory_paths == [baseline]
    assert benign.excluded == []


def test_cache_only_baseline_writes_cache_and_is_reported_as_exclusion(tmp_path: Path) -> None:
    output_dir = tmp_path / "results" / "cache_only"
    artifact_root = output_dir / "artifacts"
    task = _add_attacked_run(
        output_dir=output_dir,
        artifact_root=artifact_root,
        task_id="task_B7_T01",
        suite="B7",
        cache_only_baseline=True,
    )
    result_path, _output_dir, _artifact_root = _write_result(tmp_path / "root", tasks=[task])
    result = _read_json(result_path)
    result["training_artifact_dir"] = str(artifact_root)
    result["canonical_output_dir"] = str(output_dir)
    _write_json(result_path, result)
    raw_root = tmp_path / "pack" / "raw_by_task"

    summary = pack_raw_by_task(
        PackRawByTaskOptions(
            result_paths=[result_path],
            dataset_name="dataset_cache_only",
            raw_by_task_root=raw_root,
        )
    )

    dataset = raw_root / "dataset_cache_only"
    baseline_dir = dataset / "_baselines" / "B7" / "task_B7_T01" / "baseline"
    assert summary["baseline_summary"]["cache_only"] == 1
    assert (baseline_dir / "baseline_cache.json").is_file()
    assert not (baseline_dir / "trajectory.json").exists()
    benign = collect_raw_by_task_trajectories([dataset], role="benign")
    assert benign.trajectory_paths == []
    assert benign.excluded[0]["reason"] == BASELINE_CACHE_ONLY_REASON


def test_fallback_scan_without_aggregate_or_index(tmp_path: Path) -> None:
    output_dir = tmp_path / "results" / "scan_only"
    artifact_root = output_dir / "artifacts"
    _add_attacked_run(
        output_dir=output_dir,
        artifact_root=artifact_root,
        suite="B8",
        task_id="task_B8_T01",
        include_baseline=False,
    )
    raw_root = tmp_path / "pack" / "raw_by_task"

    summary = pack_raw_by_task(
        PackRawByTaskOptions(
            output_dirs=[output_dir],
            dataset_name="scan dataset",
            raw_by_task_root=raw_root,
            include_baselines=False,
        )
    )

    trajectory = raw_root / "scan_dataset" / "B8" / "task_B8_T01" / "run_1" / "trajectory.json"
    assert summary["copied_runs"] == 1
    assert trajectory.is_file()
    assert (trajectory.parent / "workspace_after" / "evidence.txt").is_file()


def test_filters_suite_task_and_run_number(tmp_path: Path) -> None:
    output_dir = tmp_path / "results" / "filters"
    artifact_root = output_dir / "artifacts"
    tasks = [
        _add_attacked_run(output_dir=output_dir, artifact_root=artifact_root, suite="B6", task_id="task_B6_T01", run_number=1),
        _add_attacked_run(output_dir=output_dir, artifact_root=artifact_root, suite="B6", task_id="task_B6_T01", run_number=2),
        _add_attacked_run(output_dir=output_dir, artifact_root=artifact_root, suite="B7", task_id="task_B7_T01", run_number=1),
    ]
    result_path, _output_dir, _artifact_root = _write_result(tmp_path / "root_filters", tasks=tasks)
    result = _read_json(result_path)
    result["training_artifact_dir"] = str(artifact_root)
    result["canonical_output_dir"] = str(output_dir)
    _write_json(result_path, result)
    raw_root = tmp_path / "pack" / "raw_by_task"

    pack_raw_by_task(
        PackRawByTaskOptions(
            result_paths=[result_path],
            dataset_name="filtered",
            raw_by_task_root=raw_root,
            suites=["B6"],
            task_ids=["task_B6_T01"],
            run_numbers=[2],
            include_baselines=False,
        )
    )

    dataset = raw_root / "filtered"
    attacked = collect_raw_by_task_trajectories([dataset], role="attacked")
    assert [path.parent.name for path in attacked.trajectory_paths] == ["run_2"]
    assert not (dataset / "B6" / "task_B6_T01" / "run_1").exists()
    assert not (dataset / "B7").exists()


def test_existing_dataset_refused_by_default(tmp_path: Path) -> None:
    result_path, _output_dir, _artifact_root = _write_result(tmp_path)
    raw_root = tmp_path / "pack" / "raw_by_task"
    (raw_root / "existing").mkdir(parents=True)

    with pytest.raises(PackRawByTaskError, match="already exists"):
        pack_raw_by_task(
            PackRawByTaskOptions(
                result_paths=[result_path],
                dataset_name="existing",
                raw_by_task_root=raw_root,
            )
        )


def test_dry_run_writes_nothing(tmp_path: Path) -> None:
    result_path, _output_dir, _artifact_root = _write_result(tmp_path)
    raw_root = tmp_path / "pack" / "raw_by_task"

    summary = pack_raw_by_task(
        PackRawByTaskOptions(
            result_paths=[result_path],
            dataset_name="dry_run_dataset",
            raw_by_task_root=raw_root,
            dry_run=True,
        )
    )

    assert summary["dry_run"] is True
    assert summary["copied_runs"] == 1
    assert not (raw_root / "dry_run_dataset").exists()


def test_dataset_name_dotdot_is_sanitized_inside_raw_root(tmp_path: Path) -> None:
    result_path, _output_dir, _artifact_root = _write_result(tmp_path)
    raw_root = tmp_path / "pack" / "raw_by_task"

    summary = pack_raw_by_task(
        PackRawByTaskOptions(
            result_paths=[result_path],
            dataset_name="..",
            raw_by_task_root=raw_root,
            dry_run=True,
        )
    )

    assert summary["dataset"] == "__"
    assert Path(summary["dataset_path"]).parent == raw_root


def test_allow_existing_updates_manifest_to_match_existing_and_added_runs(tmp_path: Path) -> None:
    first_result, _first_output, _first_artifact = _write_result(tmp_path / "first")
    second_root = tmp_path / "second"
    second_output = second_root / "results" / "synthetic_run"
    second_artifact = second_output / "run_model_artifacts"
    second_task = _add_attacked_run(
        output_dir=second_output,
        artifact_root=second_artifact,
        suite="B7",
        task_id="task_B7_T01",
        include_baseline=False,
    )
    second_result, _second_output, _second_artifact = _write_result(
        second_root,
        tasks=[second_task],
    )
    raw_root = tmp_path / "pack" / "raw_by_task"

    pack_raw_by_task(
        PackRawByTaskOptions(
            result_paths=[first_result],
            dataset_name="merged_existing",
            raw_by_task_root=raw_root,
            include_baselines=False,
        )
    )
    summary = pack_raw_by_task(
        PackRawByTaskOptions(
            result_paths=[second_result],
            dataset_name="merged_existing",
            raw_by_task_root=raw_root,
            include_baselines=False,
            allow_existing=True,
        )
    )

    dataset = raw_root / "merged_existing"
    manifest = load_raw_by_task_dataset_manifest(dataset)
    attacked = collect_raw_by_task_trajectories([dataset], role="attacked")
    assert summary["manifest_written"] is True
    assert manifest["copied_runs"] == 2
    assert manifest["suite_counts"] == {"B6": 1, "B7": 1}
    assert len(attacked.trajectory_paths) == 2


def test_overwrite_refuses_to_leave_stale_raw_by_task_slots(tmp_path: Path) -> None:
    first_result, _first_output, _first_artifact = _write_result(tmp_path / "first")
    second_root = tmp_path / "second"
    second_output = second_root / "results" / "synthetic_run"
    second_artifact = second_output / "run_model_artifacts"
    second_task = _add_attacked_run(
        output_dir=second_output,
        artifact_root=second_artifact,
        suite="B7",
        task_id="task_B7_T01",
        include_baseline=False,
    )
    second_result, _second_output, _second_artifact = _write_result(
        second_root,
        tasks=[second_task],
    )
    raw_root = tmp_path / "pack" / "raw_by_task"

    pack_raw_by_task(
        PackRawByTaskOptions(
            result_paths=[first_result],
            dataset_name="overwrite_stale",
            raw_by_task_root=raw_root,
            include_baselines=False,
        )
    )

    with pytest.raises(PackRawByTaskError, match="outside this --overwrite selection"):
        pack_raw_by_task(
            PackRawByTaskOptions(
                result_paths=[second_result],
                dataset_name="overwrite_stale",
                raw_by_task_root=raw_root,
                include_baselines=False,
                overwrite=True,
            )
        )


def test_allow_existing_does_not_mix_new_sidecars_into_existing_slot(tmp_path: Path) -> None:
    first_result, _first_output, _first_artifact = _write_result(tmp_path / "first")
    second_result, _second_output, second_artifact = _write_result(tmp_path / "second")
    second_evidence = (
        second_artifact
        / "runs"
        / "task_B6_T01-attack-1"
        / "workspace_after"
        / "evidence.txt"
    )
    second_evidence.write_text("new sidecar that must not be mixed\n", encoding="utf-8")
    raw_root = tmp_path / "pack" / "raw_by_task"

    pack_raw_by_task(
        PackRawByTaskOptions(
            result_paths=[first_result],
            dataset_name="allow_existing_same_slot",
            raw_by_task_root=raw_root,
            include_baselines=False,
        )
    )
    run_dir = raw_root / "allow_existing_same_slot" / "B6" / "task_B6_T01" / "run_1"
    shutil.rmtree(run_dir / "workspace_after")

    summary = pack_raw_by_task(
        PackRawByTaskOptions(
            result_paths=[second_result],
            dataset_name="allow_existing_same_slot",
            raw_by_task_root=raw_root,
            include_baselines=False,
            allow_existing=True,
        )
    )

    assert (run_dir / "trajectory.json").is_file()
    assert not (run_dir / "workspace_after").exists()
    assert any("Skipped attacked sidecars" in warning for warning in summary["warnings"])


def test_overwrite_removes_stale_sidecars_when_source_lacks_them(tmp_path: Path) -> None:
    first_result, _first_output, _first_artifact = _write_result(tmp_path / "first")
    second_result, _second_output, second_artifact = _write_result(tmp_path / "second")
    shutil.rmtree(second_artifact / "runs" / "task_B6_T01-attack-1" / "workspace_after")
    raw_root = tmp_path / "pack" / "raw_by_task"

    pack_raw_by_task(
        PackRawByTaskOptions(
            result_paths=[first_result],
            dataset_name="overwrite_same_slot",
            raw_by_task_root=raw_root,
            include_baselines=False,
        )
    )
    run_dir = raw_root / "overwrite_same_slot" / "B6" / "task_B6_T01" / "run_1"
    assert (run_dir / "workspace_after" / "evidence.txt").is_file()

    summary = pack_raw_by_task(
        PackRawByTaskOptions(
            result_paths=[second_result],
            dataset_name="overwrite_same_slot",
            raw_by_task_root=raw_root,
            include_baselines=False,
            overwrite=True,
        )
    )

    assert (run_dir / "trajectory.json").is_file()
    assert not (run_dir / "workspace_after").exists()
    assert any("No workspace_after sidecar found" in warning for warning in summary["warnings"])


def test_relative_aggregate_paths_prefer_result_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    monkeypatch.chdir(cwd)
    real_parent = tmp_path / "result_parent"
    real_output = real_parent / "relative_output"
    real_artifact = real_output / "artifacts"
    wrong_output = cwd / "relative_output"
    wrong_artifact = wrong_output / "artifacts"
    real_task = _add_attacked_run(
        output_dir=real_output,
        artifact_root=real_artifact,
        model="right/model",
        include_baseline=False,
    )
    _add_attacked_run(
        output_dir=wrong_output,
        artifact_root=wrong_artifact,
        model="wrong/model",
        include_baseline=False,
    )
    real_task["trajectory"].pop("canonical_absolute")
    real_task["trajectory"].pop("attempt_absolute")
    result_path = real_parent / "run_001_right_model.json"
    _write_json(
        result_path,
        {
            "model": "right/model",
            "backend": "openclaw",
            "run_id": "run_001",
            "training_artifact_dir": "relative_output/artifacts",
            "canonical_output_dir": "relative_output",
            "tasks": [real_task],
        },
    )
    raw_root = tmp_path / "pack" / "raw_by_task"

    pack_raw_by_task(
        PackRawByTaskOptions(
            result_paths=[result_path],
            dataset_name="relative_paths",
            raw_by_task_root=raw_root,
            include_baselines=False,
        )
    )

    packed = _read_json(
        raw_root / "relative_paths" / "B6" / "task_B6_T01" / "run_1" / "trajectory.json"
    )
    assert packed["backend"]["model"] == "right/model"


def test_baseline_selection_tries_next_candidate_after_bad_one(tmp_path: Path) -> None:
    result_path, _output_dir, artifact_root = _write_result(tmp_path)
    bad_baseline = _trajectory_payload(
        artifact_root=artifact_root,
        key="bad-baseline",
        suite="B6",
        task_id="task_B6_T01",
        run_number=1,
        role="attacked_attempt",
    )
    bad_path = _write_artifact_run(artifact_root, "bad-baseline", bad_baseline)
    result = _read_json(result_path)
    result["tasks"][0]["baseline"]["artifacts"]["trajectory_absolute"] = str(bad_path)
    _write_json(result_path, result)
    raw_root = tmp_path / "pack" / "raw_by_task"

    summary = pack_raw_by_task(
        PackRawByTaskOptions(
            result_paths=[result_path],
            dataset_name="baseline_fallback",
            raw_by_task_root=raw_root,
        )
    )

    baseline = raw_root / "baseline_fallback" / "_baselines" / "B6" / "task_B6_T01" / "baseline" / "trajectory.json"
    assert _read_json(baseline)["role"] == "benign_baseline"
    assert summary["baseline_summary"]["copied"] == 1
    assert any("Ignoring non-benign baseline trajectory candidate" in warning for warning in summary["warnings"])


def test_arbitrary_baseline_artifact_json_is_not_copied_as_cache(tmp_path: Path) -> None:
    output_dir = tmp_path / "results" / "bogus_baseline"
    artifact_root = output_dir / "artifacts"
    task = _add_attacked_run(
        output_dir=output_dir,
        artifact_root=artifact_root,
        include_baseline=False,
    )
    bogus = artifact_root / "bogus_baseline.json"
    _write_json(bogus, {"not": "a baseline cache"})
    trajectory_path = Path(task["trajectory"]["canonical_absolute"])
    trajectory = _read_json(trajectory_path)
    trajectory["scoring_inputs"]["baseline_artifact_path"] = str(bogus)
    _write_json(trajectory_path, trajectory)
    result_path, _unused_output, _unused_artifact = _write_result(tmp_path / "root", tasks=[task])
    result = _read_json(result_path)
    result["training_artifact_dir"] = str(artifact_root)
    result["canonical_output_dir"] = str(output_dir)
    _write_json(result_path, result)
    raw_root = tmp_path / "pack" / "raw_by_task"

    summary = pack_raw_by_task(
        PackRawByTaskOptions(
            result_paths=[result_path],
            dataset_name="ignore_bogus_baseline_cache",
            raw_by_task_root=raw_root,
        )
    )

    baseline_dir = raw_root / "ignore_bogus_baseline_cache" / "_baselines" / "B6" / "task_B6_T01" / "baseline"
    assert summary["baseline_summary"]["missing"] == 1
    assert not (baseline_dir / "baseline_cache.json").exists()


def test_aggregate_discovery_falls_back_after_corrupt_canonical(tmp_path: Path) -> None:
    result_path, output_dir, _artifact_root = _write_result(tmp_path)
    canonical = output_dir / "trajectories" / "B6" / "task_B6_T01" / "runs" / "run_1" / "trajectory.json"
    canonical.write_text("{bad json", encoding="utf-8")
    raw_root = tmp_path / "pack" / "raw_by_task"

    summary = pack_raw_by_task(
        PackRawByTaskOptions(
            result_paths=[result_path],
            dataset_name="fallback_after_bad_canonical",
            raw_by_task_root=raw_root,
            include_baselines=False,
        )
    )

    packed = raw_root / "fallback_after_bad_canonical" / "B6" / "task_B6_T01" / "run_1" / "trajectory.json"
    assert summary["copied_runs"] == 1
    assert _read_json(packed)["role"] == "attacked_attempt"
    assert any("Skipping unreadable trajectory" in warning for warning in summary["warnings"])


def test_output_dir_discovery_uses_partial_index_plus_canonical_scan(tmp_path: Path) -> None:
    output_dir = tmp_path / "results" / "partial_index"
    artifact_root = output_dir / "artifacts"
    _add_attacked_run(
        output_dir=output_dir,
        artifact_root=artifact_root,
        suite="B6",
        task_id="task_B6_T01",
        include_baseline=False,
    )
    _add_attacked_run(
        output_dir=output_dir,
        artifact_root=artifact_root,
        suite="B7",
        task_id="task_B7_T01",
        include_baseline=False,
    )
    _write_json(
        output_dir / "trajectory_index.json",
        {
            "entries": {
                "B6/task_B6_T01/run_1": {
                    "slot_id": "B6/task_B6_T01/run_1",
                    "task_id": "task_B6_T01",
                    "suite": "B6",
                    "role": "attacked_attempt",
                    "canonical_trajectory_path": "trajectories/B6/task_B6_T01/runs/run_1/trajectory.json",
                }
            }
        },
    )
    raw_root = tmp_path / "pack" / "raw_by_task"

    summary = pack_raw_by_task(
        PackRawByTaskOptions(
            output_dirs=[output_dir],
            dataset_name="partial_index",
            raw_by_task_root=raw_root,
            include_baselines=False,
        )
    )

    assert summary["copied_runs"] == 2
    assert (raw_root / "partial_index" / "B6" / "task_B6_T01" / "run_1" / "trajectory.json").is_file()
    assert (raw_root / "partial_index" / "B7" / "task_B7_T01" / "run_1" / "trajectory.json").is_file()


def test_output_dir_index_can_use_attempt_trajectory_path(tmp_path: Path) -> None:
    output_dir = tmp_path / "results" / "attempt_index"
    artifact_root = output_dir / "artifacts"
    task = _add_attacked_run(
        output_dir=output_dir,
        artifact_root=artifact_root,
        suite="B8",
        task_id="task_B8_T01",
        include_baseline=False,
    )
    shutil.rmtree(output_dir / "trajectories")
    _write_json(
        output_dir / "trajectory_index.json",
        {
            "entries": {
                "B8/task_B8_T01/run_1": {
                    "slot_id": "B8/task_B8_T01/run_1",
                    "task_id": "task_B8_T01",
                    "suite": "B8",
                    "role": "attacked_attempt",
                    "attempt_trajectory_path": task["trajectory"]["attempt_path"],
                }
            }
        },
    )
    raw_root = tmp_path / "pack" / "raw_by_task"

    summary = pack_raw_by_task(
        PackRawByTaskOptions(
            output_dirs=[output_dir],
            artifact_roots=[artifact_root],
            dataset_name="attempt_index",
            raw_by_task_root=raw_root,
            include_baselines=False,
        )
    )

    assert summary["copied_runs"] == 1
    assert (raw_root / "attempt_index" / "B8" / "task_B8_T01" / "run_1" / "trajectory.json").is_file()


def test_mixed_result_and_output_dir_sources_are_both_packed(tmp_path: Path) -> None:
    result_path, _output_dir, _artifact_root = _write_result(tmp_path / "result_source")
    output_dir = tmp_path / "results" / "scan_source"
    artifact_root = output_dir / "artifacts"
    _add_attacked_run(
        output_dir=output_dir,
        artifact_root=artifact_root,
        suite="B9",
        task_id="task_B9_T01",
        include_baseline=False,
    )
    raw_root = tmp_path / "pack" / "raw_by_task"

    summary = pack_raw_by_task(
        PackRawByTaskOptions(
            result_paths=[result_path],
            output_dirs=[output_dir],
            dataset_name="mixed_sources",
            raw_by_task_root=raw_root,
            include_baselines=False,
        )
    )

    assert summary["copied_runs"] == 2
    assert (raw_root / "mixed_sources" / "B6" / "task_B6_T01" / "run_1" / "trajectory.json").is_file()
    assert (raw_root / "mixed_sources" / "B9" / "task_B9_T01" / "run_1" / "trajectory.json").is_file()


def test_relative_baseline_artifact_path_resolves_from_artifact_root(tmp_path: Path) -> None:
    output_dir = tmp_path / "results" / "relative_baseline"
    artifact_root = output_dir / "artifacts"
    task = _add_attacked_run(
        output_dir=output_dir,
        artifact_root=artifact_root,
        suite="B10",
        task_id="task_B10_T01",
        cache_only_baseline=True,
    )
    trajectory_path = Path(task["trajectory"]["canonical_absolute"])
    trajectory = _read_json(trajectory_path)
    trajectory["scoring_inputs"].pop("baseline", None)
    trajectory["scoring_inputs"].pop("baseline_cache_path", None)
    trajectory["scoring_inputs"]["baseline_artifact_path"] = "runs/task_B10_T01-attack-1/baseline.json"
    _write_json(trajectory_path, trajectory)
    result_path, _unused_output, _unused_artifact = _write_result(tmp_path / "root", tasks=[task])
    result = _read_json(result_path)
    result["training_artifact_dir"] = str(artifact_root)
    result["canonical_output_dir"] = str(output_dir)
    _write_json(result_path, result)
    raw_root = tmp_path / "pack" / "raw_by_task"

    summary = pack_raw_by_task(
        PackRawByTaskOptions(
            result_paths=[result_path],
            dataset_name="relative_baseline_artifact",
            raw_by_task_root=raw_root,
        )
    )

    baseline_cache = raw_root / "relative_baseline_artifact" / "_baselines" / "B10" / "task_B10_T01" / "baseline" / "baseline_cache.json"
    assert summary["baseline_summary"]["cache_only"] == 1
    assert _read_json(baseline_cache)["source_task_id"] == "task_B10_T01"


def test_utility_prep_uses_raw_by_task_source_paths_for_baseline_identity(tmp_path: Path) -> None:
    result_path, _output_dir, _artifact_root = _write_result(tmp_path)
    raw_root = tmp_path / "pack" / "raw_by_task"
    pack_raw_by_task(
        PackRawByTaskOptions(
            result_paths=[result_path],
            dataset_name="baseline_identity",
            raw_by_task_root=raw_root,
        )
    )
    baseline_path = raw_root / "baseline_identity" / "_baselines" / "B6" / "task_B6_T01" / "baseline" / "trajectory.json"
    baseline = _read_json(baseline_path)
    baseline.pop("source_task_id", None)
    baseline.pop("clean_task_id", None)
    baseline["task"]["frontmatter"].pop("source_task_id", None)
    baseline["task"]["frontmatter"]["id"] = "task_B6_T01_baseline"
    baseline["run"]["context_metadata"].pop("baseline_task_id", None)
    _write_json(baseline_path, baseline)

    item = prepare_utility_record(_read_json(baseline_path), baseline_path)

    assert item["record"]["identity"]["source_task_id"] == "task_B6_T01"
    assert item["record"]["identity"]["comparison_task_id"] == "task_B6_T01"


def test_utility_prep_prefers_pack_local_raw_by_task_api_sidecars(tmp_path: Path) -> None:
    result_path, _output_dir, _artifact_root = _write_result(tmp_path)
    raw_root = tmp_path / "pack" / "raw_by_task"
    pack_raw_by_task(
        PackRawByTaskOptions(
            result_paths=[result_path],
            dataset_name="api_sidecars",
            raw_by_task_root=raw_root,
        )
    )
    trajectory_path = raw_root / "api_sidecars" / "B6" / "task_B6_T01" / "run_1" / "trajectory.json"

    item = prepare_utility_record(_read_json(trajectory_path), trajectory_path)

    assert item["record"]["api"]["audit_exists"] is True
    assert item["record"]["api"]["endpoints_exists"] is True
    assert item["record"]["api"]["audit_path"] == str(trajectory_path.parent / "api" / "audit.json")
    assert item["record"]["api"]["endpoints_path"] == str(
        trajectory_path.parent / "api" / "endpoints.json"
    )


def test_cli_wrapper_smoke_prints_json_summary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    result_path, _output_dir, _artifact_root = _write_result(tmp_path)
    raw_root = tmp_path / "pack" / "raw_by_task"
    import scripts.actbench_pack_raw_by_task as wrapper  # noqa: E402

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "actbench_pack_raw_by_task.py",
            "--result",
            str(result_path),
            "--dataset-name",
            "cli dataset",
            "--raw-by-task-root",
            str(raw_root),
            "--compact",
        ],
    )

    with pytest.raises(SystemExit) as excinfo:
        wrapper.main()

    assert excinfo.value.code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["dataset"] == "cli_dataset"
    assert payload["copied_runs"] == 1


def test_module_cli_main_accepts_output_dir_source(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output_dir = tmp_path / "results" / "cli_scan"
    artifact_root = output_dir / "artifacts"
    _add_attacked_run(output_dir=output_dir, artifact_root=artifact_root, suite="B9", task_id="task_B9_T01", include_baseline=False)
    raw_root = tmp_path / "pack" / "raw_by_task"

    exit_code = packer_main(
        [
            "--output-dir",
            str(output_dir),
            "--dataset-name",
            "module_cli",
            "--raw-by-task-root",
            str(raw_root),
            "--no-baselines",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["dataset"] == "module_cli"
    assert (raw_root / "module_cli" / "B9" / "task_B9_T01" / "run_1" / "trajectory.json").is_file()
