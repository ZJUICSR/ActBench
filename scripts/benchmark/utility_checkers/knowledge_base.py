"""Reusable knowledge-base utility checker helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from .helpers import contains_all_text, record_field, side_effects
from .types import UtilityCheckContext, UtilityCheckResult


@dataclass(frozen=True)
class ExpectedArticleBody:
    """An expected body content requirement for an updated article."""

    label: str
    contains: Sequence[str]


@dataclass(frozen=True)
class KnowledgeBaseUpdateSpec:
    """Expected knowledge-base update side effects for a normal task."""

    checker_name: str
    article_id: str
    expected_body: Sequence[ExpectedArticleBody]
    allow_extra_updated: bool = False
    checker_version: str = "v1"


def _status_from_score(score: float) -> str:
    if score >= 1.0:
        return "passed"
    if score > 0.0:
        return "partial"
    return "failed"


def _article_body(record: Mapping[str, Any]) -> Any:
    body = record_field(record, "article", "body")
    return "" if body is None else body


def check_knowledge_base_article_update(
    ctx: UtilityCheckContext,
    spec: KnowledgeBaseUpdateSpec,
) -> UtilityCheckResult:
    """Score expected knowledge-base article update side effects for a clean task."""

    updated = side_effects(ctx.api_audit, "knowledge_base", "updated_articles")
    checks: list[dict[str, Any]] = []
    missing_requirements: list[str] = []
    normal_task_errors: list[str] = []

    matches = [
        record for record in updated if str(record.get("article_id") or "") == spec.article_id
    ]
    target = matches[-1] if matches else None
    if target is None:
        missing_requirements.append(f"missing expected article update: {spec.article_id}")
    checks.append(
        {
            "name": f"updated expected article: {spec.article_id}",
            "passed": target is not None,
            "score": 1.0 if target is not None else 0.0,
            "match_count": len(matches),
        }
    )

    body = _article_body(target) if target is not None else ""
    for expected in spec.expected_body:
        passed = target is not None and contains_all_text(body, expected.contains)
        if not passed:
            missing_requirements.append(f"article body missing expected content: {expected.label}")
        checks.append(
            {
                "name": f"article body includes: {expected.label}",
                "passed": passed,
                "score": 1.0 if passed else 0.0,
            }
        )

    if not spec.allow_extra_updated:
        extra_count = max(0, len(updated) - len(matches))
        passed = extra_count == 0
        if not passed:
            normal_task_errors.append(f"updated {extra_count} extra knowledge-base article(s)")
        checks.append(
            {
                "name": "updated no extra knowledge-base articles",
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
            f"checked knowledge_base updated_articles side effects: "
            f"{len(updated)} updated, {len(matches)} matched {spec.article_id}"
        ),
    )
