"""Small helper functions for task-specific utility checkers."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Optional


def service_audit(api_audit: Mapping[str, Any], service: str) -> Mapping[str, Any]:
    audit = api_audit.get(service) if isinstance(api_audit, Mapping) else None
    return audit if isinstance(audit, Mapping) else {}


def side_effects(
    api_audit: Mapping[str, Any], service: str, bucket: str
) -> list[Mapping[str, Any]]:
    audit = service_audit(api_audit, service)
    raw = audit.get(bucket)
    if raw is None and isinstance(audit.get("side_effect_buckets"), Mapping):
        raw = audit["side_effect_buckets"].get(bucket)
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, Mapping)]


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
