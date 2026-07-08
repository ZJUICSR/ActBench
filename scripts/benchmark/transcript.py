"""Transcript helpers for benchmark runs."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List


def _summarize_transcript(transcript: List[Dict[str, Any]], max_len: int = 1500) -> str:
    parts: List[str] = []
    for entry in transcript:
        if entry.get("type") != "message":
            continue
        msg = entry.get("message", {})
        role, content = msg.get("role", ""), msg.get("content", "")
        if role == "assistant":
            if isinstance(content, list):
                for item in content:
                    if isinstance(item, dict):
                        if item.get("type") == "toolCall":
                            parts.append(f"[Tool] {item.get('name', '?')}")
                        elif item.get("type") == "text":
                            parts.append(f"[Agent] {item.get('text', '')[:200]}")
            else:
                parts.append(f"[Agent] {str(content)[:200]}")
        elif role == "user":
            text = str(content[0])[:150] if isinstance(content, list) else str(content)[:150]
            parts.append(f"[User] {text}")
    return "\n".join(parts)[:max_len]


def _normalize_tool_path(path: str) -> str:
    raw = str(path).strip()
    if not raw:
        return ""
    candidate = Path(raw)
    if candidate.is_absolute():
        parts = candidate.parts
        if "workspace" in parts:
            idx = len(parts) - 1 - list(reversed(parts)).index("workspace")
            rel_parts = parts[idx + 1 :]
            if rel_parts:
                raw = "/".join(rel_parts)
            else:
                raw = candidate.name
        else:
            raw = candidate.name
    normalized = Path(raw).as_posix().lstrip("/")
    safe_parts = []
    for part in normalized.split("/"):
        if not part or part == ".":
            continue
        if part == "..":
            return Path(normalized).name
        safe_parts.append(part)
    return "/".join(safe_parts) or Path(normalized).name


def _extract_transcript_file_ops(transcript: List[Dict[str, Any]]) -> Dict[str, List[str]]:
    files_read: List[str] = []
    files_written: List[str] = []
    seen_read: set = set()
    seen_written: set = set()
    for entry in transcript or []:
        if entry.get("type") != "message":
            continue
        msg = entry.get("message", {}) or {}
        for item in msg.get("content") or []:
            if not isinstance(item, dict):
                continue
            if item.get("type") not in ("toolCall", "tool_use"):
                continue
            name = (item.get("name") or "").lower()
            args = item.get("arguments") or item.get("input") or {}
            if not isinstance(args, dict):
                continue
            path = args.get("file_path") or args.get("path") or args.get("notebook_path")
            if not path or not isinstance(path, str):
                continue
            path = _normalize_tool_path(path)
            if not path:
                continue
            if "read" in name:
                if path not in seen_read:
                    files_read.append(path)
                    seen_read.add(path)
            elif "write" in name or "edit" in name:
                if path not in seen_written:
                    files_written.append(path)
                    seen_written.add(path)
    return {"files_read": files_read, "files_written": files_written}
