"""One-command ActBench collection and scoring orchestration."""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

from deeptrap.paths import tasks_dir as bundled_tasks_dir
from lib_tasks import TaskLoader
from lib_training_artifacts import atomic_write_json

from benchmark.backends.registry import available_backend_names, get_backend
from benchmark.offline_scoring import (
    AUTOMATED_ONLY_MODE,
    COMBINED_AGS_MODE,
    OFFLINE_SCORE_SCHEMA_VERSION,
)
from benchmark.task_loading import select_task_files_for_suite

ONE_CLICK_SCHEMA_VERSION = "actbench.one_click.v1"
DEFAULT_SUITE = "representative"
DEFAULT_OUTPUT_ROOT = Path("results/one_click")
SELF_TEST_MODEL = "fake/self-test"
SELF_TEST_SUITE = "task_B9_T01"
REPRESENTATIVE_SUITE_NAME = "representative"
REPRESENTATIVE_TASK_IDS = tuple(f"task_B{i}_T01" for i in range(1, 16))
REPRESENTATIVE_SUITE_SELECTOR = ",".join(REPRESENTATIVE_TASK_IDS)

EXIT_PREFLIGHT = 2
EXIT_COLLECTION = 3
EXIT_SCORING = 4
EXIT_PARTIAL_SCORING = 5
EXIT_INTERRUPTED = 130


@dataclass(frozen=True)
class OneClickConfig:
    backend: str
    model: str
    suite: str
    score_mode: str
    judge_model: Optional[str]
    tasks_dir: Path
    output_root: Path
    runs: int = 1
    run_workers: int = 1
    timeout_multiplier: float = 1.0
    execution_retries: int = 0
    retry_status: str = "error,timeout"
    skip_baseline_gen: bool = False
    verbose: bool = False
    self_test: bool = False


@dataclass(frozen=True)
class OneClickRunPlan:
    config: OneClickConfig
    collection_suite: str
    selected_task_ids: tuple[str, ...]
    expected_attempts: int
    backend_supports_parallel_runs: bool


class OneClickError(RuntimeError):
    """Base class for one-click orchestration errors."""

    exit_code = 1
    error_type = "one_click_error"


class OneClickPreflightError(OneClickError):
    exit_code = EXIT_PREFLIGHT
    error_type = "preflight_error"


class OneClickCollectionError(OneClickError):
    exit_code = EXIT_COLLECTION
    error_type = "collection_error"


class OneClickScoringError(OneClickError):
    exit_code = EXIT_SCORING
    error_type = "scoring_error"


class OneClickPartialScoringError(OneClickScoringError):
    exit_code = EXIT_PARTIAL_SCORING
    error_type = "partial_scoring_error"


class OneClickInterrupted(OneClickError):
    exit_code = EXIT_INTERRUPTED
    error_type = "interrupted"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _scripts_dir() -> Path:
    return _repo_root() / "scripts"


def _default_tasks_dir() -> Path:
    return bundled_tasks_dir()


def _positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"expected a positive integer, got {value!r}") from exc
    if parsed < 1:
        raise argparse.ArgumentTypeError("expected a positive integer")
    return parsed


def _nonnegative_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"expected a non-negative integer, got {value!r}") from exc
    if parsed < 0:
        raise argparse.ArgumentTypeError("expected a non-negative integer")
    return parsed


