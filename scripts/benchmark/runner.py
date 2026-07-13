"""Benchmark execution orchestration."""

from __future__ import annotations

import argparse
import atexit
import contextvars
import json
import logging
import statistics
import sys
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import replace
from pathlib import Path
from typing import Any, Dict, Optional

from lib_reward import ATTACK_SUCCESS_THRESHOLD, REWARD_JUDGE_MODEL
from lib_gateway_lock import acquire as _gw_acquire, release as _gw_release
from lib_tasks import Task, TaskLoader
from lib_taxonomy import infer_behavior_from_metadata
from lib_training_artifacts import (
    TrainingArtifactRecorder,
    activate_recorder,
    get_current_recorder,
    safe_artifact_name,
)

from benchmark.backends.base import BackendInitializationError, BackendRunContext
from benchmark.backends.common import execution_error_result
from benchmark.backends.registry import get_backend
from benchmark.baseline import _load_baseline_for_task, _pregenerate_baselines, _scene_for_task
from benchmark.evaluation import _evaluate_attack_for_task
from benchmark.metrics import (
    _compute_efficiency_summary,
    _compute_pass_power_summary,
    _log_attack_eval_summary,
    _log_category_summary,
    _log_efficiency_summary,
    build_attack_summary,
)
from benchmark.task_loading import _build_scene_index, select_task_files_for_suite
from benchmark.trajectories import persist_trajectory
from benchmark.ui import _colorize_gradient, _get_git_version, _load_ascii_art, _next_run_id

logger = logging.getLogger("benchmark")


def _execution_feedback(result: Dict[str, Any], backend_name: str) -> Dict[str, Any]:
    return {
        "backend": result.get("backend", backend_name),
        "transcript": result.get("transcript", []),
        "stdout": result.get("stdout", ""),
        "stderr": result.get("stderr", ""),
        "api_audit": result.get("api_audit", {}),
        "api_endpoints": result.get("api_endpoints", {}),
        "status": result.get("status"),
        "timed_out": result.get("timed_out"),
        "exit_code": result.get("exit_code"),
    }


def _attempt_run_id(run_id: str, run_index: int) -> str:
    return f"{run_id}-{run_index + 1}"


def _attempt_context(
    context: BackendRunContext,
    *,
    attempt_run_id: str,
    run_index: int,
    runs_per_task: int,
    run_workers: int,
    worker_id: int,
    extra_metadata: Optional[Dict[str, Any]] = None,
) -> BackendRunContext:
    metadata = dict(context.metadata)
    metadata.update(
        {
            "attempt_run_id": attempt_run_id,
            "run_index": run_index + 1,
            "run_number": run_index + 1,
            "runs_per_task": runs_per_task,
            "run_worker_id": worker_id,
            "run_worker_label": f"w{worker_id}",
            "run_workers": run_workers,
        }
    )
    if extra_metadata:
        metadata.update(extra_metadata)
    return replace(context, metadata=metadata)


def _attempt_error_record(
    *,
    task: Task,
    context: BackendRunContext,
    run_index: int,
    stderr: str,
    execution_time: float = 0.0,
) -> Dict[str, Any]:
    return {
        "run_index": run_index,
        "result": execution_error_result(
            context=context,
            task=task,
            stderr=stderr,
            execution_time=execution_time,
        ),
        "attack_eval": None,
        "execution_error": stderr,
        "evaluation_error": None,
    }


def _persist_trajectory_before_scoring(
    *,
    backend: Any,
    task: Task,
    result: Dict[str, Any],
    context: BackendRunContext,
    scene_index: Dict[str, Dict[str, Any]],
    model: str,
    judge_model: Optional[str],
) -> None:
    """Best-effort trajectory write before inline scoring begins."""

    recorder = get_current_recorder()
    if recorder is None:
        return
    try:
        path = persist_trajectory(
            recorder=recorder,
            task=task,
            execution_result=result,
            context=context,
            scene_index=scene_index,
            model=model,
            judge_model=judge_model,
        )
        logger.info("Wrote %s trajectory artifact: %s", getattr(backend, "name", "backend"), path)
    except Exception as exc:  # pragma: no cover - artifact failure should not change scoring
        logger.warning(
            "Failed to write trajectory for %s via %s: %s",
            task.task_id,
            getattr(backend, "name", "backend"),
            exc,
        )


_persist_openclaw_trajectory_before_scoring = _persist_trajectory_before_scoring


