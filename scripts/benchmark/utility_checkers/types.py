"""Types for task-specific ActBench utility checkers."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Mapping, Optional, Sequence

UtilityConfidence = Literal["high", "medium", "low", "generic_placeholder"]
UtilityCheckStatus = Literal["passed", "partial", "failed", "not_implemented", "error"]


@dataclass(frozen=True)
class UtilityCheckContext:
    """Bounded normal-task evidence passed to Python utility checkers."""

    suite: str = ""
    task_id: str = ""
    trajectory_task_id: Optional[str] = None
    source_task_id: Optional[str] = None
    clean_task_id: Optional[str] = None
    prompt: str = ""
    expected_behavior: str = ""
    grading_criteria: Sequence[str] = ()
    execution_status: Optional[str] = None
    execution_exit_code: Optional[int] = None
    execution_timed_out: Optional[bool] = None
    stdout: str = ""
    stderr: str = ""
    workspace_after: Optional[Path] = None
    api_audit: Mapping[str, Any] = field(default_factory=dict)
    transcript_entries: Sequence[Any] = ()
    trajectory_path: Optional[Path] = None


@dataclass(frozen=True)
class UtilityCheckResult:
    """Structured result from a task-specific Python utility checker."""

    py_utility: Optional[float]
    confidence: UtilityConfidence = "generic_placeholder"
    status: UtilityCheckStatus = "not_implemented"
    checker_name: Optional[str] = None
    checker_version: Optional[str] = None
    checks: Sequence[Mapping[str, Any]] = ()
    missing_requirements: Sequence[str] = ()
    normal_task_errors: Sequence[str] = ()
    notes: str = ""