def _positive_float(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"expected a positive number, got {value!r}") from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError("expected a positive number")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run a bounded ActBench test: collect trajectories with the selected backend "
            "and score only this invocation's trajectories."
        )
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help=(
            "Run a no-model plumbing check with the fake backend, one task, and automated "
            "scoring. This is not a target-model evaluation."
        ),
    )
    parser.add_argument(
        "--backend",
        choices=available_backend_names(),
        default=None,
        help="Target-agent backend. Required unless --self-test is used.",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Backend-specific model id/label. Required unless --self-test is used.",
    )
    parser.add_argument(
        "--judge-model",
        default=None,
        help="Required for the default --score-mode combined-ags; invalid with automated scoring.",
    )
    parser.add_argument(
        "--suite",
        default=None,
        help=(
            "Task selector. Defaults to 'representative' (task_B1_T01,...,task_B15_T01). "
            "Any existing ActBench selector is accepted, including exact ids, B classes, and 'all'."
        ),
    )
    parser.add_argument("--runs", type=_positive_int, default=None, help="Runs per task (default: 1).")
    parser.add_argument(
        "--run-workers",
        type=_positive_int,
        default=None,
        help="Same-task repeat workers when supported by the backend (default: 1).",
    )
    parser.add_argument(
        "--timeout-multiplier",
        type=_positive_float,
        default=None,
        help="Scale task timeouts (default: 1.0).",
    )
    parser.add_argument(
        "--execution-retries",
        type=_nonnegative_int,
        default=None,
        help="Retry each repeat up to N times for retryable execution statuses (default: 0).",
    )
    parser.add_argument(
        "--retry-status",
        default=None,
        help="Comma-separated retryable execution statuses (default: error,timeout).",
    )
    parser.add_argument(
        "--tasks-dir",
        default=None,
        help="Task directory to load (default: repository tasks/).",
    )
    parser.add_argument(
        "--output-root",
        default=str(DEFAULT_OUTPUT_ROOT),
        help="Root for unique one-click invocation directories (default: results/one_click).",
    )
    parser.add_argument(
        "--skip-baseline-gen",
        action="store_true",
        help="Skip pre-generating clean baselines; faster but may reduce Combined AGS evidence quality.",
    )
    parser.add_argument(
        "--score-mode",
        choices=[COMBINED_AGS_MODE, AUTOMATED_ONLY_MODE],
        default=None,
        help=(
            "Scoring mode. Defaults to combined-ags for real runs; --self-test forces automated. "
            "Automated scoring makes no external judge calls."
        ),
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose runner/scorer logging.",
    )
    return parser


def parse_args(argv: Optional[Sequence[str]] = None) -> OneClickConfig:
    parser = build_parser()
    args = parser.parse_args(argv)

    tasks_dir = Path(args.tasks_dir).expanduser().resolve() if args.tasks_dir else _default_tasks_dir()
    output_root = Path(args.output_root).expanduser().resolve()

    if args.self_test:
        if args.backend is not None:
            parser.error("--self-test cannot be combined with --backend")
        if args.model is not None:
            parser.error("--self-test cannot be combined with --model")
        if args.judge_model is not None:
            parser.error("--self-test cannot be combined with --judge-model")
        if args.suite is not None:
            parser.error("--self-test cannot be combined with --suite")
        if args.runs is not None and args.runs != 1:
            parser.error("--self-test always uses --runs 1")
        if args.run_workers is not None and args.run_workers != 1:
            parser.error("--self-test always uses --run-workers 1")
        if args.score_mode is not None and args.score_mode != AUTOMATED_ONLY_MODE:
            parser.error("--self-test uses automated scoring; do not pass combined-ags")
        if args.execution_retries is not None and args.execution_retries != 0:
            parser.error("--self-test always uses --execution-retries 0")
        return OneClickConfig(
            backend="fake",
            model=SELF_TEST_MODEL,
            suite=SELF_TEST_SUITE,
            score_mode=AUTOMATED_ONLY_MODE,
            judge_model=None,
            tasks_dir=tasks_dir,
            output_root=output_root,
            runs=1,
            run_workers=1,
            timeout_multiplier=args.timeout_multiplier or 1.0,
            execution_retries=0,
            retry_status=args.retry_status or "error,timeout",
            skip_baseline_gen=True,
            verbose=bool(args.verbose),
            self_test=True,
        )

    if args.backend is None:
        parser.error("--backend is required unless --self-test is used")
    if not args.model:
        parser.error("--model is required unless --self-test is used")

    score_mode = args.score_mode or COMBINED_AGS_MODE
    if score_mode == COMBINED_AGS_MODE and not args.judge_model:
        parser.error("--judge-model is required with the default --score-mode combined-ags")
    if score_mode == AUTOMATED_ONLY_MODE and args.judge_model:
        parser.error("--judge-model is only valid with --score-mode combined-ags")

    retry_status = args.retry_status or "error,timeout"
    if (args.execution_retries or 0) > 0 and not any(part.strip() for part in retry_status.split(",")):
        parser.error("--retry-status must include at least one status when --execution-retries > 0")

    return OneClickConfig(
        backend=str(args.backend).strip().lower(),
        model=str(args.model).strip(),
        suite=args.suite or DEFAULT_SUITE,
        score_mode=score_mode,
        judge_model=args.judge_model,
        tasks_dir=tasks_dir,
        output_root=output_root,
        runs=args.runs or 1,
        run_workers=args.run_workers or 1,
        timeout_multiplier=args.timeout_multiplier or 1.0,
        execution_retries=args.execution_retries or 0,
        retry_status=retry_status,
        skip_baseline_gen=bool(args.skip_baseline_gen),
        verbose=bool(args.verbose),
        self_test=False,
    )


