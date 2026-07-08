"""Benchmark execution orchestration."""

from __future__ import annotations

import argparse
import atexit
import json
import logging
import statistics
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

from lib_agent import (
    cleanup_agent_sessions,
    ensure_agent_exists,
    execute_openclaw_task,
    slugify_model,
)
from lib_reward import ATTACK_SUCCESS_THRESHOLD, REWARD_JUDGE_MODEL
from lib_gateway_lock import acquire as _gw_acquire, release as _gw_release
from lib_tasks import TaskLoader
from lib_taxonomy import infer_behavior_from_metadata
from lib_training_artifacts import TrainingArtifactRecorder, activate_recorder, safe_artifact_name

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
from benchmark.ui import _colorize_gradient, _get_git_version, _load_ascii_art, _next_run_id

logger = logging.getLogger("benchmark")


def run_benchmark(args: argparse.Namespace) -> None:
    """Main entry point for the ActBench runner."""
    script_dir = Path(__file__).resolve().parents[1]
    skill_root = script_dir.parent  # Parent of scripts/ is the skill root

    logger.info("🦞🦀🦐 ActBench - OpenClaw Security Evaluation")
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

    model_slug = slugify_model(args.model)
    run_root = Path("/tmp/claweval")
    run_id = _next_run_id(run_root)
    skill_dir = skill_root
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
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
                "model": args.model,
                "judge_model": args.judge_model or REWARD_JUDGE_MODEL,
                "suite": args.suite,
                "runs_per_task": args.runs,
                "tasks_dir": str(tasks_dir),
                "actbench_version": _get_git_version(skill_root),
                "benchmark_version": _get_git_version(skill_root),
            },
        )
        activate_recorder(training_recorder)
    else:
        activate_recorder(None)
    agent_id = f"bench-{model_slug}"
    # Use a shared workspace for the agent - we'll copy fixtures per task
    agent_workspace = Path(f"/tmp/claweval/{run_id}/agent_workspace")

    # Register this ActBench run's gateway agent slot (visibility, not fail-fast):
    # ActBench uses a run_id-scoped workspace, but concurrent workloads still
    # need to see that this slot is busy.
    # Stale locks are reaped on read, so a hard kill cannot wedge the slot.
    _gw_acquire(
        agent_id,
        role="actbench",
        model=args.model,
        command="actbench " + " ".join(sys.argv[1:]),
    )
    atexit.register(_gw_release, agent_id)

    # Trust openclaw's backend registry.
    # If the model id is invalid, ensure_agent_exists will fail loudly.
    ensure_agent_exists(agent_id, args.model, agent_workspace)
    cleanup_agent_sessions(agent_id)

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
        _pregenerate_baselines(
            tasks=tasks_to_run,
            scene_index=scene_index,
            model=args.model,
            agent_id=agent_id,
            run_id=run_id,
            skill_dir=skill_dir,
            timeout_multiplier=args.timeout_multiplier,
            verbose=args.verbose,
        )

    runs_per_task = max(1, args.runs)
    for i, task in enumerate(tasks_to_run, 1):
        task_results = []
        for run_index in range(runs_per_task):
            logger.info("\n%s", "=" * 80)
            logger.info(
                "📋 Task %s/%s (Run %s/%s)",
                i,
                len(tasks_to_run),
                run_index + 1,
                runs_per_task,
            )
            logger.info("%s", "=" * 80)
            execution_error = None
            try:
                result = execute_openclaw_task(
                    task=task,
                    agent_id=agent_id,
                    model_id=args.model,
                    run_id=f"{run_id}-{run_index + 1}",
                    timeout_multiplier=args.timeout_multiplier,
                    skill_dir=skill_dir,
                    verbose=args.verbose,
                )
            except Exception as exc:
                execution_error = str(exc)
                logger.warning("Task execution failed for %s, continuing: %s", task.task_id, exc)
                result = {
                    "agent_id": agent_id,
                    "task_id": task.task_id,
                    "status": "error",
                    "transcript": [],
                    "usage": {},
                    "workspace": "",
                    "exit_code": -1,
                    "timed_out": False,
                    "execution_time": 0.0,
                    "stdout": "",
                    "stderr": execution_error,
                    "api_audit": {},
                    "api_endpoints": {},
                }
            attack_eval = _evaluate_attack_for_task(
                task=task,
                execution_result=result,
                scene_index=scene_index,
                model=args.model,
                judge_model=args.judge_model,
                verbose=args.verbose,
            )

            task_results.append(result)
            results.append(result)
            if attack_eval is not None:
                attack_eval_by_task_id.setdefault(task.task_id, []).append(attack_eval.to_dict())
            if training_recorder and result.get("training_artifact_key"):
                run_key = result["training_artifact_key"]
                training_recorder.write_json(
                    Path("runs") / safe_artifact_name(run_key) / "openclaw_execution.json",
                    result,
                )
                training_recorder.write_json(
                    Path("runs") / safe_artifact_name(run_key) / "evaluation.json",
                    (
                        attack_eval.to_dict()
                        if attack_eval is not None
                        else {"error": execution_error}
                    ),
                )

            # Log score immediately
            if attack_eval is not None:
                attack_emoji = (
                    "⚠️"
                    if attack_eval.evaluation_error
                    else ("🔥" if attack_eval.is_success else "🛡️")
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
                logger.warning(
                    "❌ Task %s: execution failed: %s", task.task_id, execution_error[:200]
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
        b = _load_baseline_for_task(t, args.model, scene=scene)
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
                "attack_all_pass": (attack_eval_by_task_id.get(tid) or grades_by_task_id[tid]).get(
                    "attack_all_pass", False
                ),
                "defense_all_pass": (attack_eval_by_task_id.get(tid) or grades_by_task_id[tid]).get(
                    "defense_all_pass", False
                ),
                "openclaw_feedback": {
                    "transcript": result.get("transcript", []),
                    "stdout": result.get("stdout", ""),
                    "stderr": result.get("stderr", ""),
                    "api_audit": result.get("api_audit", {}),
                    "api_endpoints": result.get("api_endpoints", {}),
                    "status": result.get("status"),
                    "timed_out": result.get("timed_out"),
                    "exit_code": result.get("exit_code"),
                },
                "frontmatter": tasks_by_id[tid].frontmatter,
                "baseline": baseline_lite,
            }
        )

    efficiency = _compute_efficiency_summary(task_entries, grades_by_task_id)
    pass_power = _compute_pass_power_summary(attack_eval_by_task_id)

    aggregate = {
        "model": args.model,
        "judge_model": args.judge_model or REWARD_JUDGE_MODEL,
        "actbench_version": _get_git_version(skill_root),
        "benchmark_version": _get_git_version(skill_root),
        "run_id": run_id,
        "timestamp": time.time(),
        "suite": args.suite,
        "runs_per_task": runs_per_task,
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
            "model": args.model,
            "run_id": run_id,
            "suite": args.suite,
            "runs_per_task": runs_per_task,
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
    _gw_release(agent_id)
