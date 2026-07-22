"""Stable fingerprints for ActBench task payloads embedded in trajectories."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any

TASK_HASH_ALGORITHM = "sha256:actbench_task_payload_v1"


def _stable_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _stable_value(value[key]) for key in sorted(value, key=str)}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_stable_value(item) for item in value]
    return value


def _sha256_json(value: Any) -> str:
    payload = json.dumps(
        _stable_value(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def task_prompt_from_payload(payload: Mapping[str, Any]) -> str:
    """Return the prompt text used for task-version comparison."""

    frontmatter = _as_mapping(payload.get("frontmatter"))
    raw = payload.get("prompt") or frontmatter.get("prompt") or frontmatter.get("user_prompt") or ""
    return str(raw).strip()


def clean_source_content_hash_from_payload(payload: Mapping[str, Any]) -> str | None:
    """Return the clean-source content hash when the payload carries one."""

    frontmatter = _as_mapping(payload.get("frontmatter"))
    clean_source = _as_mapping(payload.get("clean_source")) or _as_mapping(
        frontmatter.get("clean_source")
    )
    content_hash = clean_source.get("content_hash")
    if content_hash is None:
        return None
    text = str(content_hash).strip()
    return text or None


def _grading_criteria(payload: Mapping[str, Any]) -> list[str]:
    raw = payload.get("grading_criteria")
    if isinstance(raw, str):
        return [raw]
    if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes, bytearray)):
        return [str(item) for item in raw]
    return []


def _task_spec_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Return the stable task fields that define clean-task checker compatibility."""

    return {
        "prompt": task_prompt_from_payload(payload),
        "expected_behavior": str(payload.get("expected_behavior") or "").strip(),
        "grading_criteria": _grading_criteria(payload),
        "clean_source_content_hash": clean_source_content_hash_from_payload(payload),
    }


def task_prompt_sha256_from_payload(payload: Mapping[str, Any]) -> str:
    """Hash only the task prompt text."""

    return _sha256_json({"prompt": task_prompt_from_payload(payload)})


def task_spec_sha256_from_payload(payload: Mapping[str, Any]) -> str:
    """Hash the stable clean-task spec fields used by trajectory compatibility checks."""

    return _sha256_json(_task_spec_payload(payload))


def fingerprint_task_payload(payload: Mapping[str, Any]) -> dict[str, str]:
    """Return additive fingerprint fields for a serialized task payload."""

    return {
        "task_hash_algorithm": TASK_HASH_ALGORITHM,
        "task_prompt_sha256": task_prompt_sha256_from_payload(payload),
        "task_spec_sha256": task_spec_sha256_from_payload(payload),
    }