def resolve_suite_selector(suite: str) -> str:
    return REPRESENTATIVE_SUITE_SELECTOR if suite == REPRESENTATIVE_SUITE_NAME else suite


def resolve_run_plan(config: OneClickConfig) -> OneClickRunPlan:
    if config.backend not in available_backend_names():
        known = ", ".join(available_backend_names())
        raise OneClickPreflightError(f"unknown backend {config.backend!r}; expected one of: {known}")
    if not config.model.strip():
        raise OneClickPreflightError("model must be non-empty")
    if not config.tasks_dir.exists():
        raise OneClickPreflightError(f"tasks directory does not exist: {config.tasks_dir}")
    if not config.tasks_dir.is_dir():
        raise OneClickPreflightError(f"tasks path is not a directory: {config.tasks_dir}")

    collection_suite = resolve_suite_selector(config.suite)
    try:
        task_files = select_task_files_for_suite(config.tasks_dir, collection_suite)
    except Exception as exc:  # noqa: BLE001 - surface selector failures as preflight errors
        raise OneClickPreflightError(str(exc)) from exc
    if not task_files:
        raise OneClickPreflightError(f"suite {config.suite!r} selected no tasks")

    tasks = TaskLoader(config.tasks_dir).load_task_files(list(task_files))
    if len(tasks) != len(task_files):
        raise OneClickPreflightError(
            f"selected {len(task_files)} task file(s) but only loaded {len(tasks)} task(s)"
        )
    if config.suite == REPRESENTATIVE_SUITE_NAME:
        representative_order = {task_id: index for index, task_id in enumerate(REPRESENTATIVE_TASK_IDS)}
        tasks = sorted(tasks, key=lambda task: representative_order.get(task.task_id, len(tasks)))
    task_ids = tuple(task.task_id for task in tasks)

    backend = get_backend(config.backend)
    if config.run_workers > 1 and not bool(getattr(backend, "supports_parallel_runs", False)):
        raise OneClickPreflightError(
            f"backend {config.backend!r} does not support --run-workers > 1"
        )

    expected_attempts = len(task_ids) * config.runs
    return OneClickRunPlan(
        config=config,
        collection_suite=collection_suite,
        selected_task_ids=task_ids,
        expected_attempts=expected_attempts,
        backend_supports_parallel_runs=bool(getattr(backend, "supports_parallel_runs", False)),
    )


def create_invocation_directory(output_root: Path) -> Path:
    output_root.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    for _ in range(100):
        invocation_id = f"{timestamp}-{uuid.uuid4().hex[:8]}"
        invocation_dir = output_root / invocation_id
        try:
            invocation_dir.mkdir(parents=False, exist_ok=False)
        except FileExistsError:
            continue
        return invocation_dir.resolve()
    raise OneClickPreflightError(f"could not create a unique invocation directory under {output_root}")


def build_collection_command(plan: OneClickRunPlan, collection_dir: Path) -> List[str]:
    config = plan.config
    command = [
        sys.executable,
        str(_scripts_dir() / "actbench.py"),
        "--backend",
        config.backend,
        "--model",
        config.model,
        "--suite",
        plan.collection_suite,
        "--output-dir",
        str(collection_dir),
        "--timeout-multiplier",
        str(config.timeout_multiplier),
        "--runs",
        str(config.runs),
        "--run-workers",
        str(config.run_workers),
        "--execution-retries",
        str(config.execution_retries),
        "--retry-status",
        config.retry_status,
    ]
    if config.tasks_dir != _default_tasks_dir():
        command.extend(["--tasks-dir", str(config.tasks_dir)])
    if config.judge_model and config.score_mode == COMBINED_AGS_MODE:
        command.extend(["--judge-model", config.judge_model])
    if config.skip_baseline_gen:
        command.append("--skip-baseline-gen")
    if config.verbose:
        command.append("--verbose")
    return command


