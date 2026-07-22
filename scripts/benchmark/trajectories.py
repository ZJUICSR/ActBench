"""ActBench trajectory artifact construction and persistence."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional

from lib_mock_secrets import materialized_secrets
from lib_reward import ATTACK_SUCCESS_THRESHOLD, REWARD_JUDGE_MODEL
from lib_tasks import Task
from lib_training_artifacts import (
    TrainingArtifactRecorder,
    artifact_file_info,
    atomic_write_json,
    safe_artifact_name,
)

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
from benchmark.task_fingerprint import fingerprint_task_payload
from benchmark.transcript_metrics import transcript_length_metrics

TRAJECTORY_SCHEMA_VERSION = "actbench.trajectory.v1"
OPENCLAW_TRAJECTORY_SCHEMA_VERSION = "actbench.openclaw_trajectory.v1"
CANONICAL_TRAJECTORY_SCHEMA_VERSION = "actbench.canonical_trajectory.v1"
TRAJECTORY_METADATA_SCHEMA_VERSION = "actbench.trajectory_metadata.v1"
TRAJECTORY_INDEX_SCHEMA_VERSION = "actbench.trajectory_index.v1"
SUPPORTED_TRAJECTORY_SCHEMA_VERSIONS = {
    TRAJECTORY_SCHEMA_VERSION,
    OPENCLAW_TRAJECTORY_SCHEMA_VERSION,
}
_BASELINE_DEFAULT = object()
_TRAJECTORY_INDEX_LOCK = threading.RLock()

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
    payload = {
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
    payload.update(fingerprint_task_payload(payload))
    return payload


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
        "attack_pass_condition": "attack_success >= attack_success_threshold",
        "pass_threshold_ags_gte": ATTACK_SUCCESS_THRESHOLD,
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
        risk_type = (
            behavior.scoring_family if behavior is not None else _resolve_task_risk_type(task)
        )
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
    payload["attack_check_code"] = task.automated_checks or scene.get("attack_check_code", "")
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


def _read_json_object(path: Path) -> Dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _run_number_from_context(context: BackendRunContext) -> int:
    metadata = context.metadata or {}
    value = metadata.get("run_number", metadata.get("run_index", 1))
    try:
        run_number = int(value)
    except (TypeError, ValueError):
        run_number = 1
    return max(1, run_number)


def canonical_trajectory_relative_dir(
    *,
    suite: str,
    task_id: str,
    run_number: int,
) -> Path:
    """Return the output-dir-relative canonical directory for one attacked run slot."""

    safe_suite = safe_artifact_name(str(suite or "unknown_suite"))
    safe_task = safe_artifact_name(str(task_id or "unknown_task"))
    safe_run = f"run_{max(1, int(run_number))}"
    return Path("trajectories") / safe_suite / safe_task / "runs" / safe_run


def canonical_trajectory_relative_path(
    *,
    suite: str,
    task_id: str,
    run_number: int,
) -> Path:
    return (
        canonical_trajectory_relative_dir(
            suite=suite,
            task_id=task_id,
            run_number=run_number,
        )
        / "trajectory.json"
    )


def canonical_trajectory_slot_id(
    *,
    suite: str,
    task_id: str,
    run_number: int,
) -> str:
    safe_suite = safe_artifact_name(str(suite or "unknown_suite"))
    safe_task = safe_artifact_name(str(task_id or "unknown_task"))
    return f"{safe_suite}/{safe_task}/run_{max(1, int(run_number))}"


def _canonical_paths(
    *,
    output_dir: Path,
    suite: str,
    task_id: str,
    run_number: int,
) -> Dict[str, Any]:
    relative_path = canonical_trajectory_relative_path(
        suite=suite,
        task_id=task_id,
        run_number=run_number,
    )
    metadata_path = relative_path.parent / "metadata.json"
    slot_id = canonical_trajectory_slot_id(
        suite=suite,
        task_id=task_id,
        run_number=run_number,
    )
    return {
        "slot_id": slot_id,
        "trajectory_path": relative_path,
        "metadata_path": metadata_path,
        "trajectory_absolute": output_dir / relative_path,
        "metadata_absolute": output_dir / metadata_path,
    }


def _canonical_payload(
    *,
    suite: str,
    task: Task,
    context: BackendRunContext,
    role: str,
    paths: Dict[str, Any],
) -> Dict[str, Any]:
    run_number = _run_number_from_context(context)
    return {
        "schema_version": CANONICAL_TRAJECTORY_SCHEMA_VERSION,
        "slot_id": paths["slot_id"],
        "suite": safe_artifact_name(str(suite or "unknown_suite")),
        "requested_suite": (context.metadata or {}).get("suite"),
        "task_id": task.task_id,
        "run_index": run_number,
        "run_number": run_number,
        "role": role,
        "trajectory_path": str(paths["trajectory_path"]),
        "metadata_path": str(paths["metadata_path"]),
        "updated_at": time.time(),
    }


def _attach_canonical_refs(trajectory: Dict[str, Any], canonical: Dict[str, Any]) -> None:
    trajectory["canonical"] = canonical
    artifacts = _as_dict(trajectory.get("artifacts"))
    artifacts["canonical_slot_id"] = canonical["slot_id"]
    artifacts["canonical_trajectory"] = canonical["trajectory_path"]
    artifacts["canonical_metadata"] = canonical["metadata_path"]
    trajectory["artifacts"] = artifacts


def _replacement_metadata(
    *,
    previous_metadata: Dict[str, Any],
    existing_trajectory_path: Path,
) -> Optional[Dict[str, Any]]:
    previous: Dict[str, Any] = {}
    if previous_metadata:
        previous = {
            "previous_sha256": previous_metadata.get("sha256"),
            "previous_size_bytes": previous_metadata.get("size_bytes"),
            "previous_training_artifact_key": previous_metadata.get("training_artifact_key"),
            "previous_attempt_run_id": previous_metadata.get("attempt_run_id"),
            "previous_updated_at": previous_metadata.get("updated_at"),
        }
    elif existing_trajectory_path.exists():
        info = artifact_file_info(existing_trajectory_path)
        previous = {
            "previous_sha256": info.get("sha256"),
            "previous_size_bytes": info.get("size_bytes"),
        }
    previous = {key: value for key, value in previous.items() if value is not None}
    if not previous:
        return None
    previous["replaced_at"] = time.time()
    return previous


def _canonical_metadata_payload(
    *,
    trajectory: Dict[str, Any],
    canonical: Dict[str, Any],
    context: BackendRunContext,
    execution_result: Dict[str, Any],
    recorder: TrainingArtifactRecorder,
    legacy_path: Path,
    legacy_relative_path: Path,
    canonical_path: Path,
    metadata_path: Path,
    file_info: Dict[str, Any],
    previous_metadata: Dict[str, Any],
    replacement: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    run = _as_dict(trajectory.get("run"))
    backend = _as_dict(trajectory.get("backend"))
    execution = _as_dict(trajectory.get("execution"))
    now = time.time()
    metadata: Dict[str, Any] = {
        "schema_version": TRAJECTORY_METADATA_SCHEMA_VERSION,
        "canonical": canonical,
        "slot_id": canonical["slot_id"],
        "suite": canonical.get("suite"),
        "requested_suite": canonical.get("requested_suite"),
        "task_id": canonical.get("task_id"),
        "role": trajectory.get("role"),
        "run_id": run.get("run_id"),
        "attempt_run_id": run.get("attempt_run_id"),
        "run_index": run.get("run_index"),
        "run_number": run.get("run_number"),
        "runs_per_task": run.get("runs_per_task"),
        "run_worker_id": run.get("run_worker_id"),
        "run_worker_label": run.get("run_worker_label"),
        "run_workers": run.get("run_workers"),
        "requested_run_workers": run.get("requested_run_workers"),
        "training_artifact_key": run.get("training_artifact_key")
        or execution.get("training_artifact_key"),
        "backend": backend.get("name") or execution.get("backend"),
        "model": backend.get("model"),
        "status": execution.get("status"),
        "timed_out": execution.get("timed_out"),
        "exit_code": execution.get("exit_code"),
        "execution_time": execution.get("execution_time"),
        "execution_retry": _json_safe(execution_result.get("execution_retry")),
        "retry_history": _json_safe(execution_result.get("retry_history", [])),
        "retry_statuses": list((context.metadata or {}).get("retry_statuses") or []),
        "artifact_root": str(recorder.root),
        "legacy_trajectory_path": str(legacy_relative_path),
        "legacy_trajectory_absolute": str(legacy_path),
        "canonical_trajectory_path": canonical["trajectory_path"],
        "canonical_trajectory_absolute": str(canonical_path),
        "metadata_path": canonical["metadata_path"],
        "metadata_absolute": str(metadata_path),
        "sha256": file_info.get("sha256"),
        "size_bytes": file_info.get("size_bytes"),
        "created_at": previous_metadata.get("created_at", now),
        "updated_at": now,
    }
    if replacement:
        metadata["replacement"] = replacement
    return metadata


def _trajectory_index_entry(metadata: Dict[str, Any]) -> Dict[str, Any]:
    keys = (
        "slot_id",
        "suite",
        "requested_suite",
        "task_id",
        "role",
        "run_id",
        "attempt_run_id",
        "run_index",
        "run_number",
        "runs_per_task",
        "run_worker_id",
        "training_artifact_key",
        "backend",
        "model",
        "status",
        "timed_out",
        "exit_code",
        "execution_time",
        "retry_statuses",
        "legacy_trajectory_path",
        "legacy_trajectory_absolute",
        "canonical_trajectory_path",
        "canonical_trajectory_absolute",
        "metadata_path",
        "metadata_absolute",
        "sha256",
        "size_bytes",
        "created_at",
        "updated_at",
        "scoring",
        "replacement",
    )
    return {key: metadata[key] for key in keys if key in metadata}


def _update_trajectory_index(output_dir: Path, metadata: Dict[str, Any]) -> Path:
    index_path = output_dir / "trajectory_index.json"
    with _TRAJECTORY_INDEX_LOCK:
        index = _read_json_object(index_path)
        if index.get("schema_version") != TRAJECTORY_INDEX_SCHEMA_VERSION:
            index = {
                "schema_version": TRAJECTORY_INDEX_SCHEMA_VERSION,
                "canonical_root": "trajectories",
                "created_at": time.time(),
                "entries": {},
            }
        entries = index.get("entries")
        if not isinstance(entries, dict):
            entries = {}
            index["entries"] = entries
        entries[str(metadata["slot_id"])] = _trajectory_index_entry(metadata)
        index["updated_at"] = time.time()
        index["total_entries"] = len(entries)
        return atomic_write_json(index_path, index)


def _persist_canonical_trajectory(
    *,
    output_dir: Path,
    recorder: TrainingArtifactRecorder,
    trajectory: Dict[str, Any],
    execution_result: Dict[str, Any],
    context: BackendRunContext,
    canonical: Dict[str, Any],
    paths: Dict[str, Any],
    legacy_path: Path,
    legacy_relative_path: Path,
) -> Dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    canonical_path = paths["trajectory_absolute"]
    metadata_path = paths["metadata_absolute"]
    previous_metadata = _read_json_object(metadata_path)
    replacement = _replacement_metadata(
        previous_metadata=previous_metadata,
        existing_trajectory_path=canonical_path,
    )
    atomic_write_json(canonical_path, trajectory)
    info = artifact_file_info(canonical_path)
    metadata = _canonical_metadata_payload(
        trajectory=trajectory,
        canonical=canonical,
        context=context,
        execution_result=execution_result,
        recorder=recorder,
        legacy_path=legacy_path,
        legacy_relative_path=legacy_relative_path,
        canonical_path=canonical_path,
        metadata_path=metadata_path,
        file_info=info,
        previous_metadata=previous_metadata,
        replacement=replacement,
    )
    atomic_write_json(metadata_path, metadata)
    _update_trajectory_index(output_dir, metadata)
    return metadata


def update_canonical_trajectory_scoring_metadata(
    *,
    output_dir: Path,
    execution_result: Dict[str, Any],
    scoring: Dict[str, Any],
) -> Optional[Path]:
    """Update a canonical slot's sidecar/index with post-scoring metadata."""

    trajectory_artifacts = _as_dict(execution_result.get("trajectory_artifacts"))
    metadata_rel = trajectory_artifacts.get("canonical_metadata_path")
    if not metadata_rel:
        return None
    metadata_path = Path(str(metadata_rel))
    if not metadata_path.is_absolute():
        metadata_path = output_dir / metadata_path
    with _TRAJECTORY_INDEX_LOCK:
        metadata = _read_json_object(metadata_path)
        if not metadata:
            return None
        metadata["scoring"] = _json_safe(scoring)
        metadata["updated_at"] = time.time()
        atomic_write_json(metadata_path, metadata)
        return _update_trajectory_index(output_dir, metadata)


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
    transcript_metrics = transcript_length_metrics(transcript_entries)
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
            "entry_count": transcript_metrics["entry_count"],
            "iteration_count": transcript_metrics["iteration_count"],
            "message_count": transcript_metrics["message_count"],
            "message_json_chars": transcript_metrics["message_json_chars"],
            "message_text_chars": transcript_metrics["message_text_chars"],
            "transcript_json_chars": transcript_metrics["transcript_json_chars"],
            "message_role_counts": transcript_metrics["message_role_counts"],
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
    canonical_output_dir: Optional[Path] = None,
    canonical_suite: Optional[str] = None,
    write_canonical: bool = False,
) -> Path:
    """Write one backend trajectory file, optionally mirroring it to a stable slot."""

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
    role = str(trajectory.get("role") or "")
    canonical: Optional[Dict[str, Any]] = None
    canonical_paths: Optional[Dict[str, Any]] = None
    if canonical_output_dir is not None and canonical_suite and role == "attacked_attempt":
        run_number = _run_number_from_context(context)
        canonical_paths = _canonical_paths(
            output_dir=Path(canonical_output_dir),
            suite=canonical_suite,
            task_id=task.task_id,
            run_number=run_number,
        )
        canonical = _canonical_payload(
            suite=canonical_suite,
            task=task,
            context=context,
            role=role,
            paths=canonical_paths,
        )
        _attach_canonical_refs(trajectory, canonical)

    legacy_relative_path = (
        Path("runs") / safe_artifact_name(training_artifact_key) / "trajectory.json"
    )
    legacy_path = recorder.write_json(legacy_relative_path, trajectory)
    trajectory_artifacts = dict(_as_dict(execution_result.get("trajectory_artifacts")))
    trajectory_artifacts.update(
        {
            "legacy_path": str(legacy_relative_path),
            "legacy_absolute": str(legacy_path),
        }
    )
    if canonical is not None:
        trajectory_artifacts.update(
            {
                "canonical_slot_id": canonical.get("slot_id"),
                "canonical_path": canonical.get("trajectory_path"),
                "canonical_metadata_path": canonical.get("metadata_path"),
            }
        )

    if (
        write_canonical
        and canonical is not None
        and canonical_paths is not None
        and canonical_output_dir is not None
    ):
        metadata = _persist_canonical_trajectory(
            output_dir=Path(canonical_output_dir),
            recorder=recorder,
            trajectory=trajectory,
            execution_result=execution_result,
            context=context,
            canonical=canonical,
            paths=canonical_paths,
            legacy_path=legacy_path,
            legacy_relative_path=legacy_relative_path,
        )
        trajectory_artifacts.update(
            {
                "canonical_slot_id": metadata.get("slot_id"),
                "canonical_path": metadata.get("canonical_trajectory_path"),
                "canonical_absolute": metadata.get("canonical_trajectory_absolute"),
                "canonical_metadata_path": metadata.get("metadata_path"),
                "canonical_metadata_absolute": metadata.get("metadata_absolute"),
                "canonical_sha256": metadata.get("sha256"),
                "canonical_size_bytes": metadata.get("size_bytes"),
            }
        )
    execution_result["trajectory_artifacts"] = trajectory_artifacts
    return legacy_path


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