def _invalid_attack_eval(error_message: str, *, error_type: str) -> Dict[str, Any]:
    """Return a RewardResult-shaped invalid evaluation for failed attempts."""

    return {
        "score": 0.0,
        "attack_success": 0.0,
        "stealth": 0.0,
        "defense_score": 0.0,
        "breakdown": {},
        "notes": "",
        "is_success": False,
        "security_awareness": {},
        "interception": {},
        "usage": {},
        "timing": {},
        "behavior_type": "",
        "behavior_id": "",
        "behavior_label": "",
        "scoring_family": "",
        "legacy_risk_type": "",
        "evaluation_error": True,
        "error_type": error_type,
        "error_message": error_message,
    }


def _execution_error_attack_eval(error_message: str) -> Dict[str, Any]:
    return _invalid_attack_eval(error_message, error_type="execution_error")


def _evaluation_error_attack_eval(error_message: str) -> Dict[str, Any]:
    return _invalid_attack_eval(error_message, error_type="evaluation_error")


def _execute_and_evaluate_attempt(
    *,
    backend: Any,
    task: Task,
    context: BackendRunContext,
    scene_index: Dict[str, Dict[str, Any]],
    model: str,
    judge_model: Optional[str],
    verbose: bool,
    run_index: int,
    runs_per_task: int,
    run_workers: int,
    worker_id: int,
) -> Dict[str, Any]:
    attempt_id = _attempt_run_id(context.run_id, run_index)
    attempt_context = _attempt_context(
        context,
        attempt_run_id=attempt_id,
        run_index=run_index,
        runs_per_task=runs_per_task,
        run_workers=run_workers,
        worker_id=worker_id,
    )
    logger.info("\n%s", "=" * 80)
    logger.info(
        "📋 Task %s (Run %s/%s, worker %s/%s)",
        task.task_id,
        run_index + 1,
        runs_per_task,
        attempt_context.metadata["run_worker_id"],
        run_workers,
    )
    logger.info("%s", "=" * 80)
    execution_error = None
    evaluation_error = None
    try:
        result = backend.execute_task(
            task=task,
            context=attempt_context,
            attempt_run_id=attempt_id,
        )
    except Exception as exc:
        execution_error = str(exc)
        logger.warning("Task execution failed for %s, continuing: %s", task.task_id, exc)
        result = execution_error_result(
            context=attempt_context,
            task=task,
            stderr=execution_error,
        )
    _persist_trajectory_before_scoring(
        backend=backend,
        task=task,
        result=result,
        context=attempt_context,
        scene_index=scene_index,
        model=model,
        judge_model=judge_model,
    )
    try:
        attack_eval = _evaluate_attack_for_task(
            task=task,
            execution_result=result,
            scene_index=scene_index,
            model=model,
            judge_model=judge_model,
            verbose=verbose,
            backend_name=backend.name,
        )
    except Exception as exc:  # noqa: BLE001 - keep execution artifacts linked to failed scoring
        evaluation_error = str(exc)
        logger.warning("Attack evaluation failed for %s, continuing: %s", task.task_id, exc)
        attack_eval = None
    return {
        "run_index": run_index,
        "result": result,
        "attack_eval": attack_eval,
        "execution_error": execution_error,
        "evaluation_error": evaluation_error,
    }


def _log_attempt_outcome(
    *,
    task: Task,
    attack_eval: Any,
    execution_error: Optional[str],
    evaluation_error: Optional[str] = None,
) -> None:
    if attack_eval is not None:
        attack_emoji = (
            "⚠️" if attack_eval.evaluation_error else ("🔥" if attack_eval.is_success else "🛡️")
        )
        breakdown = attack_eval.breakdown or {}
        py_attack = float(breakdown.get("auto_attack_success", 0.0))
        llm_attack = float(breakdown.get("llm_attack_success", 0.0))
        awareness = attack_eval.security_awareness or {}
        interception = attack_eval.interception or {}
        if attack_eval.evaluation_error:
            logger.warning(
                "%s Task %s: evaluation invalid (%s: %s)",
                attack_emoji,
                task.task_id,
                attack_eval.error_type or "evaluation_error",
                (attack_eval.error_message or attack_eval.notes)[:200],
            )
        else:
            logger.info(
                "%s Task %s: defense=%.0f%% (AGS=%.2f [py=%.2f llm=%.2f] "
                "stealth=%.2f awareness=%.2f stage=%s)",
                attack_emoji,
                task.task_id,
                attack_eval.defense_score * 100,
                attack_eval.attack_success,
                py_attack,
                llm_attack,
                attack_eval.stealth,
                float(awareness.get("score", 0.0)),
                interception.get("stage", "unclear"),
            )
        if attack_eval.notes:
            logger.info("   Notes: %s", attack_eval.notes[:200])
    elif execution_error:
        logger.warning("❌ Task %s: execution failed: %s", task.task_id, execution_error[:200])
    elif evaluation_error:
        logger.warning("❌ Task %s: evaluation failed: %s", task.task_id, evaluation_error[:200])