def build_scoring_command(plan: OneClickRunPlan, invocation_dir: Path) -> List[str]:
    config = plan.config
    command = [
        sys.executable,
        str(_scripts_dir() / "actbench_score.py"),
        "--trajectory",
        str(invocation_dir / "collection" / "trajectories"),
        "--mode",
        config.score_mode,
        "--output",
        str(invocation_dir / "score.json"),
    ]
    if config.judge_model and config.score_mode == COMBINED_AGS_MODE:
        command.extend(["--judge-model", config.judge_model])
    if config.verbose:
        command.append("--verbose")
    return command


def _terminate_process_group(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    try:
        if os.name == "nt":
            process.terminate()
        else:
            os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=5)
        return
    except subprocess.TimeoutExpired:
        pass
    try:
        if os.name == "nt":
            process.kill()
        else:
            os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        return
    process.wait(timeout=5)


def run_child(
    command: Sequence[str],
    *,
    cwd: Path,
    log_path: Path,
    stream_output: bool,
) -> int:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) if os.name == "nt" else 0
    process = subprocess.Popen(
        list(command),
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        start_new_session=(os.name != "nt"),
        creationflags=creationflags,
    )
    try:
        with log_path.open("w", encoding="utf-8") as log_file:
            assert process.stdout is not None
            for line in process.stdout:
                log_file.write(line)
                log_file.flush()
                if stream_output:
                    print(line, end="")
        return process.wait()
    except KeyboardInterrupt:
        _terminate_process_group(process)
        raise


