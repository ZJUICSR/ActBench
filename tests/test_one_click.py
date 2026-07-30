from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from benchmark import one_click  # noqa: E402


def _config(
    tmp_path: Path,
    *,
    backend: str = "fake",
    model: str = "fake/model",
    suite: str = "task_fake",
    score_mode: str = one_click.COMBINED_AGS_MODE,
    judge_model: str | None = "judge/model",
    runs: int = 1,
    skip_baseline_gen: bool = False,
) -> one_click.OneClickConfig:
    return one_click.OneClickConfig(
        backend=backend,
        model=model,
        suite=suite,
        score_mode=score_mode,
        judge_model=judge_model,
        tasks_dir=tmp_path / "tasks",
        output_root=tmp_path / "one_click",
        runs=runs,
        run_workers=1,
        timeout_multiplier=1.0,
        execution_retries=0,
        retry_status="error,timeout",
        skip_baseline_gen=skip_baseline_gen,
        verbose=False,
        self_test=False,
    )


def _plan(
    tmp_path: Path,
    *,
    task_ids: tuple[str, ...] = ("task_fake",),
    runs: int = 1,
    score_mode: str = one_click.COMBINED_AGS_MODE,
    skip_baseline_gen: bool = False,
) -> one_click.OneClickRunPlan:
    config = _config(
        tmp_path,
        score_mode=score_mode,
        judge_model="judge/model" if score_mode == one_click.COMBINED_AGS_MODE else None,
        runs=runs,
        skip_baseline_gen=skip_baseline_gen,
    )
    return one_click.OneClickRunPlan(
        config=config,
        collection_suite=config.suite,
        selected_task_ids=task_ids,
        expected_attempts=len(task_ids) * runs,
        backend_supports_parallel_runs=True,
    )


def _write_collection(
    collection_dir: Path,
    *,
    plan: one_click.OneClickRunPlan,
    status: str = "success",
    backend: str | None = None,
    model: str | None = None,
    with_baseline: bool = True,
) -> Path:
    trajectory_dir = collection_dir / "trajectories" / "B9" / "task_fake" / "runs" / "run_1"
    trajectory_dir.mkdir(parents=True)
    trajectory_path = trajectory_dir / "trajectory.json"
    trajectory_path.write_text("{}\n", encoding="utf-8")
    payload = {
        "workflow": "trajectory_collection",
        "backend": backend or plan.config.backend,
        "model": model or plan.config.model,
        "suite": plan.collection_suite,
        "tasks": [
            {
                "task_id": plan.selected_task_ids[0],
                "status": status,
                "backend_metadata": {"run_number": 1},
                "trajectory": {
                    "canonical_path": "trajectories/B9/task_fake/runs/run_1/trajectory.json"
                },
                "baseline": {"role": "benign_baseline"} if with_baseline else None,
            }
        ],
    }
    path = collection_dir / "0001_fake-model.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _write_score(score_path: Path, *, plan: one_click.OneClickRunPlan) -> None:
    payload = {
        "schema_version": one_click.OFFLINE_SCORE_SCHEMA_VERSION,
        "scoring_mode": "combined_ags"
        if plan.config.score_mode == one_click.COMBINED_AGS_MODE
        else "automated_only",
        "scoring_semantics": "actbench_ags"
        if plan.config.score_mode == one_click.COMBINED_AGS_MODE
        else "actbench_automated_only",
        "trajectory_count": plan.expected_attempts,
        "valid_scores": plan.expected_attempts,
        "evaluation_errors": 0,
        "mean_ags": 0.9,
        "asr": 1.0,
        "pass@k": {},
        "attack_reproduced": True,
        "llm_invoked": plan.config.score_mode == one_click.COMBINED_AGS_MODE,
        "results": [{} for _ in range(plan.expected_attempts)],
    }
    score_path.write_text(json.dumps(payload), encoding="utf-8")


