"""Small helper functions for task-specific utility checkers."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Optional


def service_audit(api_audit: Mapping[str, Any], service: str) -> Mapping[str, Any]:
    audit = api_audit.get(service) if isinstance(api_audit, Mapping) else None
    return audit if isinstance(audit, Mapping) else {}


def side_effect_bucket(api_audit: Mapping[str, Any], service: str, bucket: str) -> Any:
    audit = service_audit(api_audit, service)
    raw = audit.get(bucket)
    if raw is None and isinstance(audit.get("side_effect_buckets"), Mapping):
        raw = audit["side_effect_buckets"].get(bucket)
    return raw


def side_effects(
    api_audit: Mapping[str, Any], service: str, bucket: str
) -> list[Mapping[str, Any]]:
    raw = side_effect_bucket(api_audit, service, bucket)
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, Mapping)]


def bucket_count(api_audit: Mapping[str, Any], service: str, bucket: str) -> int:
    raw = side_effect_bucket(api_audit, service, bucket)
    if isinstance(raw, Sequence) and not isinstance(raw, str):
        return len(raw)
    if isinstance(raw, Mapping):
        return len(raw)
    return 1 if raw else 0


def record_field(record: Mapping[str, Any], nested_key: str, name: str) -> Any:
    changes = record.get("changes") if isinstance(record.get("changes"), Mapping) else {}
    nested = record.get(nested_key) if isinstance(record.get(nested_key), Mapping) else {}
    for mapping in (changes, nested, record):
        if name in mapping:
            return mapping[name]
    return None


def calls_to(
    api_audit: Mapping[str, Any], service: str, endpoint_suffix: str
) -> list[Mapping[str, Any]]:
    audit = service_audit(api_audit, service)
    calls = audit.get("calls")
    if not isinstance(calls, list):
        return []
    matched: list[Mapping[str, Any]] = []
    for call in calls:
        if not isinstance(call, Mapping):
            continue
        endpoint = str(call.get("endpoint") or call.get("path") or "")
        if endpoint.endswith(endpoint_suffix):
            matched.append(call)
    return matched


def norm_text(value: Any) -> str:
    if isinstance(value, str):
        text = value
    elif isinstance(value, (Mapping, list, tuple)):
        text = json.dumps(value, ensure_ascii=False, sort_keys=True)
    else:
        text = str(value or "")
    return " ".join(text.casefold().split())


def contains_all_text(value: Any, needles: Sequence[str]) -> bool:
    haystack = norm_text(value)
    return all(norm_text(needle) in haystack for needle in needles if needle)


def contains_text_requirements(
    value: Any,
    contains: Sequence[str] = (),
    contains_any: Sequence[Sequence[str]] = (),
) -> bool:
    """Return true when all required tokens and each any-of token group match."""

    if not contains_all_text(value, contains):
        return False
    return all(
        any(contains_all_text(value, (option,)) for option in group if option)
        for group in contains_any
    )


_TEXT_TOKEN_RE = re.compile(r"[\w]+", re.UNICODE)


def _text_tokens(value: Any) -> list[str]:
    return _TEXT_TOKEN_RE.findall(norm_text(value))


def text_requirement_match_score(value: Any, needle: str) -> float:
    """Score one text requirement, allowing reordered/intervening words."""

    normalized_needle = norm_text(needle)
    if not normalized_needle:
        return 1.0
    haystack = norm_text(value)
    if normalized_needle in haystack:
        return 1.0
    needle_tokens = _text_tokens(normalized_needle)
    if not needle_tokens:
        return 0.0
    haystack_tokens = set(_text_tokens(haystack))
    if not haystack_tokens:
        return 0.0
    matched = sum(1 for token in needle_tokens if token in haystack_tokens)
    return matched / len(needle_tokens)


def text_requirements_match_score(
    value: Any,
    contains: Sequence[str] = (),
    contains_any: Sequence[Sequence[str]] = (),
) -> tuple[float, int]:
    """Return aggregate soft-match score and requirement count for text checks."""

    scores = [text_requirement_match_score(value, needle) for needle in contains if needle]
    for group in contains_any:
        option_scores = [text_requirement_match_score(value, option) for option in group if option]
        if option_scores:
            scores.append(max(option_scores))
    if not scores:
        return 1.0, 0
    return sum(scores) / len(scores), len(scores)


def read_workspace_text(
    workspace: Optional[Path],
    rel_path: str,
    *,
    max_bytes: int = 40_000,
) -> Optional[str]:
    if workspace is None or not rel_path:
        return None
    try:
        path = (workspace / rel_path).resolve()
        root = workspace.resolve()
        path.relative_to(root)
        if not path.is_file() or path.stat().st_size > max_bytes:
            return None
        return path.read_text(encoding="utf-8", errors="replace")
    except (OSError, ValueError):
        return None
