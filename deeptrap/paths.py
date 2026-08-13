"""Runtime paths that work from both a source checkout and an installed wheel."""

from __future__ import annotations

from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parent
RUNTIME_ROOT = PACKAGE_ROOT.parent
_BUNDLED_DATA_ROOT = PACKAGE_ROOT / "data"


def data_root() -> Path:
    """Return the root containing benchmark tasks and other bundled data."""
    source_tasks = RUNTIME_ROOT / "tasks"
    if source_tasks.is_dir():
        return RUNTIME_ROOT
    return _BUNDLED_DATA_ROOT


def tasks_dir() -> Path:
    return data_root() / "tasks"


def skills_dir() -> Path:
    return data_root() / "skills"


def scripts_dir() -> Path:
    return RUNTIME_ROOT / "scripts"


def mock_services_dir() -> Path:
    return RUNTIME_ROOT / "mock_services"