def test_parse_args_defaults_to_representative_combined_ags_with_explicit_judge() -> None:
    config = one_click.parse_args(
        ["--backend", "fake", "--model", "fake/model", "--judge-model", "judge/model"]
    )

    assert config.suite == one_click.DEFAULT_SUITE
    assert config.score_mode == one_click.COMBINED_AGS_MODE
    assert config.judge_model == "judge/model"
    assert config.runs == 1
    assert config.run_workers == 1
    assert config.skip_baseline_gen is False


def test_parse_args_requires_judge_for_default_combined_ags() -> None:
    with pytest.raises(SystemExit):
        one_click.parse_args(["--backend", "fake", "--model", "fake/model"])


def test_parse_args_rejects_judge_with_automated_mode() -> None:
    with pytest.raises(SystemExit):
        one_click.parse_args(
            [
                "--backend",
                "fake",
                "--model",
                "fake/model",
                "--score-mode",
                one_click.AUTOMATED_ONLY_MODE,
                "--judge-model",
                "judge/model",
            ]
        )


def test_parse_args_self_test_forces_fake_automated_configuration(tmp_path: Path) -> None:
    config = one_click.parse_args(["--self-test", "--output-root", str(tmp_path)])

    assert config.self_test is True
    assert config.backend == "fake"
    assert config.model == one_click.SELF_TEST_MODEL
    assert config.suite == one_click.SELF_TEST_SUITE
    assert config.score_mode == one_click.AUTOMATED_ONLY_MODE
    assert config.judge_model is None
    assert config.skip_baseline_gen is True


def test_resolve_suite_selector_maps_representative_to_fixed_b1_b15_tasks() -> None:
    assert one_click.resolve_suite_selector("representative") == ",".join(
        f"task_B{i}_T01" for i in range(1, 16)
    )
    assert one_click.REPRESENTATIVE_TASK_IDS[0] == "task_B1_T01"
    assert one_click.REPRESENTATIVE_TASK_IDS[-1] == "task_B15_T01"
    assert one_click.resolve_suite_selector("B9") == "B9"


def test_resolve_run_plan_uses_real_representative_tasks(tmp_path: Path) -> None:
    config = one_click.OneClickConfig(
        backend="fake",
        model="fake/model",
        suite="representative",
        score_mode=one_click.COMBINED_AGS_MODE,
        judge_model="judge/model",
        tasks_dir=ROOT / "tasks",
        output_root=tmp_path,
    )

    plan = one_click.resolve_run_plan(config)

    assert plan.collection_suite == one_click.REPRESENTATIVE_SUITE_SELECTOR
    assert plan.selected_task_ids == one_click.REPRESENTATIVE_TASK_IDS
    assert plan.expected_attempts == 15


def test_collection_command_preserves_baselines_by_default(tmp_path: Path) -> None:
    plan = _plan(tmp_path)
    command = one_click.build_collection_command(plan, tmp_path / "collection")

    assert "--skip-baseline-gen" not in command
    assert command[0] == sys.executable
    assert str(SCRIPTS / "actbench.py") in command
    assert "--judge-model" in command
    assert "judge/model" in command


def test_collection_command_can_skip_baselines(tmp_path: Path) -> None:
    plan = _plan(tmp_path, skip_baseline_gen=True)
    command = one_click.build_collection_command(plan, tmp_path / "collection")

    assert "--skip-baseline-gen" in command


def test_scoring_command_scores_only_invocation_trajectory_tree(tmp_path: Path) -> None:
    plan = _plan(tmp_path)
    invocation_dir = tmp_path / "invoke"

    command = one_click.build_scoring_command(plan, invocation_dir)

    assert command[0] == sys.executable
    assert str(SCRIPTS / "actbench_score.py") in command
    assert "--trajectory" in command
    assert str(invocation_dir / "collection" / "trajectories") in command
    assert "--judge-model" in command
    assert "judge/model" in command


def test_find_collection_result_ignores_collection_summary(tmp_path: Path) -> None:
    collection_dir = tmp_path / "collection"
    collection_dir.mkdir()
    plan = _plan(tmp_path)
    result_path = _write_collection(collection_dir, plan=plan)
    (collection_dir / "actbench_summary_0001_fake-model.json").write_text(
        json.dumps(
            {
                "workflow": "trajectory_collection",
                "summary_kind": "trajectory_collection",
                "tasks": [],
            }
        ),
        encoding="utf-8",
    )

    assert one_click.find_collection_result(collection_dir) == result_path


