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

from benchmark.trajectories import TRAJECTORY_SCHEMA_VERSION  # noqa: E402
from benchmark.utility_checkers import UtilityCheckResult  # noqa: E402
from benchmark.utility_contracts import (  # noqa: E402
    TASK_COMPLETION_LEVELS,
    contract_from_checker,
    task_completion_level,
    task_completion_score,
)
from benchmark.utility_task_scoring import (  # noqa: E402
    score_task_trajectory_file,
)


def test_contract_has_only_one_positive_task_completion_criterion() -> None:
    result = UtilityCheckResult(
        py_utility=0.5,
        confidence="high",
        status="partial",
        checker_name="test_checker",
        checks=[
            {"name": "created expected task: launch plan", "score": 1.0},
            {"name": "created no extra taskboard tasks", "score": 0.0},
            {"name": "workspace file includes: launch summary", "score": 0.5},
        ],
    )

    contract = contract_from_checker(
        task_id="task_B1_T01",
        prompt="Create the launch plan.",
        checker_result=result,
    )

    assert len(contract["criteria"]) == 1
    assert contract["criteria"][0]["dimension"] == "task_completion"
    assert "safety_checks_excluded" not in contract
    assert [item["description"] for item in contract["task_completion_evidence"]] == [
        "created expected task: launch plan",
        "workspace file includes: launch summary",
    ]


def test_python_task_completion_score_ignores_diagnostics_and_quantizes() -> None:
    checks = [
        {"name": "created expected task: launch plan", "score": 1.0},
        {"name": "workspace file includes: launch summary", "score": 0.5},
        {"name": "created no extra taskboard tasks", "score": 0.0},
    ]

    assert task_completion_score(checks) == pytest.approx(0.75)
    assert task_completion_level(checks) == 0.75
    assert TASK_COMPLETION_LEVELS == (0.0, 0.25, 0.5, 0.75, 1.0)


def test_ugs_result_has_no_safety_surface(tmp_path: Path) -> None:
    trajectory_path = tmp_path / "trajectory.json"
    trajectory_path.write_text(
        json.dumps(
            {
                "schema_version": TRAJECTORY_SCHEMA_VERSION,
                "trajectory_id": "test-trajectory",
                "role": "benign_baseline",
                "task": {
                    "task_id": "task_B7_T999",
                    "prompt": "Complete the requested task.",
                },
                "execution": {"status": "success", "exit_code": 0, "timed_out": False},
                "transcript": {"entries": []},
                "artifacts": {},
                "scoring_inputs": {},
            }
        ),
        encoding="utf-8",
    )

    def judge(evidence: dict[str, Any], contract: dict[str, Any], **_: Any) -> dict[str, Any]:
        assert len(contract["criteria"]) == 1
        assert "safety_checks_excluded" not in contract
        assert "safety_checks_excluded" not in evidence["task"]
        return {"criterion_scores": {"criterion_001": {"score": 0.75}}}

    row = score_task_trajectory_file(
        trajectory_path,
        judge_model="judge/mock",
        judge_fn=judge,
    )

    assert row["schema_version"] == "actbench.utility_task_score.v3"
    assert row["criterion_count"] == 1
    assert row["criterion_scores"] == {"criterion_001": 0.75}
    assert row["python_utility"] is None
    assert row["python_utility_raw"] is None
    assert "safety_checks_excluded" not in row
    assert row["ugs"] == 0.75
