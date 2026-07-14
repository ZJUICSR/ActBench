"""ActBench trajectory artifact construction and persistence."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, Optional

from lib_mock_secrets import materialized_secrets
from lib_reward import ATTACK_SUCCESS_THRESHOLD, REWARD_JUDGE_MODEL
from lib_tasks import Task
from lib_training_artifacts import TrainingArtifactRecorder, safe_artifact_name

from benchmark.artifacts import build_artifact_refs
from benchmark.baseline import _baseline_cache_path, _load_baseline_for_task, _scene_for_task
from benchmark.backends.base import BackendRunContext
from benchmark.evaluation import (
    _derive_attack_payload,
    _extract_malicious_skill_names,
    _resolve_task_behavior,
    _resolve_task_risk_type,
    _resolve_task_scenario,
)
from benchmark.scoring_guides import RISK_GUIDES

TRAJECTORY_SCHEMA_VERSION = "actbench.trajectory.v1"
OPENCLAW_TRAJECTORY_SCHEMA_VERSION = "actbench.openclaw_trajectory.v1"
SUPPORTED_TRAJECTORY_SCHEMA_VERSIONS = {
    TRAJECTORY_SCHEMA_VERSION,
    OPENCLAW_TRAJECTORY_SCHEMA_VERSION,
}
_BASELINE_DEFAULT = object()

_LANE_METADATA_KEYS = (
    "openclaw_base_agent_id",
    "openclaw_lane_id",
    "openclaw_lane_agent_id",
    "openclaw_lane_workspace",
)

_EXECUTION_FIELDS = (
    "status",
    "exit_code",
    "timed_out",
    "execution_time",
    "stdout",
    "stderr",
    "usage",
    "workspace",
    "api_audit",
    "api_endpoints",
    "training_artifact_key",
)

_EXECUTION_EXTRA_EXCLUDE = {
    "transcript",
    "attack_eval",
    "grading",
}


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def trajectory_artifact_key(
    *,
    task: Task,
    context: BackendRunContext,
    execution_result: Optional[Dict[str, Any]] = None,
) -> str:
    """Return the per-attempt artifact key, deriving a deterministic fallback if needed."""

    existing = (execution_result or {}).get("training_artifact_key")
    if existing:
        return safe_artifact_name(str(existing))
    metadata = context.metadata or {}
    attempt_run_id = metadata.get("attempt_run_id") or context.run_id
    return safe_artifact_name(f"{context.backend}_{attempt_run_id}_{task.task_id}")


def openclaw_trajectory_artifact_key(
    *,
    task: Task,
    context: BackendRunContext,
    execution_result: Optional[Dict[str, Any]] = None,
) -> str:
    """Compatibility alias for ``trajectory_artifact_key``."""

    return trajectory_artifact_key(
        task=task,
        context=context,
        execution_result=execution_result,
    )


def _task_payload(task: Task) -> Dict[str, Any]:
    return {
        "task_id": task.task_id,
        "name": task.name,
        "category": task.category,
        "grading_type": task.grading_type,
        "timeout_seconds": task.timeout_seconds,
        "prompt": task.prompt,
        "expected_behavior": task.expected_behavior,
        "grading_criteria": task.grading_criteria,
        "automated_checks": task.automated_checks,
        "llm_judge_rubric": task.llm_judge_rubric,
        "grading_weights": task.grading_weights,
        "frontmatter": task.frontmatter,
        "workspace_files": task.workspace_files,
        "source_path": str(task.file_path) if task.file_path else None,
    }


def _artifact_refs(
    *,
    recorder: Optional[TrainingArtifactRecorder],
    training_artifact_key: str,
    backend_name: Optional[str] = None,
) -> Dict[str, Any]:
    return build_artifact_refs(
        training_artifact_key=training_artifact_key,
        recorder=recorder,
        backend_name=backend_name,
    )


def _json_safe(value: Any) -> Any:
    try:
        json.dumps(value)
        return value
    except (TypeError, ValueError):
        return json.loads(json.dumps(value, default=str))


def _execution_payload(execution_result: Dict[str, Any]) -> Dict[str, Any]:
    payload = {key: execution_result.get(key) for key in _EXECUTION_FIELDS}
    payload["agent_id"] = execution_result.get("agent_id")
    payload["task_id"] = execution_result.get("task_id")
    extra = {
        key: _json_safe(value)
        for key, value in execution_result.items()
        if key not in _EXECUTION_FIELDS
        and key not in _EXECUTION_EXTRA_EXCLUDE
        and key not in {"agent_id", "task_id"}
    }
    if extra:
        payload["extra"] = extra
    return payload


def _backend_payload(
    *,
    context: BackendRunContext,
    execution_result: Dict[str, Any],
    model: str,
) -> Dict[str, Any]:
    backend_metadata = execution_result.get("backend_metadata")
    if not isinstance(backend_metadata, dict):
        backend_metadata = {}
    lane_metadata = {
        key: backend_metadata[key]
        for key in _LANE_METADATA_KEYS
        if backend_metadata.get(key) is not None
    }
    return {
        "name": execution_result.get("backend", context.backend),
        "model": model,
        "agent_id": execution_result.get("agent_id") or context.agent_id,
        "context_agent_id": context.agent_id,
        "backend_metadata": backend_metadata,
        "lane_metadata": lane_metadata,
    }


def _run_payload(
    *,
    context: BackendRunContext,
    training_artifact_key: str,
) -> Dict[str, Any]:
    metadata = context.metadata or {}
    return {
        "run_id": context.run_id,
        "attempt_run_id": metadata.get("attempt_run_id"),
        "run_index": metadata.get("run_index"),
        "run_number": metadata.get("run_number"),
        "runs_per_task": metadata.get("runs_per_task"),
        "run_worker_id": metadata.get("run_worker_id"),
        "run_worker_label": metadata.get("run_worker_label"),
        "run_workers": metadata.get("run_workers"),
        "requested_run_workers": metadata.get("requested_run_workers"),
        "command": metadata.get("command"),
        "training_artifact_key": training_artifact_key,
        "context_metadata": metadata,
    }


def _scoring_inputs(
    *,
    task: Task,
    execution_result: Dict[str, Any],
    scene_index: Dict[str, Dict[str, Any]],
    model: str,
    judge_model: Optional[str],
    backend_name: str,
    artifacts: Dict[str, Any],
    scene_override: Optional[Dict[str, Any]] = None,
    baseline_override: Any = _BASELINE_DEFAULT,
    execution_role: Optional[str] = None,
) -> Dict[str, Any]:
    execution_feedback_snapshot = {
        "status": execution_result.get("status"),
        "timed_out": execution_result.get("timed_out"),
        "exit_code": execution_result.get("exit_code"),
        "stdout": execution_result.get("stdout", ""),
        "stderr": execution_result.get("stderr", ""),
        "api_audit": execution_result.get("api_audit", {}),
        "api_endpoints": execution_result.get("api_endpoints", {}),
    }
    scenario = _resolve_task_scenario(task)
    payload: Dict[str, Any] = {
        "scoreable": bool(scenario),
        "scoring_semantics": "actbench_ags",
        "attack_success_threshold": ATTACK_SUCCESS_THRESHOLD,
        "defense_pass_condition": "attack_success < attack_success_threshold",
        "configured_judge_model": judge_model or REWARD_JUDGE_MODEL,
        "default_judge_model": REWARD_JUDGE_MODEL,
        "target_model": model,
        "backend_name": backend_name,
        "execution_role": execution_role,
        "replay_workspace_preference": "artifacts.workspace_after",
        "replay_workspace_path": artifacts.get("workspace_after"),
        "replay_workspace_absolute_path": artifacts.get("workspace_after_absolute"),
        "scorer_entrypoints": {
            "combined_ags": "benchmark.evaluation._evaluate_attack_for_task",
            "evaluate_attack": "lib_reward.evaluate_attack",
            "python_automated_checks": "lib_reward._run_automated_checks",
            "llm_judge": "lib_reward._run_llm_judge",
        },
    }
    if not scenario:
        payload["skip_reason"] = "missing_scenario"

    scene = scene_override if scene_override is not None else _scene_for_task(task, scene_index)
    if not scene:
        fm = task.frontmatter or {}
        scene = {
            "risk_goal": fm.get("risk_goal") or fm.get("attack_goal", ""),
            "user_prompt": fm.get("user_prompt", task.prompt),
            "attack_check_code": fm.get("attack_check_code", ""),
            "secrets": fm.get("secrets"),
            "workspace_files": [],
            "source": "task_frontmatter_fallback",
        }
    payload["scenario_id"] = scenario
    payload["scene"] = scene

    try:
        behavior = _resolve_task_behavior(task)
    except Exception as exc:  # pragma: no cover - defensive metadata capture
        behavior = None
        payload["behavior_error"] = str(exc)
    payload["behavior"] = behavior.to_dict() if behavior is not None else None

    try:
        risk_type = behavior.scoring_family if behavior is not None else _resolve_task_risk_type(task)
    except Exception as exc:  # pragma: no cover - defensive metadata capture
        risk_type = None
        payload["risk_type_error"] = str(exc)
    payload["risk_type"] = risk_type
    payload["reward_criteria"] = RISK_GUIDES.get(risk_type or "", {}).get("reward_criteria", {})

    attack_goal = scene.get("risk_goal") or (task.frontmatter or {}).get(
        "attack_goal", task.expected_behavior or task.prompt
    )
    if not isinstance(attack_goal, str):
        attack_goal = str(attack_goal)
    payload["attack_goal"] = attack_goal

    attack_payload = _derive_attack_payload(task, scene)
    payload["attack_payload"] = attack_payload
    payload["malicious_skill_names"] = _extract_malicious_skill_names(task, attack_payload) or []
    payload["user_prompt"] = scene.get("user_prompt", "")
    payload["attack_check_code"] = task.automated_checks or scene.get(
        "attack_check_code", ""
    )
    payload["secrets"] = materialized_secrets(scene, scene.get("workspace_files", []))

    cache_path = None
    if baseline_override is _BASELINE_DEFAULT:
        baseline = _load_baseline_for_task(task, model, scene=scene, backend_name=backend_name)
        cache_path = _baseline_cache_path(task, model, scene=scene, backend_name=backend_name)
    else:
        baseline = baseline_override
    payload["baseline"] = baseline
    payload["baseline_cache_path"] = str(cache_path) if cache_path is not None else None
    payload["baseline_artifact_path"] = artifacts.get("baseline")

    payload["execution_feedback_reconstruction"] = {
        "source": "trajectory.execution + trajectory.transcript.entries",
        "workspace_path_override": "trajectory.artifacts.workspace_after",
        "api_audit_path": artifacts.get("api_audit"),
        "api_endpoints_path": artifacts.get("api_endpoints"),
    }
    payload["execution_feedback_snapshot"] = execution_feedback_snapshot
    return payload


def _missing_transcript_source() -> Dict[str, Any]:
    return {
        "kind": "missing",
        "requested_session_id": None,
        "resolved_session_id": None,
        "transcript_path": None,
        "fallback_used": False,
    }


def _transcript_source_payload(execution_result: Dict[str, Any]) -> Dict[str, Any]:
    backend_metadata = _as_dict(execution_result.get("backend_metadata"))
    source = execution_result.get("transcript_source") or backend_metadata.get("transcript_source")
    if isinstance(source, dict):
        return source
    if isinstance(source, str) and source:
        return {"kind": source}
    return _missing_transcript_source()


def build_trajectory(
    *,
    task: Task,
    execution_result: Dict[str, Any],
    context: BackendRunContext,
    scene_index: Dict[str, Dict[str, Any]],
    model: str,
    judge_model: Optional[str],
    recorder: Optional[TrainingArtifactRecorder] = None,
    scene_override: Optional[Dict[str, Any]] = None,
    baseline_override: Any = _BASELINE_DEFAULT,
    execution_role: Optional[str] = None,
) -> Dict[str, Any]:
    """Build a replay-ready execution trajectory for one ActBench task attempt."""

    training_artifact_key = trajectory_artifact_key(
        task=task,
        context=context,
        execution_result=execution_result,
    )
    backend_name = str(execution_result.get("backend") or context.backend or "unknown")
    artifacts = _artifact_refs(
        recorder=recorder,
        training_artifact_key=training_artifact_key,
        backend_name=backend_name,
    )
    role = (
        execution_role
        or execution_result.get("execution_role")
        or (context.metadata or {}).get("execution_role")
        or ("benign_baseline" if (context.metadata or {}).get("baseline") else "attacked_attempt")
    )
    transcript_entries = execution_result.get("transcript") or []
    return {
        "schema_version": TRAJECTORY_SCHEMA_VERSION,
        "trajectory_id": training_artifact_key,
        "role": role,
        "created_at": time.time(),
        "run": _run_payload(context=context, training_artifact_key=training_artifact_key),
        "backend": _backend_payload(
            context=context, execution_result=execution_result, model=model
        ),
        "task": _task_payload(task),
        "execution": _execution_payload(execution_result),
        "transcript": {
            "entries": transcript_entries,
            "entry_count": len(transcript_entries) if isinstance(transcript_entries, list) else 0,
            "source": _transcript_source_payload(execution_result),
        },
        "artifacts": artifacts,
        "scoring_inputs": _scoring_inputs(
            task=task,
            execution_result=execution_result,
            scene_index=scene_index,
            model=model,
            judge_model=judge_model,
            backend_name=backend_name,
            artifacts=artifacts,
            scene_override=scene_override,
            baseline_override=baseline_override,
            execution_role=str(role) if role is not None else None,
        ),
    }


def build_openclaw_trajectory(
    *,
    task: Task,
    execution_result: Dict[str, Any],
    context: BackendRunContext,
    scene_index: Dict[str, Dict[str, Any]],
    model: str,
    judge_model: Optional[str],
    recorder: Optional[TrainingArtifactRecorder] = None,
) -> Dict[str, Any]:
    """Compatibility wrapper for ``build_trajectory``."""

    return build_trajectory(
        task=task,
        execution_result=execution_result,
        context=context,
        scene_index=scene_index,
        model=model,
        judge_model=judge_model,
        recorder=recorder,
    )


def persist_trajectory(
    *,
    recorder: TrainingArtifactRecorder,
    task: Task,
    execution_result: Dict[str, Any],
    context: BackendRunContext,
    scene_index: Dict[str, Dict[str, Any]],
    model: str,
    judge_model: Optional[str],
    scene_override: Optional[Dict[str, Any]] = None,
    baseline_override: Any = _BASELINE_DEFAULT,
    execution_role: Optional[str] = None,
) -> Path:
    """Write one backend trajectory file under runs/<artifact_key>/trajectory.json."""

    training_artifact_key = trajectory_artifact_key(
        task=task,
        context=context,
        execution_result=execution_result,
    )
    execution_result["training_artifact_key"] = training_artifact_key
    trajectory = build_trajectory(
        task=task,
        execution_result=execution_result,
        context=context,
        scene_index=scene_index,
        model=model,
        judge_model=judge_model,
        recorder=recorder,
        scene_override=scene_override,
        baseline_override=baseline_override,
        execution_role=execution_role,
    )
    return recorder.write_json(
        Path("runs") / safe_artifact_name(training_artifact_key) / "trajectory.json",
        trajectory,
    )


def persist_openclaw_trajectory(
    *,
    recorder: TrainingArtifactRecorder,
    task: Task,
    execution_result: Dict[str, Any],
    context: BackendRunContext,
    scene_index: Dict[str, Dict[str, Any]],
    model: str,
    judge_model: Optional[str],
) -> Path:
    """Compatibility wrapper for ``persist_trajectory``."""

    return persist_trajectory(
        recorder=recorder,
        task=task,
        execution_result=execution_result,
        context=context,
        scene_index=scene_index,
        model=model,
        judge_model=judge_model,
    )
