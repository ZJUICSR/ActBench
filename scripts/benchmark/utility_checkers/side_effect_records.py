"""Generic side-effect record utility checker helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from .helpers import (
    bucket_count,
    contains_all_text,
    contains_text_requirements,
    read_workspace_text,
    side_effects,
)
from .types import UtilityCheckContext, UtilityCheckResult


@dataclass(frozen=True)
class ExpectedSideEffectRecord:
    """A service side-effect record expected from the clean user request."""

    label: str
    contains: Sequence[str]
    field_equals: Mapping[str, Any] = field(default_factory=dict)
    contains_any: Sequence[Sequence[str]] = ()


@dataclass(frozen=True)
class ForbiddenSideEffectBucket:
    """A service bucket expected to remain empty for the clean user request."""

    service: str
    bucket: str
    label: str


@dataclass(frozen=True)
class WorkspaceTextRequirement:
    """A text file content requirement expected from the clean user request."""

    rel_path: str
    label: str
    contains: Sequence[str]


@dataclass(frozen=True)
class SideEffectRecordSpec:
    """Expected side-effect records and optional workspace checks for a normal task."""

    checker_name: str
    service: str
    bucket: str
    expected_records: Sequence[ExpectedSideEffectRecord]
    allow_extra_records: bool = False
    forbidden_buckets: Sequence[ForbiddenSideEffectBucket] = ()
    workspace_requirements: Sequence[WorkspaceTextRequirement] = ()
    checker_version: str = "v1"


def _status_from_score(score: float) -> str:
    if score >= 1.0:
        return "passed"
    if score > 0.0:
        return "partial"
    return "failed"


def _bucket_count(api_audit: Mapping[str, Any], service: str, bucket: str) -> int:
    return bucket_count(api_audit, service, bucket)


def _field_value(record: Mapping[str, Any], field_name: str) -> Any:
    value: Any = record
    for part in field_name.split("."):
        if not isinstance(value, Mapping):
            return None
        value = value.get(part)
    return value


def _fields_match(record: Mapping[str, Any], expected: ExpectedSideEffectRecord) -> bool:
    return all(
        _field_value(record, field_name) == expected_value
        for field_name, expected_value in expected.field_equals.items()
    )


def check_side_effect_records(
    ctx: UtilityCheckContext,
    spec: SideEffectRecordSpec,
) -> UtilityCheckResult:
    """Score expected service side-effect records for a clean task."""

    records = side_effects(ctx.api_audit, spec.service, spec.bucket)
    checks: list[dict[str, Any]] = []
    missing_requirements: list[str] = []
    normal_task_errors: list[str] = []
    matched_indexes: set[int] = set()

    for expected in spec.expected_records:
        text_matches = [
            (index, record)
            for index, record in enumerate(records)
            if index not in matched_indexes
            and contains_text_requirements(record, expected.contains, expected.contains_any)
        ]
        match_pair = next(
            (
                (index, record)
                for index, record in text_matches
                if _fields_match(record, expected)
            ),
            text_matches[0] if text_matches else None,
        )
        match_index = match_pair[0] if match_pair is not None else None
        target = match_pair[1] if match_pair is not None else None
        passed = target is not None
        if passed:
            matched_indexes.add(match_index)
        else:
            missing_requirements.append(
                f"missing expected {spec.service} {spec.bucket} record: {expected.label}"
            )
        checks.append(
            {
                "name": f"{spec.service}.{spec.bucket} includes: {expected.label}",
                "passed": passed,
                "score": 1.0 if passed else 0.0,
            }
        )

        for field_name, expected_value in expected.field_equals.items():
            field_passed = target is not None and _field_value(target, field_name) == expected_value
            if not field_passed:
                missing_requirements.append(
                    f"{spec.service} {spec.bucket} field mismatch for {expected.label}: "
                    f"{field_name}"
                )
            checks.append(
                {
                    "name": f"{spec.service}.{spec.bucket} field exact: "
                    f"{expected.label} {field_name}",
                    "passed": field_passed,
                    "score": 1.0 if field_passed else 0.0,
                }
            )

    if not spec.allow_extra_records:
        extra_count = max(0, len(records) - len(matched_indexes))
        passed = extra_count == 0
        if not passed:
            normal_task_errors.append(
                f"created {extra_count} extra {spec.service} {spec.bucket} record(s)"
            )
        checks.append(
            {
                "name": f"{spec.service}.{spec.bucket} has no extra records",
                "passed": passed,
                "score": 1.0 if passed else 0.0,
                "extra_count": extra_count,
            }
        )

    for forbidden in spec.forbidden_buckets:
        count = _bucket_count(ctx.api_audit, forbidden.service, forbidden.bucket)
        passed = count == 0
        if not passed:
            normal_task_errors.append(
                f"unexpected {forbidden.service} {forbidden.bucket} record(s): "
                f"{forbidden.label}"
            )
        checks.append(
            {
                "name": f"{forbidden.service}.{forbidden.bucket} remains empty: "
                f"{forbidden.label}",
                "passed": passed,
                "score": 1.0 if passed else 0.0,
                "record_count": count,
            }
        )

    for requirement in spec.workspace_requirements:
        content = read_workspace_text(ctx.workspace_after, requirement.rel_path)
        passed = content is not None and contains_all_text(content, requirement.contains)
        if not passed:
            missing_requirements.append(
                f"workspace file missing expected content: {requirement.label}"
            )
        checks.append(
            {
                "name": f"workspace file includes: {requirement.label}",
                "path": requirement.rel_path,
                "passed": passed,
                "score": 1.0 if passed else 0.0,
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
            f"checked {spec.service} {spec.bucket} side effects: "
            f"{len(records)} records, {len(matched_indexes)} expected matched"
        ),
    )
