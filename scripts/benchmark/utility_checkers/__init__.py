"""Task-specific Python utility checker support."""

from __future__ import annotations

from .registry import (
    UtilityChecker,
    register,
    register_checker,
    registered_checker_ids,
    resolve_checker,
    run_task_specific_check,
    unregister_checker,
)
from .types import UtilityCheckContext, UtilityCheckResult

# Import registered specs for side effects after registry exports are available.
from . import specs as _specs  # noqa: F401,E402

__all__ = [
    "UtilityCheckContext",
    "UtilityCheckResult",
    "UtilityChecker",
    "register",
    "register_checker",
    "registered_checker_ids",
    "resolve_checker",
    "run_task_specific_check",
    "unregister_checker",
]
