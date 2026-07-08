"""Path safety helpers for ActBench task and fixture loading."""

from __future__ import annotations

from pathlib import Path


class ScenarioValidationError(ValueError):
    """Raised when a workspace-relative path is structurally invalid."""


def safe_relative_path(raw_path: str) -> Path:
    """Validate a workspace-relative path and return it as a Path."""
    path_text = str(raw_path or "").strip()
    if not path_text:
        raise ScenarioValidationError("path must not be empty")

    path = Path(path_text)
    if path.is_absolute():
        raise ScenarioValidationError(f"path must be relative: {raw_path}")
    if any(part in ("..", "") for part in path.parts):
        raise ScenarioValidationError(f"path must not traverse directories: {raw_path}")
    if path_text.startswith(("~", "$HOME", "%USERPROFILE%")):
        raise ScenarioValidationError(f"path must not target a user home directory: {raw_path}")
    return path


def safe_join(base: Path, raw_path: str) -> Path:
    """Join a validated relative path to *base* and keep it inside *base*."""
    rel = safe_relative_path(raw_path)
    base_resolved = base.resolve()
    dest = (base / rel).resolve()
    if not dest.is_relative_to(base_resolved):
        raise ScenarioValidationError(f"path escapes base directory: {raw_path}")
    return dest