def test_validate_collection_result_accepts_valid_collection(tmp_path: Path) -> None:
    plan = _plan(tmp_path)
    collection_dir = tmp_path / "collection"
    result_path = _write_collection(collection_dir, plan=plan)

    result = one_click.validate_collection_result(result_path, plan)

    assert result["summary"]["successful_attempts"] == 1
    assert result["summary"]["canonical_trajectories"] == 1
    assert result["summary"]["baseline_tasks_missing"] == 0


def test_validate_collection_result_warns_on_missing_baseline(tmp_path: Path) -> None:
    plan = _plan(tmp_path)
    collection_dir = tmp_path / "collection"
    result_path = _write_collection(collection_dir, plan=plan, with_baseline=False)

    result = one_click.validate_collection_result(result_path, plan)

    assert result["summary"]["baseline_tasks_missing"] == 1
    assert result["summary"]["missing_baseline_task_ids"] == ["task_fake"]


def test_validate_collection_result_fails_on_execution_error(tmp_path: Path) -> None:
    plan = _plan(tmp_path)
    collection_dir = tmp_path / "collection"
    result_path = _write_collection(collection_dir, plan=plan, status="error")

    with pytest.raises(one_click.OneClickCollectionError):
        one_click.validate_collection_result(result_path, plan)


def test_validate_collection_result_fails_on_wrong_backend(tmp_path: Path) -> None:
    plan = _plan(tmp_path)
    collection_dir = tmp_path / "collection"
    result_path = _write_collection(collection_dir, plan=plan, backend="openclaw")

    with pytest.raises(one_click.OneClickCollectionError):
        one_click.validate_collection_result(result_path, plan)


def test_validate_score_result_accepts_valid_adverse_result(tmp_path: Path) -> None:
    plan = _plan(tmp_path)
    score_path = tmp_path / "score.json"
    _write_score(score_path, plan=plan)

    result = one_click.validate_score_result(score_path, plan)

    assert result["summary"]["attack_reproduced"] is True
    assert result["summary"]["evaluation_errors"] == 0


def test_validate_score_result_rejects_partial_errors_even_when_scorer_would_succeed(
    tmp_path: Path,
) -> None:
    plan = _plan(tmp_path, task_ids=("task_one", "task_two"), runs=1)
    score_path = tmp_path / "score.json"
    payload = {
        "schema_version": one_click.OFFLINE_SCORE_SCHEMA_VERSION,
        "scoring_mode": "combined_ags",
        "trajectory_count": 2,
        "valid_scores": 1,
        "evaluation_errors": 1,
        "results": [{}, {"evaluation_error": "boom"}],
    }
    score_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(one_click.OneClickPartialScoringError):
        one_click.validate_score_result(score_path, plan)


def test_self_test_end_to_end_uses_fake_backend_and_writes_manifest(tmp_path: Path) -> None:
    exit_code = one_click.main(["--self-test", "--output-root", str(tmp_path / "runs")])

    assert exit_code == 0
    invocation_dirs = sorted((tmp_path / "runs").iterdir())
    assert len(invocation_dirs) == 1
    invocation_dir = invocation_dirs[0]
    manifest = json.loads((invocation_dir / "one_click_result.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "complete"
    assert manifest["request"]["backend"] == "fake"
    assert manifest["request"]["score_mode"] == one_click.AUTOMATED_ONLY_MODE
    assert manifest["resolved"]["task_ids"] == [one_click.SELF_TEST_SUITE]
    assert manifest["scoring"]["trajectory_count"] == 1
    assert manifest["scoring"]["valid_scores"] == 1
    assert manifest["scoring"]["evaluation_errors"] == 0
    canonical = list((invocation_dir / "collection" / "trajectories").rglob("trajectory.json"))
    assert len(canonical) == 1
    score = json.loads((invocation_dir / "score.json").read_text(encoding="utf-8"))
    assert score["trajectory_count"] == 1
    assert score["valid_scores"] == 1
    assert score["evaluation_errors"] == 0
