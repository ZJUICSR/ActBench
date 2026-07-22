"""Report task-specific Python utility checker coverage without invoking an LLM judge."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

from benchmark.protected_value_scanner import unsupported_protected_value_scan
from benchmark.raw_by_task import RawByTaskError
from benchmark.trajectories import SUPPORTED_TRAJECTORY_SCHEMA_VERSIONS
from benchmark.utility_checkers import resolve_checker, run_task_specific_check
from benchmark.utility_scoring import (
    UtilityScoringError,
    build_utility_check_context,
    collect_raw_by_task_baseline_paths,
    execution_warnings_from_trajectory,
)

UTILITY_CHECKER_REPORT_SCHEMA_VERSION = "actbench.utility_checker_report.v1"


class CheckerReportError(UtilityScoringError):
    """Raised when checker report inputs are invalid."""


def _load_json_file(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_sha256_file(path: Path) -> str:
    try:
        return _sha256_file(path)
    except OSError:
        return ""


def _validate_trajectory(trajectory: Dict[str, Any]) -> str:
    schema_version = trajectory.get("schema_version")
    if schema_version not in SUPPORTED_TRAJECTORY_SCHEMA_VERSIONS:
        supported = ", ".join(sorted(SUPPORTED_TRAJECTORY_SCHEMA_VERSIONS))
        raise CheckerReportError(
            f"Unsupported trajectory schema_version {schema_version!r}; expected one of: {supported}"
        )
    return str(schema_version)


def _execution_caps_from_context(ctx: Any) -> list[dict[str, str]]:
    caps: list[dict[str, str]] = []
    if ctx.execution_timed_out is True:
        caps.append(
            {
                "type": "execution_timeout",
                "message": "Trajectory execution timed out; checker was not run.",
            }
        )
    status = str(ctx.execution_status or "").strip().lower()
    if status and status != "success":
        caps.append(
            {
                "type": "execution_status_not_success",
                "message": f"Trajectory execution status is {status!r}; checker was not run.",
            }
        )
    if ctx.execution_exit_code not in (None, 0):
        caps.append(
            {
                "type": "execution_exit_nonzero",
                "message": f"Trajectory execution exit_code is {ctx.execution_exit_code}; checker was not run.",
            }
        )
    return caps


def _protected_value_scan_from_context(ctx: Any) -> dict[str, Any]:
    """Return disabled protected-value diagnostics for UGS checker reports."""

    return unsupported_protected_value_scan(getattr(ctx, "task_id", None))


def _minimal_error_result(path: Path, exc: Exception, *, trajectory_sha256: str) -> dict[str, Any]:
    return {
        "schema_version": UTILITY_CHECKER_REPORT_SCHEMA_VERSION,
        "trajectory_path": str(path),
        "trajectory_sha256": trajectory_sha256,
        "trajectory_schema_version": None,
        "suite": None,
        "task_id": None,
        "execution_status": None,
        "execution_exit_code": None,
        "execution_timed_out": None,
        "checker_registered": False,
        "checker_name": None,
        "checker_version": None,
        "py_utility": None,
        "py_confidence": "generic_placeholder",
        "task_specific_checks_invoked": False,
        "task_specific_check_status": "not_implemented",
        "python_checks": [],
        "python_notes": "",
        "missing_requirements": [],
        "normal_task_errors": [],
        "caps": [],
        "warnings": [],
        "protected_value_scan": unsupported_protected_value_scan(None),
        "evaluation_error": True,
        "error_type": type(exc).__name__,
        "error_message": str(exc),
    }


def report_trajectory_file(path: Path | str) -> dict[str, Any]:
    """Run only the registered Python utility checker for one trajectory file."""

    trajectory_path = Path(path).expanduser()
    trajectory_sha256 = _safe_sha256_file(trajectory_path)
    try:
        trajectory = _load_json_file(trajectory_path)
        if not isinstance(trajectory, dict):
            raise CheckerReportError("Trajectory JSON root must be an object.")
        trajectory_schema_version = _validate_trajectory(trajectory)
        ctx = build_utility_check_context(trajectory, trajectory_path=trajectory_path)
        checker_registered = resolve_checker(ctx) is not None
        caps = _execution_caps_from_context(ctx)
        warnings = execution_warnings_from_trajectory(trajectory)
        protected_value_scan = _protected_value_scan_from_context(ctx)
        if caps:
            return {
                "schema_version": UTILITY_CHECKER_REPORT_SCHEMA_VERSION,
                "trajectory_path": str(trajectory_path),
                "trajectory_sha256": trajectory_sha256,
                "trajectory_schema_version": trajectory_schema_version,
                "suite": ctx.suite,
                "task_id": ctx.task_id,
                "execution_status": ctx.execution_status,
                "execution_exit_code": ctx.execution_exit_code,
                "execution_timed_out": ctx.execution_timed_out,
                "checker_registered": checker_registered,
                "checker_name": None,
                "checker_version": None,
                "py_utility": None,
                "py_confidence": "generic_placeholder",
                "task_specific_checks_invoked": False,
                "task_specific_check_status": "not_run_execution_cap",
                "python_checks": [],
                "python_notes": "",
                "missing_requirements": [],
                "normal_task_errors": [],
                "caps": caps,
                "warnings": warnings,
                "protected_value_scan": protected_value_scan,
                "evaluation_error": False,
                "error_type": "",
                "error_message": "",
            }
        check_result = run_task_specific_check(ctx)
        return {
            "schema_version": UTILITY_CHECKER_REPORT_SCHEMA_VERSION,
            "trajectory_path": str(trajectory_path),
            "trajectory_sha256": trajectory_sha256,
            "trajectory_schema_version": trajectory_schema_version,
            "suite": ctx.suite,
            "task_id": ctx.task_id,
            "execution_status": ctx.execution_status,
            "execution_exit_code": ctx.execution_exit_code,
            "execution_timed_out": ctx.execution_timed_out,
            "checker_registered": checker_registered,
            "checker_name": check_result.checker_name,
            "checker_version": check_result.checker_version,
            "py_utility": check_result.py_utility,
            "py_confidence": check_result.confidence,
            "task_specific_checks_invoked": check_result.status != "not_implemented",
            "task_specific_check_status": check_result.status,
            "python_checks": [dict(item) for item in check_result.checks],
            "python_notes": check_result.notes,
            "missing_requirements": list(check_result.missing_requirements),
            "normal_task_errors": list(check_result.normal_task_errors),
            "caps": [],
            "warnings": warnings,
            "protected_value_scan": protected_value_scan,
            "evaluation_error": False,
            "error_type": "",
            "error_message": "",
        }
    except Exception as exc:
        return _minimal_error_result(trajectory_path, exc, trajectory_sha256=trajectory_sha256)


def build_checker_report(
    paths: Iterable[Path | str],
    *,
    raw_by_task_source: Optional[Dict[str, Any]] = None,
    raw_by_task_excluded: Optional[Sequence[Dict[str, Any]]] = None,
) -> dict[str, Any]:
    """Build a no-LLM report for registered task-specific utility checkers."""

    results: List[Dict[str, Any]] = []
    seen: set[Path] = set()
    for raw_path in paths:
        path = Path(raw_path).expanduser()
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        results.append(report_trajectory_file(path))

    valid = [row for row in results if not bool(row.get("evaluation_error"))]
    invoked = [row for row in valid if bool(row.get("task_specific_checks_invoked"))]
    scored = [row for row in valid if row.get("py_utility") is not None]
    passed = [row for row in scored if float(row.get("py_utility") or 0.0) >= 1.0]
    protected_scans = [
        row.get("protected_value_scan")
        for row in valid
        if isinstance(row.get("protected_value_scan"), dict)
    ]
    payload: dict[str, Any] = {
        "schema_version": UTILITY_CHECKER_REPORT_SCHEMA_VERSION,
        "generated_at": time.time(),
        "llm_invoked": False,
        "raw_by_task_source": raw_by_task_source or {},
        "trajectory_count": len(results),
        "valid_rows": len(valid),
        "evaluation_errors": len(results) - len(valid),
        "checker_registered_count": sum(1 for row in valid if bool(row.get("checker_registered"))),
        "checker_invoked_count": len(invoked),
        "checker_scored_count": len(scored),
        "checker_pass_count": len(passed),
        "checker_pass_rate": len(passed) / len(scored) if scored else 0.0,
        "placeholder_count": sum(
            1 for row in valid if row.get("task_specific_check_status") == "not_implemented"
        ),
        "execution_capped_count": sum(
            1 for row in valid if row.get("task_specific_check_status") == "not_run_execution_cap"
        ),
        "execution_warning_count": sum(1 for row in valid if row.get("warnings")),
        "protected_value_scan_supported_count": sum(
            1 for scan in protected_scans if bool(scan.get("supported"))
        ),
        "protected_value_leak_count": sum(
            1 for scan in protected_scans if bool(scan.get("leak_detected"))
        ),
        "protected_value_scan_error_count": sum(
            1 for scan in protected_scans if bool(scan.get("error"))
        ),
        "checker_error_count": sum(
            1 for row in valid if row.get("task_specific_check_status") == "error"
        ),
        "results": results,
    }
    if raw_by_task_excluded:
        payload["raw_by_task_excluded"] = list(raw_by_task_excluded)
    return payload


def _parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Report task-specific Python utility checker coverage for raw_by_task baselines"
    )
    parser.add_argument(
        "--raw-by-task-root",
        default=None,
        help="Root containing raw_by_task dataset directories. Defaults to ~/pack/raw_by_task.",
    )
    parser.add_argument(
        "--raw-by-task-dataset",
        action="append",
        default=[],
        help="raw_by_task dataset name or path to inspect. May be repeated.",
    )
    parser.add_argument(
        "--suite",
        action="append",
        default=None,
        help="Limit baseline collection to a suite/behavior such as B1. May be repeated.",
    )
    parser.add_argument(
        "--task-id",
        action="append",
        default=None,
        help="Limit baseline collection to a task id. May be repeated.",
    )
    parser.add_argument(
        "--output",
        "-o",
        default=None,
        help="Optional path to write the checker report JSON. Defaults to stdout only.",
    )
    parser.add_argument(
        "--compact",
        action="store_true",
        help="Emit compact one-line JSON instead of pretty-printed JSON.",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _parse_args(argv)
    try:
        paths, source, excluded = collect_raw_by_task_baseline_paths(
            raw_by_task_root=args.raw_by_task_root,
            raw_by_task_dataset=args.raw_by_task_dataset,
            suites=args.suite,
            task_ids=args.task_id,
        )
    except RawByTaskError as exc:
        raise SystemExit(str(exc)) from exc
    if not paths:
        raise SystemExit(
            "No raw_by_task benign baseline trajectory.json files matched the selection"
        )

    payload = build_checker_report(
        paths,
        raw_by_task_source=source,
        raw_by_task_excluded=excluded,
    )
    indent = None if args.compact else 2
    text = json.dumps(payload, indent=indent, sort_keys=True)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(text + "\n", encoding="utf-8")
    print(text)
    if payload["trajectory_count"] > 0 and payload["valid_rows"] == 0:
        return 1
    return 0


__all__ = [
    "CheckerReportError",
    "UTILITY_CHECKER_REPORT_SCHEMA_VERSION",
    "build_checker_report",
    "main",
    "report_trajectory_file",
]
