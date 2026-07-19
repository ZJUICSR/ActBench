"""Registry and execution wrapper for task-specific utility checkers."""

from __future__ import annotations

import logging
import math
import re
from collections.abc import Mapping as MappingABC
from typing import Any, Callable, Optional

from .types import UtilityCheckContext, UtilityCheckResult

logger = logging.getLogger(__name__)

UtilityChecker = Callable[[UtilityCheckContext], UtilityCheckResult | dict[str, Any]]

_CHECKERS: dict[str, UtilityChecker] = {}
_CONFIDENCE_VALUES = {"high", "medium", "low", "generic_placeholder"}
_STATUS_VALUES = {"passed", "partial", "failed", "not_implemented", "error"}


def _coerce_unit_float(value: Any, *, default: Optional[float] = None) -> Optional[float]:
    try:
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return default
            fraction = re.fullmatch(r"([+-]?\d+(?:\.\d+)?)\s*/\s*([+-]?\d+(?:\.\d+)?)", text)
            if fraction:
                denominator = float(fraction.group(2))
                if denominator == 0:
                    return default
                numeric = float(fraction.group(1)) / denominator
            elif text.endswith("%"):
                numeric = float(text[:-1].strip()) / 100.0
            else:
                numeric = float(text)
        else:
            numeric = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(numeric):
        return default
    if numeric > 10.0 and numeric <= 100.0:
        numeric = numeric / 100.0
    elif numeric > 1.0:
        numeric = numeric / 10.0
    return max(0.0, min(1.0, numeric))


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    return [str(item) for item in value if item is not None]


def _checks_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, (list, tuple)):
        return []
    checks: list[dict[str, Any]] = []
    for item in value:
        if isinstance(item, MappingABC):
            checks.append({str(key): val for key, val in item.items()})
        elif item is not None:
            checks.append({"value": str(item)})
    return checks


def _normalize_confidence(value: Any) -> str:
    text = str(value or "").strip()
    return text if text in _CONFIDENCE_VALUES else "low"


def _normalize_status(value: Any) -> str:
    text = str(value or "").strip()
    return text if text in _STATUS_VALUES else "error"


def _normalize_check_result(
    result: UtilityCheckResult | dict[str, Any],
    *,
    default_checker_name: Optional[str] = None,
) -> UtilityCheckResult:
    if isinstance(result, UtilityCheckResult):
        raw = {
            "py_utility": result.py_utility,
            "confidence": result.confidence,
            "status": result.status,
            "checker_name": result.checker_name,
            "checker_version": result.checker_version,
            "checks": result.checks,
            "missing_requirements": result.missing_requirements,
            "normal_task_errors": result.normal_task_errors,
            "notes": result.notes,
        }
    elif isinstance(result, dict):
        raw = dict(result)
    else:
        raw = {
            "py_utility": None,
            "confidence": "low",
            "status": "error",
            "notes": f"checker returned unsupported result type: {type(result).__name__}",
        }

    py_utility = raw.get("py_utility")
    if py_utility is None and "utility" in raw:
        py_utility = raw.get("utility")
    if py_utility is None and "score" in raw:
        py_utility = raw.get("score")
    return UtilityCheckResult(
        py_utility=_coerce_unit_float(py_utility, default=None),
        confidence=_normalize_confidence(raw.get("confidence")),
        status=_normalize_status(raw.get("status")),
        checker_name=str(raw.get("checker_name") or default_checker_name or "") or None,
        checker_version=str(raw.get("checker_version") or "") or None,
        checks=_checks_list(raw.get("checks")),
        missing_requirements=_string_list(raw.get("missing_requirements")),
        normal_task_errors=_string_list(raw.get("normal_task_errors")),
        notes=str(raw.get("notes") or "")[:2000],
    )


def register_checker(task_id: str, checker: UtilityChecker) -> Optional[UtilityChecker]:
    """Register a checker for an exact task id; return any previous checker."""

    if not task_id:
        raise ValueError("task_id must be non-empty")
    previous = _CHECKERS.get(task_id)
    _CHECKERS[task_id] = checker
    return previous


def register(*task_ids: str) -> Callable[[UtilityChecker], UtilityChecker]:
    """Decorator form of register_checker()."""

    def decorator(checker: UtilityChecker) -> UtilityChecker:
        for task_id in task_ids:
            register_checker(task_id, checker)
        return checker

    return decorator


def unregister_checker(task_id: str) -> None:
    """Remove a registered task checker if present."""

    _CHECKERS.pop(task_id, None)


def registered_checker_ids() -> list[str]:
    """Return registered task ids for diagnostics/tests."""

    return sorted(_CHECKERS)


def _candidate_task_ids(ctx: UtilityCheckContext) -> list[str]:
    candidates: list[str] = []
    for raw in (ctx.task_id, ctx.source_task_id, ctx.clean_task_id, ctx.trajectory_task_id):
        if not raw:
            continue
        text = str(raw)
        if text not in candidates:
            candidates.append(text)
        if text.endswith("_baseline"):
            normalized = text[: -len("_baseline")]
            if normalized and normalized not in candidates:
                candidates.append(normalized)
    return candidates


def resolve_checker(ctx: UtilityCheckContext) -> Optional[UtilityChecker]:
    """Resolve a checker by canonical, source, clean, or trajectory task id."""

    for task_id in _candidate_task_ids(ctx):
        checker = _CHECKERS.get(task_id)
        if checker is not None:
            return checker
    return None


def run_task_specific_check(ctx: UtilityCheckContext) -> UtilityCheckResult:
    """Run the registered checker, or return the placeholder result."""

    checker = resolve_checker(ctx)
    if checker is None:
        return UtilityCheckResult(
            py_utility=None,
            confidence="generic_placeholder",
            status="not_implemented",
        )

    checker_name = getattr(checker, "__name__", checker.__class__.__name__)
    try:
        return _normalize_check_result(checker(ctx), default_checker_name=checker_name)
    except Exception as exc:  # pragma: no cover - concrete exceptions vary by checker
        logger.warning("Utility checker %s failed for %s: %s", checker_name, ctx.task_id, exc)
        return UtilityCheckResult(
            py_utility=None,
            confidence="low",
            status="error",
            checker_name=checker_name,
            notes=f"checker failed: {type(exc).__name__}: {exc}",
        )
