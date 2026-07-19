"""Transcript length and iteration metrics for benchmark outputs."""

from __future__ import annotations

import json
from typing import Any, Dict

_TEXT_KEYS = ("text", "thinking", "content")


def _json_char_length(value: Any) -> int:
    try:
        return len(
            json.dumps(
                value,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
        )
    except (TypeError, ValueError):
        return len(str(value))


def _text_char_length(value: Any) -> int:
    if isinstance(value, str):
        return len(value)
    if isinstance(value, list):
        return sum(_text_char_length(item) for item in value)
    if isinstance(value, dict):
        total = 0
        for key in _TEXT_KEYS:
            if key in value:
                total += _text_char_length(value.get(key))
        return total
    return 0


def transcript_length_metrics(transcript_entries: Any) -> Dict[str, Any]:
    """Return normalized per-run trajectory length metrics.

    ``iteration_count`` is the number of transcript entries with a top-level
    ``message`` field. ``message_json_chars`` measures the serialized JSON size
    of those message payloads, while ``transcript_json_chars`` measures the full
    normalized transcript entry list. These fields let repeated runs be compared
    without loading the full transcript.
    """

    entries = transcript_entries if isinstance(transcript_entries, list) else []
    message_count = 0
    message_json_chars = 0
    message_text_chars = 0
    role_counts: Dict[str, int] = {}

    for entry in entries:
        if not isinstance(entry, dict) or "message" not in entry:
            continue
        message = entry.get("message")
        message_count += 1
        message_json_chars += _json_char_length(message)
        message_text_chars += _text_char_length(message)
        role = "unknown"
        if isinstance(message, dict):
            raw_role = message.get("role")
            if raw_role:
                role = str(raw_role)
        role_counts[role] = role_counts.get(role, 0) + 1

    return {
        "entry_count": len(entries),
        "iteration_count": message_count,
        "message_count": message_count,
        "message_json_chars": message_json_chars,
        "message_text_chars": message_text_chars,
        "transcript_json_chars": _json_char_length(entries),
        "message_role_counts": dict(sorted(role_counts.items())),
    }