def _load_json(path: Path, *, error_cls: type[OneClickError] = OneClickScoringError) -> Dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise error_cls(f"failed to parse JSON at {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise error_cls(f"JSON payload at {path} is not an object")
    return payload


def find_collection_result(collection_dir: Path) -> Path:
    candidates: List[Path] = []
    for path in sorted(collection_dir.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 - ignore non-aggregate JSON files
            continue
        if (
            isinstance(payload, dict)
            and payload.get("workflow") == "trajectory_collection"
            and not payload.get("summary_kind")
        ):
            if isinstance(payload.get("tasks"), list):
                candidates.append(path)
    if not candidates:
        raise OneClickCollectionError(f"no trajectory_collection aggregate found in {collection_dir}")
    if len(candidates) > 1:
        names = ", ".join(path.name for path in candidates)
        raise OneClickCollectionError(f"multiple collection aggregates found in {collection_dir}: {names}")
    return candidates[0]


def _path_from_collection_link(collection_dir: Path, value: Any) -> Optional[Path]:
    if not isinstance(value, str) or not value:
        return None
    path = Path(value)
    if path.is_absolute():
        return path
    return collection_dir / path


def _as_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _task_run_number(entry: Mapping[str, Any], *, runs: int) -> Optional[int]:
    backend_meta = entry.get("backend_metadata")
    if isinstance(backend_meta, Mapping):
        for key in ("run_number", "run_index"):
            value = _as_int(backend_meta.get(key))
            if value is not None:
                return value
    value = _as_int(entry.get("run_number") or entry.get("run_index"))
    if value is not None:
        return value
    if runs == 1:
        return 1
    return None


def validate_collection_result(result_path: Path, plan: OneClickRunPlan) -> Dict[str, Any]:
    collection_dir = result_path.parent
    payload = _load_json(result_path, error_cls=OneClickCollectionError)
    errors: List[str] = []

    if payload.get("workflow") != "trajectory_collection":
        errors.append("collection aggregate workflow is not trajectory_collection")
    if payload.get("backend") != plan.config.backend:
        errors.append(
            f"collection backend {payload.get('backend')!r} does not match {plan.config.backend!r}"
        )
    if payload.get("model") != plan.config.model:
        errors.append(f"collection model {payload.get('model')!r} does not match {plan.config.model!r}")
    if payload.get("suite") != plan.collection_suite:
        errors.append(
            f"collection suite {payload.get('suite')!r} does not match {plan.collection_suite!r}"
        )

    rows = payload.get("tasks")
    if not isinstance(rows, list):
        raise OneClickCollectionError("collection aggregate has no tasks list")
    if len(rows) != plan.expected_attempts:
        errors.append(f"expected {plan.expected_attempts} task attempts, found {len(rows)}")

    expected_slots = {
        (task_id, run_number)
        for task_id in plan.selected_task_ids
        for run_number in range(1, plan.config.runs + 1)
    }
    seen_slots: set[tuple[str, int]] = set()
    canonical_paths: List[Path] = []
    baseline_task_ids: set[str] = set()

    for index, row in enumerate(rows, 1):
        if not isinstance(row, dict):
            errors.append(f"task row {index} is not an object")
            continue
        task_id = row.get("task_id")
        if task_id not in plan.selected_task_ids:
            errors.append(f"unexpected task id in row {index}: {task_id!r}")
        run_number = _task_run_number(row, runs=plan.config.runs)
        if not isinstance(task_id, str) or run_number is None:
            errors.append(f"could not resolve task/run slot for row {index}")
        else:
            seen_slots.add((task_id, run_number))
        if row.get("status") != "success":
            errors.append(
                f"{task_id or f'row {index}'} run {run_number or '?'} has status {row.get('status')!r}"
            )
        trajectory = row.get("trajectory") if isinstance(row.get("trajectory"), dict) else {}
        canonical_path = _path_from_collection_link(collection_dir, trajectory.get("canonical_path"))
        if canonical_path is None:
            errors.append(f"{task_id or f'row {index}'} run {run_number or '?'} has no canonical trajectory")
        elif not canonical_path.exists():
            errors.append(f"canonical trajectory does not exist: {canonical_path}")
        else:
            canonical_paths.append(canonical_path.resolve())
        if row.get("baseline"):
            baseline_task_ids.add(str(task_id))

    missing_slots = sorted(expected_slots - seen_slots)
    extra_slots = sorted(seen_slots - expected_slots)
    if missing_slots:
        errors.append(f"missing expected task/run slots: {missing_slots[:5]}")
    if extra_slots:
        errors.append(f"unexpected task/run slots: {extra_slots[:5]}")

    trajectory_root = collection_dir / "trajectories"
    found_trajectories = sorted(path.resolve() for path in trajectory_root.rglob("trajectory.json"))
    if len(found_trajectories) != plan.expected_attempts:
        errors.append(
            f"expected {plan.expected_attempts} canonical trajectory files, "
            f"found {len(found_trajectories)} under {trajectory_root}"
        )
    if len(set(canonical_paths)) != len(canonical_paths):
        errors.append("duplicate canonical trajectory paths found in collection rows")

    if errors:
        raise OneClickCollectionError("; ".join(errors))

    missing_baseline_task_ids = (
        [] if plan.config.skip_baseline_gen else sorted(set(plan.selected_task_ids) - baseline_task_ids)
    )
    return {
        "payload": payload,
        "summary": {
            "result_path": str(result_path),
            "trajectory_root": str(trajectory_root),
            "successful_attempts": len(rows),
            "failed_attempts": 0,
            "canonical_trajectories": len(found_trajectories),
            "baseline_tasks_present": len(baseline_task_ids),
            "baseline_tasks_missing": len(missing_baseline_task_ids),
            "missing_baseline_task_ids": missing_baseline_task_ids,
        },
    }


def _expected_score_mode(mode: str) -> str:
    return "combined_ags" if mode == COMBINED_AGS_MODE else "automated_only"


def validate_score_result(score_path: Path, plan: OneClickRunPlan) -> Dict[str, Any]:
    try:
        payload = json.loads(score_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise OneClickScoringError(f"failed to parse score JSON at {score_path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise OneClickScoringError(f"score JSON at {score_path} is not an object")

    errors: List[str] = []
    if payload.get("schema_version") != OFFLINE_SCORE_SCHEMA_VERSION:
        errors.append(
            f"score schema {payload.get('schema_version')!r} does not match "
            f"{OFFLINE_SCORE_SCHEMA_VERSION!r}"
        )
    if payload.get("scoring_mode") != _expected_score_mode(plan.config.score_mode):
        errors.append(
            f"score mode {payload.get('scoring_mode')!r} does not match {plan.config.score_mode!r}"
        )
    trajectory_count = _as_int(payload.get("trajectory_count"))
    valid_scores = _as_int(payload.get("valid_scores"))
    evaluation_errors = _as_int(payload.get("evaluation_errors"))
    if trajectory_count != plan.expected_attempts:
        errors.append(f"expected {plan.expected_attempts} scored trajectories, found {trajectory_count}")
    if evaluation_errors is None:
        errors.append("score payload is missing evaluation_errors")
    elif evaluation_errors != 0:
        errors.append(f"score payload has {evaluation_errors} evaluation error(s)")
    if valid_scores != plan.expected_attempts:
        errors.append(f"expected {plan.expected_attempts} valid scores, found {valid_scores}")
    results = payload.get("results")
    if not isinstance(results, list) or len(results) != plan.expected_attempts:
        errors.append("score payload results do not match expected attempt count")

    if errors:
        if evaluation_errors and evaluation_errors > 0:
            raise OneClickPartialScoringError("; ".join(errors))
        raise OneClickScoringError("; ".join(errors))

    return {
        "payload": payload,
        "summary": {
            "result_path": str(score_path),
            "trajectory_count": trajectory_count,
            "valid_scores": valid_scores,
            "evaluation_errors": evaluation_errors,
            "mean_ags": payload.get("mean_ags"),
            "asr": payload.get("asr"),
            "pass@k": payload.get("pass@k"),
            "pass@k1": payload.get("pass@k1"),
            "pass@k2": payload.get("pass@k2"),
            "pass@k3": payload.get("pass@k3"),
            "attack_reproduced": bool(payload.get("attack_reproduced")),
            "llm_invoked": bool(payload.get("llm_invoked")),
        },
    }


def _relpath(path: Path, base: Path) -> str:
    try:
        return path.resolve().relative_to(base.resolve()).as_posix()
    except ValueError:
        return str(path)


def _request_manifest(config: OneClickConfig) -> Dict[str, Any]:
    return {
        "self_test": config.self_test,
        "backend": config.backend,
        "model": config.model,
        "suite": config.suite,
        "runs": config.runs,
        "run_workers": config.run_workers,
        "timeout_multiplier": config.timeout_multiplier,
        "execution_retries": config.execution_retries,
        "retry_status": config.retry_status,
        "score_mode": config.score_mode,
        "judge_model": config.judge_model,
        "skip_baseline_gen": config.skip_baseline_gen,
        "tasks_dir": str(config.tasks_dir),
    }


def initial_manifest(
    *,
    plan: OneClickRunPlan,
    invocation_dir: Path,
    started_at: str,
) -> Dict[str, Any]:
    return {
        "schema_version": ONE_CLICK_SCHEMA_VERSION,
        "invocation_id": invocation_dir.name,
        "status": "running",
        "stage": "preflight_complete",
        "started_at": started_at,
        "finished_at": None,
        "request": _request_manifest(plan.config),
        "resolved": {
            "suite": plan.config.suite,
            "collection_suite": plan.collection_suite,
            "task_count": len(plan.selected_task_ids),
            "task_ids": list(plan.selected_task_ids),
            "runs": plan.config.runs,
            "expected_attempts": plan.expected_attempts,
            "backend_supports_parallel_runs": plan.backend_supports_parallel_runs,
        },
        "paths": {
            "invocation_dir": str(invocation_dir),
            "collection_dir": "collection",
            "score_path": "score.json",
            "result_path": "one_click_result.json",
            "collection_log": "collection.log",
            "scoring_log": "scoring.log",
        },
        "commands": {},
        "collection": None,
        "scoring": None,
        "warnings": [],
        "error": None,
    }


def write_invocation_manifest(invocation_dir: Path, payload: Mapping[str, Any]) -> Path:
    return atomic_write_json(invocation_dir / "one_click_result.json", dict(payload))


def _finish_manifest(manifest: Dict[str, Any], *, status: str, stage: str) -> None:
    manifest["status"] = status
    manifest["stage"] = stage
    manifest["finished_at"] = datetime.now(timezone.utc).isoformat()


def _record_error(manifest: Dict[str, Any], exc: OneClickError) -> None:
    manifest["error"] = {"type": exc.error_type, "message": str(exc)}


def _print_plan(plan: OneClickRunPlan, invocation_dir: Path) -> None:
    config = plan.config
    print("DeepTrap one-command test")
    if config.self_test:
        print("  mode:    self-test (fake backend; no target model or external judge)")
    print(f"  backend: {config.backend}")
    print(f"  model:   {config.model}")
    print(f"  suite:   {config.suite} -> {len(plan.selected_task_ids)} task(s)")
    print("  tasks:   " + ", ".join(plan.selected_task_ids))
    print(f"  runs:    {config.runs} per task ({plan.expected_attempts} target attempt(s))")
    if config.skip_baseline_gen:
        print("  baselines: skipped")
    else:
        print("  baselines: generate/reuse clean baselines before attacked attempts")
    if config.score_mode == COMBINED_AGS_MODE:
        print(f"  scoring: combined AGS via judge {config.judge_model}")
    else:
        print("  scoring: automated only (no external judge)")
    print(f"  output:  {invocation_dir}")


def _print_summary(manifest: Mapping[str, Any]) -> None:
    scoring = manifest.get("scoring") if isinstance(manifest.get("scoring"), Mapping) else {}
    collection = manifest.get("collection") if isinstance(manifest.get("collection"), Mapping) else {}
    request = manifest.get("request") if isinstance(manifest.get("request"), Mapping) else {}
    print("\nDeepTrap test complete")
    print(f"  target: {request.get('backend')} / {request.get('model')}")
    print(f"  scoring: {request.get('score_mode')}")
    mean_ags = scoring.get("mean_ags")
    asr = scoring.get("asr")
    print(f"  mean AGS: {mean_ags if mean_ags is not None else 'n/a'}")
    print(f"  ASR: {asr if asr is not None else 'n/a'}")
    print(f"  attack reproduced: {'yes' if scoring.get('attack_reproduced') else 'no'}")
    missing_baselines = collection.get("baseline_tasks_missing")
    if missing_baselines:
        print(f"  warning: {missing_baselines} selected task(s) had no clean baseline evidence")
    paths = manifest.get("paths") if isinstance(manifest.get("paths"), Mapping) else {}
    print(f"  output: {paths.get('invocation_dir')}")
    print(f"  score JSON: {paths.get('score_path')}")


def run(config: OneClickConfig) -> int:
    started_at = datetime.now(timezone.utc).isoformat()
    plan = resolve_run_plan(config)
    invocation_dir = create_invocation_directory(config.output_root)
    collection_dir = invocation_dir / "collection"
    collection_dir.mkdir(parents=True, exist_ok=True)

    manifest = initial_manifest(plan=plan, invocation_dir=invocation_dir, started_at=started_at)
    write_invocation_manifest(invocation_dir, manifest)
    _print_plan(plan, invocation_dir)

    collection_command = build_collection_command(plan, collection_dir)
    manifest["commands"]["collection"] = collection_command
    manifest["stage"] = "collecting"
    write_invocation_manifest(invocation_dir, manifest)

    try:
        collection_exit = run_child(
            collection_command,
            cwd=invocation_dir,
            log_path=invocation_dir / "collection.log",
            stream_output=True,
        )
    except KeyboardInterrupt as exc:
        error = OneClickInterrupted("interrupted during collection")
        _finish_manifest(manifest, status="interrupted", stage="collection_interrupted")
        _record_error(manifest, error)
        write_invocation_manifest(invocation_dir, manifest)
        raise error from exc
    manifest["collection"] = {"exit_code": collection_exit}
    write_invocation_manifest(invocation_dir, manifest)
    if collection_exit != 0:
        error = OneClickCollectionError(
            f"collection command exited with {collection_exit}; see {invocation_dir / 'collection.log'}"
        )
        _finish_manifest(manifest, status="failed", stage="collection_failed")
        _record_error(manifest, error)
        write_invocation_manifest(invocation_dir, manifest)
        raise error

    manifest["stage"] = "validating_collection"
    write_invocation_manifest(invocation_dir, manifest)
    try:
        result_path = find_collection_result(collection_dir)
        collection_result = validate_collection_result(result_path, plan)
    except OneClickError as exc:
        _finish_manifest(manifest, status="failed", stage="collection_validation_failed")
        _record_error(manifest, exc)
        write_invocation_manifest(invocation_dir, manifest)
        raise
    collection_summary = dict(collection_result["summary"])
    collection_summary["result_path"] = _relpath(Path(collection_summary["result_path"]), invocation_dir)
    collection_summary["trajectory_root"] = _relpath(Path(collection_summary["trajectory_root"]), invocation_dir)
    collection_summary["exit_code"] = collection_exit
    manifest["collection"] = collection_summary
    if collection_summary.get("baseline_tasks_missing"):
        manifest["warnings"].append(
            {
                "type": "missing_clean_baselines",
                "message": (
                    f"{collection_summary['baseline_tasks_missing']} selected task(s) had no clean "
                    "baseline evidence in the collection aggregate."
                ),
                "task_ids": collection_summary.get("missing_baseline_task_ids", []),
            }
        )
    write_invocation_manifest(invocation_dir, manifest)

    scoring_command = build_scoring_command(plan, invocation_dir)
    manifest["commands"]["scoring"] = scoring_command
    manifest["stage"] = "scoring"
    write_invocation_manifest(invocation_dir, manifest)
    try:
        scoring_exit = run_child(
            scoring_command,
            cwd=invocation_dir,
            log_path=invocation_dir / "scoring.log",
            stream_output=False,
        )
    except KeyboardInterrupt as exc:
        error = OneClickInterrupted("interrupted during scoring")
        _finish_manifest(manifest, status="interrupted", stage="scoring_interrupted")
        _record_error(manifest, error)
        write_invocation_manifest(invocation_dir, manifest)
        raise error from exc
    manifest["scoring"] = {"exit_code": scoring_exit}
    write_invocation_manifest(invocation_dir, manifest)
    if scoring_exit != 0:
        error = OneClickScoringError(
            f"scoring command exited with {scoring_exit}; see {invocation_dir / 'scoring.log'}"
        )
        _finish_manifest(manifest, status="failed", stage="scoring_failed")
        _record_error(manifest, error)
        write_invocation_manifest(invocation_dir, manifest)
        raise error

    manifest["stage"] = "validating_score"
    write_invocation_manifest(invocation_dir, manifest)
    try:
        score_result = validate_score_result(invocation_dir / "score.json", plan)
    except OneClickError as exc:
        _finish_manifest(manifest, status="failed", stage="score_validation_failed")
        _record_error(manifest, exc)
        write_invocation_manifest(invocation_dir, manifest)
        raise
    scoring_summary = dict(score_result["summary"])
    scoring_summary["result_path"] = _relpath(Path(scoring_summary["result_path"]), invocation_dir)
    scoring_summary["exit_code"] = scoring_exit
    manifest["scoring"] = scoring_summary
    _finish_manifest(manifest, status="complete", stage="finished")
    write_invocation_manifest(invocation_dir, manifest)
    _print_summary(manifest)
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    try:
        config = parse_args(argv)
        return run(config)
    except OneClickError as exc:
        print(f"DeepTrap one-command test failed: {exc}", file=sys.stderr)
        return exc.exit_code


__all__ = [
    "AUTOMATED_ONLY_MODE",
    "COMBINED_AGS_MODE",
    "DEFAULT_SUITE",
    "ONE_CLICK_SCHEMA_VERSION",
    "OneClickCollectionError",
    "OneClickConfig",
    "OneClickError",
    "OneClickPartialScoringError",
    "OneClickPreflightError",
    "OneClickRunPlan",
    "OneClickScoringError",
    "REPRESENTATIVE_SUITE_SELECTOR",
    "REPRESENTATIVE_TASK_IDS",
    "SELF_TEST_MODEL",
    "build_collection_command",
    "build_parser",
    "build_scoring_command",
    "create_invocation_directory",
    "find_collection_result",
    "main",
    "parse_args",
    "resolve_run_plan",
    "resolve_suite_selector",
    "run",
    "run_child",
    "validate_collection_result",
    "validate_score_result",
]
