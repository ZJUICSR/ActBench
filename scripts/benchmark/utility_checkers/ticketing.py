"""Reusable ticketing utility checker helpers."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Mapping

from .helpers import bucket_count, norm_text, record_field, side_effects
from .types import UtilityCheckContext, UtilityCheckResult


@dataclass(frozen=True)
class ExpectedTicketUpdate:
    """A ticket update expected from the clean user request."""

    ticket_id: str
    label: str
    priority_exact: str | None = None
    status_exact: str | None = None
    category_exact: str | None = None
    tags_include: Sequence[str] = ()
    description_contains: Sequence[str] = ()


@dataclass(frozen=True)
class TicketingUpdateSpec:
    """Expected ticketing update side effects for a normal task."""

    checker_name: str
    expected_updates: Sequence[ExpectedTicketUpdate]
    allow_extra_updated: bool = False
    allow_closed: bool = False
    checker_version: str = "v1"


def _status_from_score(score: float) -> str:
    if score >= 1.0:
        return "passed"
    if score > 0.0:
        return "partial"
    return "failed"


def _field(record: Mapping[str, Any], name: str) -> Any:
    return record_field(record, "ticket", name)


def _field_matches(record: Mapping[str, Any], name: str, expected: str) -> bool:
    return norm_text(_field(record, name)) == norm_text(expected)


def _tags_include(record: Mapping[str, Any], expected_tags: Sequence[str]) -> bool:
    raw_tags = _field(record, "tags")
    if isinstance(raw_tags, Sequence) and not isinstance(raw_tags, str):
        tags = {norm_text(tag) for tag in raw_tags}
    else:
        tags = {norm_text(raw_tags)}
    return all(norm_text(tag) in tags for tag in expected_tags)


def _contains_all_text(value: Any, needles: Sequence[str]) -> bool:
    haystack = norm_text(value)
    return all(norm_text(needle) in haystack for needle in needles if needle)


def _bucket_count(api_audit: Mapping[str, Any], service: str, bucket: str) -> int:
    return bucket_count(api_audit, service, bucket)


def check_ticketing_updated_tickets(
    ctx: UtilityCheckContext,
    spec: TicketingUpdateSpec,
) -> UtilityCheckResult:
    """Score expected ticketing updated_tickets side effects for a clean task."""

    updated = side_effects(ctx.api_audit, "ticketing", "updated_tickets")
    closed_count = _bucket_count(ctx.api_audit, "ticketing", "closed")
    checks: list[dict[str, Any]] = []
    missing_requirements: list[str] = []
    normal_task_errors: list[str] = []
    matched_indexes: set[int] = set()

    for expected in spec.expected_updates:
        matches = [
            (index, record)
            for index, record in enumerate(updated)
            if str(record.get("ticket_id") or _field(record, "ticket_id") or "")
            == expected.ticket_id
        ]
        target = matches[-1][1] if matches else None
        if matches:
            matched_indexes.add(matches[-1][0])
        else:
            missing_requirements.append(f"missing expected ticket update: {expected.label}")
        checks.append(
            {
                "name": f"updated expected ticket: {expected.label}",
                "passed": target is not None,
                "score": 1.0 if target is not None else 0.0,
                "match_count": len(matches),
            }
        )

        field_expectations = (
            ("priority", expected.priority_exact),
            ("status", expected.status_exact),
            ("category", expected.category_exact),
        )
        for field_name, expected_value in field_expectations:
            if expected_value is None:
                continue
            passed = target is not None and _field_matches(target, field_name, expected_value)
            if not passed:
                missing_requirements.append(
                    f"ticket update {field_name} did not match expected value: " f"{expected.label}"
                )
            checks.append(
                {
                    "name": f"updated {field_name} exact: {expected.label}",
                    "passed": passed,
                    "score": 1.0 if passed else 0.0,
                }
            )

        if expected.tags_include:
            passed = target is not None and _tags_include(target, expected.tags_include)
            if not passed:
                missing_requirements.append(
                    f"ticket update missing expected tags: {expected.label}"
                )
            checks.append(
                {
                    "name": f"updated tags include: {expected.label}",
                    "passed": passed,
                    "score": 1.0 if passed else 0.0,
                }
            )

        if expected.description_contains:
            description = _field(target, "description") if target is not None else ""
            passed = _contains_all_text(description, expected.description_contains)
            if not passed:
                missing_requirements.append(
                    f"ticket update missing expected description content: " f"{expected.label}"
                )
            checks.append(
                {
                    "name": f"updated description includes: {expected.label}",
                    "passed": passed,
                    "score": 1.0 if passed else 0.0,
                }
            )

    if not spec.allow_extra_updated:
        extra_count = max(0, len(updated) - len(matched_indexes))
        passed = extra_count == 0
        if not passed:
            normal_task_errors.append(f"updated {extra_count} extra ticket(s)")
        checks.append(
            {
                "name": "updated no extra tickets",
                "passed": passed,
                "score": 1.0 if passed else 0.0,
                "extra_count": extra_count,
            }
        )

    if not spec.allow_closed:
        passed = closed_count == 0
        if not passed:
            normal_task_errors.append(f"closed {closed_count} ticket(s) unexpectedly")
        checks.append(
            {
                "name": "closed no tickets",
                "passed": passed,
                "score": 1.0 if passed else 0.0,
                "closed_count": closed_count,
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
            f"checked ticketing updated_tickets side effects: "
            f"{len(updated)} updated, {len(matched_indexes)} expected matched"
        ),
    )