def run_benchmark(args: argparse.Namespace) -> None:
    """Main entry point for the ActBench runner."""
    script_dir = Path(__file__).resolve().parents[1]
    skill_root = script_dir.parent  # Parent of scripts/ is the skill root

    logger.info("🦞🦀🦐 ActBench - Target-Agent Security Evaluation")
    ascii_crab = _load_ascii_art(skill_root, "crab.txt")
    if ascii_crab:
        print("\n" + _colorize_gradient(ascii_crab) + "\n")
    else:
        print("\n" + "🦀 " * 30)
        print("🦀 " * 30 + "\n")
    logger.info("🦞🦀🦐 Starting ActBench run 🦐🦀🦞")

    if args.tasks_dir:
        tasks_dir = Path(args.tasks_dir)
    else:
        tasks_dir = skill_root / "tasks"
        cwd_tasks = Path.cwd() / "tasks"
        if not tasks_dir.exists() and cwd_tasks.exists():
            skill_root = Path.cwd()
            tasks_dir = cwd_tasks

    if not tasks_dir.exists():
        logger.error(f"❌ Tasks directory not found: {tasks_dir}")
        sys.exit(1)

    logger.info("🔧 Initializing task loader...")
    logger.info("📁 Using tasks directory: %s", tasks_dir)

    logger.info("📂 Resolving task suite: %s", args.suite)
    try:
        task_files = select_task_files_for_suite(tasks_dir, args.suite)
    except ValueError as exc:
        logger.error("❌ %s", exc)
        sys.exit(2)
    logger.info("📂 Loading %d selected task(s)...", len(task_files))
    tasks = TaskLoader(tasks_dir).load_task_files(task_files)
    logger.info("Loaded %d selected task(s)", len(tasks))
    if len(tasks) != len(task_files):
        logger.error(
            "❌ Loaded only %d/%d selected task(s); aborting instead of producing partial results",
            len(tasks),
            len(task_files),
        )
        sys.exit(1)
    if not tasks:
        logger.error("❌ No tasks selected for suite %r", args.suite)
        sys.exit(2)
    scene_index = _build_scene_index(skill_root)

    backend_name = getattr(args, "backend", "openclaw")
    try:
        backend = get_backend(backend_name)
    except ValueError as exc:
        logger.error("❌ %s", exc)
        sys.exit(2)

    runs_per_task = max(1, args.runs)
    raw_run_workers = getattr(args, "run_workers", 1)
    run_workers = 1 if raw_run_workers is None else int(raw_run_workers)
    if run_workers < 1:
        logger.error("❌ --run-workers must be a positive integer")
        sys.exit(2)
    effective_run_workers = min(run_workers, runs_per_task)
    if effective_run_workers > 1 and not getattr(backend, "supports_parallel_runs", False):
        logger.error(
            "❌ Backend %s does not support same-task parallel runs; use --run-workers 1",
            backend.name,
        )
        sys.exit(2)

    model_id = args.model
    model_slug = backend.slugify_model(model_id)
    run_root = Path("/tmp/claweval")
    run_id = _next_run_id(run_root)
    skill_dir = skill_root
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    agent_id = backend.make_agent_id(model_id)
    # Use a shared workspace for the agent - we'll copy fixtures per task
    agent_workspace = Path(f"/tmp/claweval/{run_id}/agent_workspace")
    command = "actbench " + " ".join(sys.argv[1:])
    backend_context = BackendRunContext(
        backend=backend.name,
        model=model_id,
        run_id=run_id,
        run_root=run_root,
        skill_dir=skill_dir,
        agent_id=agent_id,
        agent_workspace=agent_workspace,
        timeout_multiplier=args.timeout_multiplier,
        verbose=args.verbose,
        metadata={
            "runs_per_task": runs_per_task,
            "run_workers": effective_run_workers,
            "requested_run_workers": run_workers,
            "command": command,
        },
    )

    training_recorder = None
    if not args.no_training_artifacts:
        artifact_root = (
            Path(args.training_artifact_dir)
            if args.training_artifact_dir
            else output_dir / f"{run_id}_{model_slug}_artifacts"
        )
        training_recorder = TrainingArtifactRecorder(
            root=artifact_root,
            run_kind="actbench",
            run_id=run_id,
            metadata={
                "model": model_id,
                "backend": backend.name,
                "backend_metadata": {
                    "name": backend.name,
                    "model": model_id,
                    "agent_id": agent_id,
                },
                "judge_model": args.judge_model or REWARD_JUDGE_MODEL,
                "suite": args.suite,
                "runs_per_task": runs_per_task,
                "run_workers": effective_run_workers,
                "requested_run_workers": run_workers,
                "tasks_dir": str(tasks_dir),
                "actbench_version": _get_git_version(skill_root),
                "benchmark_version": _get_git_version(skill_root),
            },
        )
        activate_recorder(training_recorder)
    else:
        activate_recorder(None)

    gateway_lock_acquired = False
    gateway_lock_atexit_callback = None
    backend_initialized = False
    try:
        if backend.uses_gateway_lock:
            # Register this ActBench run's gateway agent slot (visibility, not fail-fast):
            # ActBench uses a run_id-scoped workspace, but concurrent workloads still
            # need to see that this slot is busy.
            # Stale locks are reaped on read, so a hard kill cannot wedge the slot.
            _gw_acquire(
                agent_id,
                role="actbench",
                model=model_id,
                command=command,
            )
            gateway_lock_acquired = True

            def _release_gateway_lock_at_exit(agent_id: str = agent_id) -> None:
                _gw_release(agent_id)

            gateway_lock_atexit_callback = _release_gateway_lock_at_exit
            atexit.register(gateway_lock_atexit_callback)

        try:
            backend.initialize_run(backend_context)
            backend_initialized = True
        except BackendInitializationError as exc:
            logger.error("❌ Backend %s could not be initialized: %s", backend.name, exc)
            sys.exit(2)

        results = []
        grades_by_task_id = {}
        attack_eval_by_task_id = {}
        sanity_task_id = "task_00_sanity"

        tasks_to_run = tasks
        tasks_by_id = {task.task_id: task for task in tasks_to_run}
        if training_recorder:
            task_artifacts = [
                {
                    "task_id": task.task_id,
                    "name": task.name,
                    "category": task.category,
                    "prompt": task.prompt,
                    "frontmatter": task.frontmatter,
                    "workspace_files": task.workspace_files,
                }
                for task in tasks_to_run
            ]
            training_recorder.write_json("actbench_tasks.json", task_artifacts)
            training_recorder.write_json("benchmark_tasks.json", task_artifacts)

        if not getattr(args, "skip_baseline_gen", False):

            def _baseline_context(
                task: Task,
                scenario: str,
                attempt_run_id: str,
                baseline_index: int,
            ) -> BackendRunContext:
                return _attempt_context(
                    backend_context,
                    attempt_run_id=attempt_run_id,
                    run_index=baseline_index,
                    runs_per_task=1,
                    run_workers=1,
                    worker_id=1,
                    extra_metadata={
                        "baseline": True,
                        "baseline_scenario": scenario,
                        "baseline_task_id": task.task_id,
                        "baseline_index": baseline_index + 1,
                    },
                )

            _pregenerate_baselines(
                tasks=tasks_to_run,
                scene_index=scene_index,
                model=model_id,
                backend=backend,
                context=backend_context,
                run_id=run_id,
                context_factory=_baseline_context,
            )

        for i, task in enumerate(tasks_to_run, 1):
            logger.info("\n🚩 Task %s/%s: %s", i, len(tasks_to_run), task.task_id)
            task_results = []
            if effective_run_workers > 1:
                logger.info(
                    "🔁 Running %d repeats with %d same-task workers",
                    runs_per_task,
                    effective_run_workers,
                )

            if effective_run_workers == 1:
                attempt_records = [
                    _execute_and_evaluate_attempt(
                        backend=backend,
                        task=task,
                        context=backend_context,
                        scene_index=scene_index,
                        model=model_id,
                        judge_model=args.judge_model,
                        verbose=args.verbose,
                        run_index=run_index,
                        runs_per_task=runs_per_task,
                        run_workers=effective_run_workers,
                        worker_id=1,
                    )
                    for run_index in range(runs_per_task)
                ]
            else:
                attempt_records = []
                next_run_index = 0
                futures: Dict[Any, tuple[int, int]] = {}

                def _submit_attempt(
                    executor: ThreadPoolExecutor,
                    *,
                    run_index: int,
                    worker_id: int,
                ) -> None:
                    attempt_contextvars = contextvars.copy_context()
                    future = executor.submit(
                        attempt_contextvars.run,
                        _execute_and_evaluate_attempt,
                        backend=backend,
                        task=task,
                        context=backend_context,
                        scene_index=scene_index,
                        model=model_id,
                        judge_model=args.judge_model,
                        verbose=args.verbose,
                        run_index=run_index,
                        runs_per_task=runs_per_task,
                        run_workers=effective_run_workers,
                        worker_id=worker_id,
                    )
                    futures[future] = (run_index, worker_id)

                with ThreadPoolExecutor(max_workers=effective_run_workers) as executor:
                    for worker_id in range(1, effective_run_workers + 1):
                        if next_run_index >= runs_per_task:
                            break
                        _submit_attempt(
                            executor,
                            run_index=next_run_index,
                            worker_id=worker_id,
                        )
                        next_run_index += 1

                    while futures:
                        done, _ = wait(futures, return_when=FIRST_COMPLETED)
                        for future in done:
                            run_index, worker_id = futures.pop(future)
                            try:
                                attempt_records.append(future.result())
                            except Exception as exc:
                                attempt_id = _attempt_run_id(backend_context.run_id, run_index)
                                attempt_context = _attempt_context(
                                    backend_context,
                                    attempt_run_id=attempt_id,
                                    run_index=run_index,
                                    runs_per_task=runs_per_task,
                                    run_workers=effective_run_workers,
                                    worker_id=worker_id,
                                )
                                message = f"attempt worker failed: {exc}"
                                logger.warning(
                                    "Task attempt failed for %s run %s/%s, continuing: %s",
                                    task.task_id,
                                    run_index + 1,
                                    runs_per_task,
                                    exc,
                                )
                                attempt_records.append(
                                    _attempt_error_record(
                                        task=task,
                                        context=attempt_context,
                                        run_index=run_index,
                                        stderr=message,
                                    )
                                )
                            if next_run_index < runs_per_task:
                                _submit_attempt(
                                    executor,
                                    run_index=next_run_index,
                                    worker_id=worker_id,
                                )
                                next_run_index += 1

            for attempt_record in sorted(attempt_records, key=lambda item: item["run_index"]):
                result = attempt_record["result"]
                attack_eval = attempt_record["attack_eval"]
                execution_error = attempt_record["execution_error"]
                evaluation_error = attempt_record.get("evaluation_error")

                task_results.append(result)
                results.append(result)
                attack_eval_entry = None
                if attack_eval is not None:
                    attack_eval_entry = attack_eval.to_dict()
                elif execution_error:
                    attack_eval_entry = _execution_error_attack_eval(execution_error)
                elif evaluation_error:
                    attack_eval_entry = _evaluation_error_attack_eval(evaluation_error)
                if attack_eval_entry is not None:
                    attack_eval_by_task_id.setdefault(task.task_id, []).append(attack_eval_entry)
                if training_recorder and result.get("training_artifact_key"):
                    run_key = result["training_artifact_key"]
                    run_dir = Path("runs") / safe_artifact_name(run_key)
                    training_recorder.write_json(run_dir / "agent_execution.json", result)
                    if backend.name == "openclaw":
                        training_recorder.write_json(run_dir / "openclaw_execution.json", result)
                    training_recorder.write_json(
                        run_dir / "evaluation.json",
                        (
                            attack_eval.to_dict()
                            if attack_eval is not None
                            else {
                                "error": execution_error or evaluation_error,
                                "error_type": (
                                    "execution_error"
                                    if execution_error
                                    else "evaluation_error" if evaluation_error else "missing_evaluation"
                                ),
                            }
                        ),
                    )

                _log_attempt_outcome(
                    task=task,
                    attack_eval=attack_eval,
                    execution_error=execution_error,
                    evaluation_error=evaluation_error,
                )

            # Build grading from attack_eval (defense = 1 - attack)
            if attack_eval_by_task_id.get(task.task_id):
                all_attack_runs = attack_eval_by_task_id[task.task_id]
                valid_attack_runs = [
                    entry for entry in all_attack_runs if not entry.get("evaluation_error")
                ]
                invalid_count = len(all_attack_runs) - len(valid_attack_runs)
                attack_scores = [entry["score"] for entry in valid_attack_runs]
                defense_scores = [1.0 - s for s in attack_scores]
                defense_passes = [score < ATTACK_SUCCESS_THRESHOLD for score in attack_scores]
                pass_count = sum(1 for passed in defense_passes if passed)
                all_pass = bool(defense_passes) and all(defense_passes)
                pass_power_k = len(defense_passes)
                scoring_semantics = {
                    "scoring_semantics": "actbench_ags",
                    "attack_success_threshold": ATTACK_SUCCESS_THRESHOLD,
                    "defense_pass_condition": "attack_success < attack_success_threshold",
                    "repeat_count": len(all_attack_runs),
                    "valid_repeat_count": len(valid_attack_runs),
                    "attack_all_pass": bool(defense_passes)
                    and all(score >= ATTACK_SUCCESS_THRESHOLD for score in attack_scores),
                    "defense_all_pass": all_pass,
                }
                attack_eval_by_task_id[task.task_id] = {
                    "runs": all_attack_runs,
                    "valid_runs": len(valid_attack_runs),
                    "invalid_runs": invalid_count,
                    "evaluation_error_count": invalid_count,
                    "mean": statistics.mean(attack_scores) if attack_scores else 0.0,
                    "std": statistics.stdev(attack_scores) if len(attack_scores) > 1 else 0.0,
                    "min": min(attack_scores) if attack_scores else 0.0,
                    "max": max(attack_scores) if attack_scores else 0.0,
                    "defense_passes": defense_passes,
                    "pass_count": pass_count,
                    "pass_rate": pass_count / len(defense_passes) if defense_passes else 0.0,
                    "all_pass": all_pass,
                    "pass_power_k": pass_power_k,
                    "pass_power_label": f"Pass^{pass_power_k}",
                    "pass_3": all_pass if pass_power_k == 3 else None,
                    "pass_threshold_attack_success_lt": ATTACK_SUCCESS_THRESHOLD,
                    **scoring_semantics,
                }
                # Grading = defense score (inverted attack score, 0-1)
                grades_by_task_id[task.task_id] = {
                    "mean": statistics.mean(defense_scores) if defense_scores else 0.0,
                    "std": statistics.stdev(defense_scores) if len(defense_scores) > 1 else 0.0,
                    "min": min(defense_scores) if defense_scores else 0.0,
                    "max": max(defense_scores) if defense_scores else 0.0,
                    "defense_passes": defense_passes,
                    "pass_count": pass_count,
                    "pass_rate": pass_count / len(defense_passes) if defense_passes else 0.0,
                    "all_pass": all_pass,
                    "pass_power_k": pass_power_k,
                    "pass_power_label": f"Pass^{pass_power_k}",
                    "pass_3": all_pass if pass_power_k == 3 else None,
                    "pass_threshold_attack_success_lt": ATTACK_SUCCESS_THRESHOLD,
                    "valid_runs": len(valid_attack_runs),
                    "invalid_runs": invalid_count,
                    "evaluation_error_count": invalid_count,
                    **scoring_semantics,
                }
            else:
                empty_scoring_semantics = {
                    "scoring_semantics": "actbench_ags",
                    "attack_success_threshold": ATTACK_SUCCESS_THRESHOLD,
                    "defense_pass_condition": "attack_success < attack_success_threshold",
                    "repeat_count": 0,
                    "valid_repeat_count": 0,
                    "attack_all_pass": False,
                    "defense_all_pass": False,
                }
                grades_by_task_id[task.task_id] = {
                    "mean": 0.0,
                    "std": 0.0,
                    "min": 0.0,
                    "max": 0.0,
                    "defense_passes": [],
                    "pass_count": 0,
                    "pass_rate": 0.0,
                    "all_pass": False,
                    "pass_power_k": 0,
                    "pass_power_label": "Pass^0",
                    "pass_3": None,
                    "pass_threshold_attack_success_lt": ATTACK_SUCCESS_THRESHOLD,
                    **empty_scoring_semantics,
                }

            all_runs_missing_transcript = all(
                not run_result.get("transcript") for run_result in task_results
            )
            if (
                task.task_id == sanity_task_id
                and grades_by_task_id[task.task_id]["mean"] == 0.0
                and not args.no_fail_fast
                and not all_runs_missing_transcript
            ):
                logger.error(
                    "🚨 FAIL FAST: Sanity check (%s) scored 0%%. "
                    "Aborting benchmark run to avoid wasting resources.",
                    sanity_task_id,
                )
                sys.exit(3)
            if task.task_id == sanity_task_id and grades_by_task_id[task.task_id]["mean"] == 0.0:
                if all_runs_missing_transcript:
                    logger.warning(
                        "⚠️ Sanity check scored 0%% but transcripts were missing for all runs; "
                        "skipping fail-fast as likely infrastructure/logging issue."
                    )

        # Pre-load benign baselines (cached per scene+model) so post-hoc analysis
        # can distinguish over-refuse from real attack success: if baseline
        # completed the task but the under-attack run failed, the model is being
        # over-cautious; if baseline ALSO failed, the task may exceed model
        # capability rather than the agent being attacked successfully.
        baselines_by_task_id: Dict[str, Optional[Dict[str, Any]]] = {}
        baseline_hits = 0
        for tid, t in tasks_by_id.items():
            scene = _scene_for_task(t, scene_index)
            b = _load_baseline_for_task(t, model_id, scene=scene, backend_name=backend.name)
            baselines_by_task_id[tid] = b
            if b is not None:
                baseline_hits += 1
        if baselines_by_task_id:
            logger.info(
                "🧪 Baseline cache: %d/%d tasks have a cached benign run",
                baseline_hits,
                len(baselines_by_task_id),
            )

        task_entries = []
        for result in results:
            tid = result["task_id"]
            baseline = baselines_by_task_id.get(tid)
            # Strip the heavy raw transcript before persisting; keep summary +
            # file ops for downstream analysis. Original cache file remains intact.
            baseline_lite = None
            if baseline is not None:
                baseline_lite = {
                    "scene_id": baseline.get("scene_id"),
                    "target_model": baseline.get("target_model"),
                    "backend": baseline.get("backend", backend.name),
                    "files_read": baseline.get("files_read", []),
                    "files_written": baseline.get("files_written", []),
                    "transcript_summary": baseline.get("transcript_summary", ""),
                    "execution_time": baseline.get("execution_time"),
                }
            if training_recorder and result.get("training_artifact_key"):
                run_dir = Path("runs") / safe_artifact_name(str(result["training_artifact_key"]))
                training_recorder.write_json(run_dir / "baseline.json", baseline or {})
            task = tasks_by_id[tid]
            behavior = infer_behavior_from_metadata(task.frontmatter or {}, path=task.file_path)
            task_entries.append(
                {
                    "task_id": tid,
                    "behavior_type": behavior.behavior_type,
                    "behavior_id": behavior.behavior_id,
                    "behavior_label": behavior.behavior_label,
                    "scoring_family": behavior.scoring_family,
                    "legacy_risk_type": behavior.legacy_risk_type,
                    "backend": result.get("backend", backend.name),
                    "backend_metadata": result.get(
                        "backend_metadata",
                        {"name": backend.name, "model": model_id, "agent_id": agent_id},
                    ),
                    "status": result["status"],
                    "timed_out": result["timed_out"],
                    "execution_time": result["execution_time"],
                    "transcript_length": len(result["transcript"]),
                    "usage": result.get("usage", {}),
                    "workspace": result["workspace"],
                    "training_artifact_key": result.get("training_artifact_key"),
                    "grading": grades_by_task_id[tid],
                    "attack_eval": attack_eval_by_task_id.get(tid),
                    "scoring_semantics": "actbench_ags",
                    "attack_success_threshold": ATTACK_SUCCESS_THRESHOLD,
                    "defense_pass_condition": "attack_success < attack_success_threshold",
                    "repeat_count": (attack_eval_by_task_id.get(tid) or grades_by_task_id[tid]).get(
                        "repeat_count", 0
                    ),
                    "valid_repeat_count": (
                        attack_eval_by_task_id.get(tid) or grades_by_task_id[tid]
                    ).get("valid_repeat_count", 0),
                    "attack_all_pass": (
                        attack_eval_by_task_id.get(tid) or grades_by_task_id[tid]
                    ).get("attack_all_pass", False),
                    "defense_all_pass": (
                        attack_eval_by_task_id.get(tid) or grades_by_task_id[tid]
                    ).get("defense_all_pass", False),
                    "agent_feedback": _execution_feedback(result, backend.name),
                    "openclaw_feedback": _execution_feedback(result, backend.name),
                    "frontmatter": tasks_by_id[tid].frontmatter,
                    "baseline": baseline_lite,
                }
            )

        efficiency = _compute_efficiency_summary(task_entries, grades_by_task_id)
        pass_power = _compute_pass_power_summary(attack_eval_by_task_id)

        aggregate = {
            "model": model_id,
            "backend": backend.name,
            "backend_metadata": {
                "name": backend.name,
                "model": model_id,
                "agent_id": agent_id,
            },
            "judge_model": args.judge_model or REWARD_JUDGE_MODEL,
            "actbench_version": _get_git_version(skill_root),
            "benchmark_version": _get_git_version(skill_root),
            "run_id": run_id,
            "timestamp": time.time(),
            "suite": args.suite,
            "runs_per_task": runs_per_task,
            "run_workers": effective_run_workers,
            "requested_run_workers": run_workers,
            "scoring_semantics": "actbench_ags",
            "attack_success_threshold": ATTACK_SUCCESS_THRESHOLD,
            "defense_pass_condition": "attack_success < attack_success_threshold",
            "tasks": task_entries,
            "efficiency": efficiency,
            "pass_power": pass_power,
        }
        if training_recorder:
            aggregate["training_artifact_dir"] = str(training_recorder.root)
            aggregate["training_manifest_path"] = str(training_recorder.root / "manifest.json")

        output_path = output_dir / f"{run_id}_{model_slug}.json"
        output_path.write_text(json.dumps(aggregate, indent=2), encoding="utf-8")
        if training_recorder:
            training_recorder.write_json("aggregate_result.json", aggregate)
            training_recorder.write_manifest({"aggregate_result": str(output_path)})

        # Compact, machine-readable per-task attack summary: lets curation tooling
        # read ags/py/llm/runs/attack_reproduced per task without grepping the
        # [FINAL] log table or parsing the full aggregate.
        attack_summary = build_attack_summary(attack_eval_by_task_id, tasks_by_id=tasks_by_id)
        attack_summary.update(
            {
                "model": model_id,
                "backend": backend.name,
                "run_id": run_id,
                "suite": args.suite,
                "runs_per_task": runs_per_task,
                "run_workers": effective_run_workers,
                "requested_run_workers": run_workers,
            }
        )
        summary_payload = json.dumps(attack_summary, indent=2)
        summary_path = output_dir / f"actbench_summary_{run_id}_{model_slug}.json"
        summary_path.write_text(summary_payload, encoding="utf-8")
        legacy_summary_path = output_dir / f"bench_summary_{run_id}_{model_slug}.json"
        legacy_summary_path.write_text(summary_payload, encoding="utf-8")

        # Calculate and log final score summary
        total_score = sum(grades_by_task_id[tid]["mean"] for tid in grades_by_task_id)
        max_score = float(len(grades_by_task_id))  # Each task has max_score of 1.0
        score_pct = (total_score / max_score * 100) if max_score > 0 else 0
        logger.info("📊 Final score: %.2f/%.0f (%.1f%%)", total_score, max_score, score_pct)
        logger.info(
            "🛡️ %s / All-pass: %d/%d tasks (%.1f%%); single-run pass: %d/%d (%.1f%%)",
            pass_power.get("label", "All-pass"),
            pass_power.get("all_pass_tasks", 0),
            pass_power.get("total_tasks", 0),
            float(pass_power.get("all_pass_rate", 0.0) or 0.0) * 100,
            pass_power.get("pass_runs", 0),
            pass_power.get("valid_runs", pass_power.get("total_runs", 0)),
            float(pass_power.get("pass_run_rate", 0.0) or 0.0) * 100,
        )
        if pass_power.get("invalid_runs"):
            logger.info(
                "⚠️ Invalid evaluation runs: %d/%d",
                pass_power.get("invalid_runs", 0),
                pass_power.get("total_runs", 0),
            )

        logger.info("Saved results to %s", output_path)
        logger.info(
            "[FINAL] Attack summary (%d/%d tasks reproduced) saved to %s (legacy alias: %s)",
            attack_summary.get("attack_reproduced_tasks", 0),
            attack_summary.get("total_tasks", 0),
            summary_path,
            legacy_summary_path,
        )
        _log_category_summary(task_entries, tasks_by_id, scene_index=scene_index)
        _log_attack_eval_summary(attack_eval_by_task_id, tasks_by_id, scene_index=scene_index)
        _log_efficiency_summary(efficiency, grades_by_task_id)
    finally:
        if backend_initialized:
            try:
                backend.finalize_run(backend_context)
            except Exception as exc:  # pragma: no cover - defensive cleanup logging
                logger.warning("Backend %s finalization failed: %s", backend.name, exc)
        if backend.uses_gateway_lock and gateway_lock_acquired:
            try:
                _gw_release(agent_id)
            finally:
                if gateway_lock_atexit_callback is not None:
                    try:
                        atexit.unregister(gateway_lock_atexit_callback)
                    except Exception as exc:  # pragma: no cover - defensive cleanup logging
                        logger.warning("Gateway lock atexit unregister failed: %s", exc)
