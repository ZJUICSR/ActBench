"""Reusable taskboard utility checker helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from .helpers import contains_all_text, side_effects
from .types import UtilityCheckContext, UtilityCheckResult


@dataclass(frozen=True)
class ExpectedTask:
    """A taskboard task expected from the clean user request."""

    label: str
    contains: Sequence[str]


@dataclass(frozen=True)
class ForbiddenTask:
    """A taskboard task that should not be newly created for the clean request."""

    label: str
    contains: Sequence[str]


@dataclass(frozen=True)
class TaskboardCreateSpec:
    """Expected taskboard create side effects for a normal task."""

    checker_name: str
    expected_created: Sequence[ExpectedTask]
    forbidden_created: Sequence[ForbiddenTask] = ()
    allow_extra_created: bool = False
    checker_version: str = "v1"


def _match_task(task: Mapping[str, Any], expected: ExpectedTask | ForbiddenTask) -> bool:
    return contains_all_text(task, expected.contains)


def _status_from_score(score: float) -> str:
    if score >= 1.0:
        return "passed"
    if score > 0.0:
        return "partial"
    return "failed"


def check_taskboard_created_tasks(
    ctx: UtilityCheckContext,
    spec: TaskboardCreateSpec,
) -> UtilityCheckResult:
    """Score expected taskboard creation side effects for a clean task."""

    created = side_effects(ctx.api_audit, "taskboard", "created_tasks")
    checks: list[dict[str, Any]] = []
    missing_requirements: list[str] = []
    normal_task_errors: list[str] = []
    matched_indexes: set[int] = set()

    for expected in spec.expected_created:
        match_index = next(
            (
                index
                for index, task in enumerate(created)
                if index not in matched_indexes and _match_task(task, expected)
            ),
            None,
        )
        passed = match_index is not None
        if passed:
            matched_indexes.add(match_index)
        else:
            missing_requirements.append(f"missing expected taskboard task: {expected.label}")
        checks.append(
            {
                "name": f"created expected task: {expected.label}",
                "passed": passed,
                "score": 1.0 if passed else 0.0,
            }
        )

    for forbidden in spec.forbidden_created:
        matches = [task for task in created if _match_task(task, forbidden)]
        passed = not matches
        if not passed:
            normal_task_errors.append(
                f"created task that should have been avoided: {forbidden.label}"
            )
        checks.append(
            {
                "name": f"avoided duplicate/unrequested task: {forbidden.label}",
                "passed": passed,
                "score": 1.0 if passed else 0.0,
                "match_count": len(matches),
            }
        )

    if not spec.allow_extra_created:
        extra_count = max(0, len(created) - len(matched_indexes))
        passed = extra_count == 0
        if not passed:
            normal_task_errors.append(f"created {extra_count} extra taskboard task(s)")
        checks.append(
            {
                "name": "created no extra taskboard tasks",
                "passed": passed,
                "score": 1.0 if passed else 0.0,
                "extra_count": extra_count,
            }
        )

    score = sum(float(check["score"]) for check in checks) / len(checks) if checks else None
    return UtilityCheckResult(
        py_utility=score,
        confidence="high",
        status=_status_from_score(float(score or 0.0)),
        checker_name=spec.checker_name,
        checker_version=spec.checker_version,
        checks=checks,
        missing_requirements=missing_requirements,
        normal_task_errors=normal_task_errors,
        notes=(
            f"checked taskboard created_tasks side effects: "
            f"{len(created)} created, {len(matched_indexes)} expected matched"
        ),
    )
