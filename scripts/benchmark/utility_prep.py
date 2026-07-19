"""Prepare ActBench trajectories for offline utility grading.

This module builds a separate, reference-oriented bundle for future UGS/TAcc
judging. It intentionally does not invoke attack scoring, automated attack
checks, or LLM judges.
"""

from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

from lib_training_artifacts import safe_artifact_name

from benchmark.offline_scoring import (
    collect_trajectory_paths,
    dedupe_trajectory_paths,
    execution_failure_message,
    resolve_replay_workspace,
)
from benchmark.raw_by_task import (
    BASELINE_CACHE_ONLY_REASON,
    RawByTaskError,
    collect_raw_by_task_trajectories,
    raw_by_task_role_from_roles,
    resolve_raw_by_task_datasets,
)
from benchmark.trajectories import SUPPORTED_TRAJECTORY_SCHEMA_VERSIONS
from benchmark.transcript_metrics import transcript_length_metrics

UTILITY_PREP_MANIFEST_SCHEMA_VERSION = "actbench.utility_prep_manifest.v1"
UTILITY_PREP_SUMMARY_SCHEMA_VERSION = "actbench.utility_prep_summary.v1"
UTILITY_INPUT_SCHEMA_VERSION = "actbench.utility_input.v1"
UTILITY_TRANSCRIPT_SCHEMA_VERSION = "actbench.utility_transcript.v1"

DEFAULT_TRANSCRIPT_MODE = "separate"
SUPPORTED_TRANSCRIPT_MODES = ("separate", "inline", "reference")
ROLE_ALL = "all"
ROLE_ALIASES = {
    "all": ROLE_ALL,
    "attacked": "attacked_attempt",
    "attacked_attempt": "attacked_attempt",
    "benign": "benign_baseline",
    "benign_baseline": "benign_baseline",
}

EXCLUDED_DEDUPED = "deduped"
EXCLUDED_INVALID_JSON = "invalid_json"
EXCLUDED_NON_OBJECT_JSON = "non_object_json"
EXCLUDED_UNSUPPORTED_SCHEMA = "unsupported_schema"
EXCLUDED_EXECUTION_FAILURE = "execution_failure"
EXCLUDED_MISSING_WORKSPACE = "missing_workspace"
EXCLUDED_ROLE_FILTER = "role_filter"
EXCLUDED_BACKEND_FILTER = "backend_filter"
EXCLUDED_MODEL_FILTER = "model_filter"
EXCLUDED_TASK_FILTER = "task_filter"
EXCLUDED_SUITE_FILTER = "suite_filter"
EXCLUDED_INSUFFICIENT_TRANSCRIPT = "insufficient_transcript"
EXCLUDED_BASELINE_CACHE_ONLY = BASELINE_CACHE_ONLY_REASON


class UtilityPrepError(ValueError):
    """Raised when utility prep inputs or options are invalid."""


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _string_or_none(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value)
    return text if text else None


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _sha256_file(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json_file(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_trajectory(path: Path | str) -> Dict[str, Any]:
    """Load a trajectory JSON file and require an object payload."""

    loaded = _load_json_file(Path(path))
    if not isinstance(loaded, dict):
        raise UtilityPrepError("trajectory JSON payload is not an object")
    return loaded


def _path_state(path: Path) -> Dict[str, bool]:
    try:
        exists = path.exists()
        is_dir = path.is_dir() if exists else False
        is_file = path.is_file() if exists else False
    except OSError:
        exists = False
        is_dir = False
        is_file = False
    return {"exists": exists, "is_dir": is_dir, "is_file": is_file}


def _infer_artifact_root(trajectory_path: Optional[Path]) -> Optional[Path]:
    if trajectory_path is None:
        return None
    resolved = trajectory_path.resolve()
    if resolved.name == "trajectory.json" and len(resolved.parents) >= 3:
        runs_dir = resolved.parent.parent
        if runs_dir.name == "runs":
            return runs_dir.parent
    return None


def _resolve_possibly_relative_path(
    raw_value: Any,
    *,
    trajectory_path: Optional[Path],
    artifact_root: Optional[Path],
) -> Optional[Path]:
    if not isinstance(raw_value, str) or not raw_value:
        return None
    path = Path(raw_value).expanduser()
    if path.is_absolute():
        return path
    candidates: List[Path] = []
    if artifact_root is not None:
        candidates.append(artifact_root / path)
    inferred_root = _infer_artifact_root(trajectory_path)
    if inferred_root is not None:
        candidates.append(inferred_root / path)
    candidates.append(path)
    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()
    return candidates[0] if candidates else path


def _artifact_root(trajectory: Dict[str, Any], trajectory_path: Optional[Path]) -> Optional[Path]:
    artifacts = _as_dict(trajectory.get("artifacts"))
    root = _resolve_possibly_relative_path(
        artifacts.get("artifact_root"),
        trajectory_path=trajectory_path,
        artifact_root=None,
    )
    if root is not None:
        return root
    return _infer_artifact_root(trajectory_path)


def _trajectory_source_root_key(path: Path, trajectory: Optional[Dict[str, Any]]) -> str:
    if isinstance(trajectory, dict):
        root = _artifact_root(trajectory, path)
        if root is not None:
            return str(root.resolve())
    resolved = path.resolve()
    parts = list(resolved.parts)
    if "trajectories" in parts:
        index = parts.index("trajectories")
        if index > 0:
            return str(Path(*parts[:index]))
    if resolved.name == "trajectory.json" and len(resolved.parents) >= 3:
        runs_dir = resolved.parent.parent
        if runs_dir.name == "runs":
            return str(runs_dir.parent)
    return str(resolved.parent)


def _dedupe_utility_trajectory_paths(paths: Iterable[Path | str]) -> List[Path]:
    """Dedupe canonical/legacy copies without collapsing different result roots."""

    grouped: Dict[str, List[Path]] = {}
    group_order: List[str] = []
    for raw_path in paths:
        path = Path(raw_path)
        trajectory: Optional[Dict[str, Any]] = None
        try:
            loaded = _load_json_file(path)
            if isinstance(loaded, dict):
                trajectory = loaded
        except Exception:
            trajectory = None
        key = _trajectory_source_root_key(path, trajectory)
        if key not in grouped:
            grouped[key] = []
            group_order.append(key)
        grouped[key].append(path)

    deduped: List[Path] = []
    for key in group_order:
        deduped.extend(dedupe_trajectory_paths(grouped[key]))
    return deduped


def _artifact_ref(
    trajectory: Dict[str, Any],
    trajectory_path: Optional[Path],
    key: str,
) -> Dict[str, Any]:
    artifacts = _as_dict(trajectory.get("artifacts"))
    root = _artifact_root(trajectory, trajectory_path)
    raw = artifacts.get(f"{key}_absolute") or artifacts.get(key)
    path = _resolve_possibly_relative_path(raw, trajectory_path=trajectory_path, artifact_root=root)
    if path is None:
        return {"path": "", "source": key, "exists": False, "is_dir": False, "is_file": False}
    state = _path_state(path)
    return {"path": str(path), "source": f"artifacts.{key}", **state}


def _normalize_role(value: Any) -> str:
    text = str(value or "unknown").strip()
    return ROLE_ALIASES.get(text, text)


def _role_from_trajectory(trajectory: Dict[str, Any]) -> str:
    canonical = _as_dict(trajectory.get("canonical"))
    task = _as_dict(trajectory.get("task"))
    return _normalize_role(
        trajectory.get("role") or canonical.get("role") or task.get("role") or "unknown"
    )


def _canonical_slot_id(trajectory: Dict[str, Any]) -> Optional[str]:
    canonical = _as_dict(trajectory.get("canonical"))
    artifacts = _as_dict(trajectory.get("artifacts"))
    return _string_or_none(canonical.get("slot_id") or artifacts.get("canonical_slot_id"))


def _task_id_from_trajectory(trajectory: Dict[str, Any]) -> str:
    task = _as_dict(trajectory.get("task"))
    canonical = _as_dict(trajectory.get("canonical"))
    return str(task.get("task_id") or canonical.get("task_id") or "unknown_task")


def _suite_from_task_id(task_id: str) -> str:
    parts = task_id.split("_")
    if len(parts) >= 2 and parts[0] == "task" and parts[1]:
        return parts[1]
    return "unknown_suite"


def _suite_from_trajectory(trajectory: Dict[str, Any]) -> str:
    canonical = _as_dict(trajectory.get("canonical"))
    run = _as_dict(trajectory.get("run"))
    context_metadata = _as_dict(run.get("context_metadata"))
    task = _as_dict(trajectory.get("task"))
    frontmatter = _as_dict(task.get("frontmatter"))
    task_id = _task_id_from_trajectory(trajectory)
    return str(
        canonical.get("suite")
        or context_metadata.get("suite")
        or frontmatter.get("behavior_id")
        or _suite_from_task_id(task_id)
    )


def _run_number_from_trajectory(trajectory: Dict[str, Any]) -> int:
    canonical = _as_dict(trajectory.get("canonical"))
    run = _as_dict(trajectory.get("run"))
    return max(1, _safe_int(canonical.get("run_number") or run.get("run_number") or run.get("run_index"), 1))


def _fallback_attempt_component(trajectory: Dict[str, Any]) -> str:
    run = _as_dict(trajectory.get("run"))
    execution = _as_dict(trajectory.get("execution"))
    value = (
        trajectory.get("trajectory_id")
        or run.get("training_artifact_key")
        or execution.get("training_artifact_key")
        or run.get("attempt_run_id")
        or "unknown_attempt"
    )
    return f"attempt_{safe_artifact_name(str(value))}"


def _record_id(trajectory: Dict[str, Any]) -> str:
    slot_id = _canonical_slot_id(trajectory)
    if slot_id:
        return slot_id
    suite = safe_artifact_name(_suite_from_trajectory(trajectory))
    task_id = safe_artifact_name(_task_id_from_trajectory(trajectory))
    return (
        f"{suite}/{task_id}/run_{_run_number_from_trajectory(trajectory)}/"
        f"{_fallback_attempt_component(trajectory)}"
    )


def _record_relative_dir(trajectory: Dict[str, Any]) -> Path:
    suite = safe_artifact_name(_suite_from_trajectory(trajectory))
    task_id = safe_artifact_name(_task_id_from_trajectory(trajectory))
    run_number = _run_number_from_trajectory(trajectory)
    path = Path("records") / suite / task_id / "runs" / f"run_{run_number}"
    if not _canonical_slot_id(trajectory):
        path = path / _fallback_attempt_component(trajectory)
    return path


def _backend_name(trajectory: Dict[str, Any]) -> str:
    backend = _as_dict(trajectory.get("backend"))
    execution = _as_dict(trajectory.get("execution"))
    return str(backend.get("name") or execution.get("backend") or "unknown")


def _model_name(trajectory: Dict[str, Any]) -> str:
    backend = _as_dict(trajectory.get("backend"))
    scoring_inputs = _as_dict(trajectory.get("scoring_inputs"))
    return str(backend.get("model") or scoring_inputs.get("target_model") or "unknown")


def _transcript_entries(trajectory: Dict[str, Any]) -> List[Any]:
    transcript = _as_dict(trajectory.get("transcript"))
    return _as_list(transcript.get("entries"))


def _has_inline_api_evidence(trajectory: Dict[str, Any]) -> bool:
    execution = _as_dict(trajectory.get("execution"))
    api_audit = execution.get("api_audit")
    if not isinstance(api_audit, dict) or not api_audit:
        return False
    return any(bool(value) for value in api_audit.values())


def _transcript_sufficient(trajectory: Dict[str, Any]) -> bool:
    entries = _transcript_entries(trajectory)
    if entries:
        return True
    execution = _as_dict(trajectory.get("execution"))
    if str(execution.get("stdout") or "").strip():
        return True
    return _has_inline_api_evidence(trajectory)


def _api_side_effect_summary(api_audit: Any) -> List[Dict[str, Any]]:
    if not isinstance(api_audit, dict):
        return []
    summary: List[Dict[str, Any]] = []
    for service, service_audit in sorted(api_audit.items(), key=lambda item: str(item[0])):
        if not isinstance(service_audit, dict):
            continue
        calls = _as_list(service_audit.get("calls"))
        endpoints = sorted(
            {
                str(call.get("endpoint") or call.get("path"))
                for call in calls
                if isinstance(call, dict) and (call.get("endpoint") or call.get("path"))
            }
        )
        buckets: Dict[str, int] = {}
        for key, value in service_audit.items():
            if key == "calls":
                continue
            if isinstance(value, list):
                buckets[str(key)] = len(value)
            elif isinstance(value, dict):
                buckets[str(key)] = len(value)
        summary.append(
            {
                "service": str(service),
                "call_count": len(calls),
                "endpoints": endpoints,
                "side_effect_buckets": dict(sorted(buckets.items())),
            }
        )
    return summary


def _baseline_ref(trajectory: Dict[str, Any]) -> Dict[str, Any]:
    task = _as_dict(trajectory.get("task"))
    scoring_inputs = _as_dict(trajectory.get("scoring_inputs"))
    baseline = _as_dict(task.get("baseline") or scoring_inputs.get("baseline"))
    baseline_artifacts = _as_dict(baseline.get("artifacts"))
    ref: Dict[str, Any] = {}
    for key in (
        "schema_version",
        "role",
        "scene_id",
        "source_task_id",
        "clean_task_id",
        "target_model",
        "backend",
        "content_hash",
        "status",
        "training_artifact_key",
    ):
        if baseline.get(key) is not None:
            ref[key] = baseline.get(key)
    if task.get("baseline_cache_path") or scoring_inputs.get("baseline_cache_path"):
        ref["cache_path"] = task.get("baseline_cache_path") or scoring_inputs.get("baseline_cache_path")
    if task.get("baseline_artifact_path") or scoring_inputs.get("baseline_artifact_path"):
        ref["artifact_path"] = task.get("baseline_artifact_path") or scoring_inputs.get("baseline_artifact_path")
    if baseline_artifacts:
        ref["artifact_root"] = baseline_artifacts.get("artifact_root")
        ref["run_dir"] = baseline_artifacts.get("run_dir")
        ref["trajectory"] = baseline_artifacts.get("trajectory")
        ref["trajectory_absolute"] = baseline_artifacts.get("trajectory_absolute")
        ref = {key: value for key, value in ref.items() if value is not None}
    return ref


def _source_metadata(path: Path, trajectory: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    trajectory = trajectory or {}
    run = _as_dict(trajectory.get("run"))
    canonical = _as_dict(trajectory.get("canonical"))
    execution = _as_dict(trajectory.get("execution"))
    return {
        "trajectory_path": str(path),
        "trajectory_id": trajectory.get("trajectory_id"),
        "canonical_slot_id": _canonical_slot_id(trajectory),
        "task_id": _task_id_from_trajectory(trajectory) if trajectory else None,
        "suite": _suite_from_trajectory(trajectory) if trajectory else None,
        "role": _role_from_trajectory(trajectory) if trajectory else None,
        "run_number": _run_number_from_trajectory(trajectory) if trajectory else None,
        "run_id": run.get("run_id"),
        "attempt_run_id": run.get("attempt_run_id"),
        "backend": _backend_name(trajectory) if trajectory else None,
        "model": _model_name(trajectory) if trajectory else None,
        "execution_status": execution.get("status"),
        "canonical_trajectory_path": canonical.get("trajectory_path"),
    }


def _exclusion(
    path: Path,
    reason: str,
    *,
    message: Optional[str] = None,
    trajectory: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    item = _source_metadata(path, trajectory)
    item["reason"] = reason
    if message:
        item["message"] = message
    return {key: value for key, value in item.items() if value is not None}


def _normalize_roles(values: Optional[Sequence[str]]) -> List[str]:
    roles = [_normalize_role(value) for value in (values or [ROLE_ALL])]
    return [role for role in roles if role]


def _value_allowed(value: str, filters: Optional[Sequence[str]]) -> bool:
    if not filters:
        return True
    return value in {str(item) for item in filters}


def _role_allowed(role: str, roles: Sequence[str]) -> bool:
    return ROLE_ALL in roles or role in roles


def _task_filter_values(trajectory: Dict[str, Any]) -> set[str]:
    task = _as_dict(trajectory.get("task"))
    frontmatter = _as_dict(task.get("frontmatter"))
    run = _as_dict(trajectory.get("run"))
    context_metadata = _as_dict(run.get("context_metadata"))
    values = {
        _task_id_from_trajectory(trajectory),
        str(trajectory.get("source_task_id") or ""),
        str(task.get("source_task_id") or ""),
        str(context_metadata.get("baseline_task_id") or ""),
        str(frontmatter.get("source_task_id") or ""),
        str(frontmatter.get("id") or ""),
    }
    return {value for value in values if value}


def _task_allowed(trajectory: Dict[str, Any], filters: Optional[Sequence[str]]) -> bool:
    if not filters:
        return True
    allowed = {str(item) for item in filters}
    return bool(_task_filter_values(trajectory) & allowed)


def _passes_filters(
    trajectory: Dict[str, Any],
    *,
    roles: Sequence[str],
    backends: Optional[Sequence[str]],
    models: Optional[Sequence[str]],
    task_ids: Optional[Sequence[str]],
    suites: Optional[Sequence[str]],
) -> Optional[str]:
    if not _role_allowed(_role_from_trajectory(trajectory), roles):
        return EXCLUDED_ROLE_FILTER
    if not _value_allowed(_backend_name(trajectory), backends):
        return EXCLUDED_BACKEND_FILTER
    if not _value_allowed(_model_name(trajectory), models):
        return EXCLUDED_MODEL_FILTER
    if not _task_allowed(trajectory, task_ids):
        return EXCLUDED_TASK_FILTER
    if not _value_allowed(_suite_from_trajectory(trajectory), suites):
        return EXCLUDED_SUITE_FILTER
    return None


def _quality_flags(
    *,
    execution_message: Optional[str],
    workspace: Dict[str, Any],
) -> List[str]:
    flags: List[str] = []
    if execution_message:
        flags.append(EXCLUDED_EXECUTION_FAILURE)
    if not bool(workspace.get("is_dir")):
        flags.append(EXCLUDED_MISSING_WORKSPACE)
    return flags


def _task_payload(trajectory: Dict[str, Any]) -> Dict[str, Any]:
    task = _as_dict(trajectory.get("task"))
    frontmatter = _as_dict(task.get("frontmatter"))
    scoring_inputs = _as_dict(trajectory.get("scoring_inputs"))
    prompt = task.get("prompt") or frontmatter.get("prompt") or scoring_inputs.get("user_prompt")
    return {
        "task_id": task.get("task_id"),
        "name": task.get("name"),
        "category": task.get("category"),
        "grading_type": task.get("grading_type"),
        "timeout_seconds": task.get("timeout_seconds"),
        "prompt": prompt,
        "expected_behavior": task.get("expected_behavior") or frontmatter.get("expected_behavior"),
        "grading_criteria": _as_list(task.get("grading_criteria") or frontmatter.get("grading_criteria")),
        "frontmatter": frontmatter,
        "source_path": task.get("source_path"),
    }


def _execution_payload(trajectory: Dict[str, Any]) -> Dict[str, Any]:
    execution = _as_dict(trajectory.get("execution"))
    return {
        "status": execution.get("status"),
        "exit_code": execution.get("exit_code"),
        "timed_out": execution.get("timed_out"),
        "execution_time": execution.get("execution_time"),
        "stdout": execution.get("stdout"),
        "stderr": execution.get("stderr"),
        "usage": execution.get("usage"),
    }


def _identity_payload(trajectory: Dict[str, Any]) -> Dict[str, Any]:
    run = _as_dict(trajectory.get("run"))
    context_metadata = _as_dict(run.get("context_metadata"))
    task = _as_dict(trajectory.get("task"))
    frontmatter = _as_dict(task.get("frontmatter"))
    task_id = _task_id_from_trajectory(trajectory)
    role = _role_from_trajectory(trajectory)
    source_task_id = _string_or_none(
        trajectory.get("source_task_id")
        or task.get("source_task_id")
        or context_metadata.get("baseline_task_id")
        or frontmatter.get("source_task_id")
        or frontmatter.get("id")
    )
    clean_task_id = _string_or_none(
        trajectory.get("clean_task_id")
        or task.get("clean_task_id")
        or (task_id if role == "benign_baseline" and task_id.endswith("_baseline") else None)
    )
    return {
        "suite": _suite_from_trajectory(trajectory),
        "task_id": task_id,
        "source_task_id": source_task_id,
        "clean_task_id": clean_task_id,
        "comparison_task_id": source_task_id if role == "benign_baseline" and source_task_id else task_id,
        "role": role,
        "run_id": run.get("run_id"),
        "attempt_run_id": run.get("attempt_run_id"),
        "run_index": run.get("run_index"),
        "run_number": _run_number_from_trajectory(trajectory),
        "runs_per_task": run.get("runs_per_task"),
        "run_worker_id": run.get("run_worker_id"),
        "run_worker_label": run.get("run_worker_label"),
        "run_workers": run.get("run_workers"),
        "requested_run_workers": run.get("requested_run_workers"),
        "training_artifact_key": run.get("training_artifact_key"),
    }


def _agent_payload(trajectory: Dict[str, Any]) -> Dict[str, Any]:
    backend = _as_dict(trajectory.get("backend"))
    return {
        "backend": _backend_name(trajectory),
        "model": _model_name(trajectory),
        "agent_id": backend.get("agent_id"),
        "context_agent_id": backend.get("context_agent_id"),
        "backend_metadata": _as_dict(backend.get("backend_metadata")),
    }


def prepare_utility_record(
    trajectory: Dict[str, Any],
    trajectory_path: Path,
    *,
    transcript_mode: str = DEFAULT_TRANSCRIPT_MODE,
) -> Dict[str, Any]:
    """Build one utility-input record and its sidecar transcript payload."""

    entries = _transcript_entries(trajectory)
    metrics = transcript_length_metrics(entries)
    record_rel_dir = _record_relative_dir(trajectory)
    transcript_rel_path = record_rel_dir / "transcript.json"
    workspace = resolve_replay_workspace(trajectory, trajectory_path=trajectory_path)
    api_audit_ref = _artifact_ref(trajectory, trajectory_path, "api_audit")
    api_endpoints_ref = _artifact_ref(trajectory, trajectory_path, "api_endpoints")
    execution = _as_dict(trajectory.get("execution"))
    transcript = _as_dict(trajectory.get("transcript"))
    canonical = _as_dict(trajectory.get("canonical"))
    artifacts = _as_dict(trajectory.get("artifacts"))

    transcript_block: Dict[str, Any] = {
        **metrics,
        "mode": transcript_mode,
        "source": _as_dict(transcript.get("source")),
    }
    if transcript_mode == "separate":
        transcript_block["entries_path"] = "transcript.json"
    elif transcript_mode == "inline":
        transcript_block["entries"] = entries
    else:
        transcript_block["entries_path"] = ""
        transcript_block["source_trajectory_path"] = str(trajectory_path)

    source_sha256 = _sha256_file(trajectory_path)
    record: Dict[str, Any] = {
        "schema_version": UTILITY_INPUT_SCHEMA_VERSION,
        "record_id": _record_id(trajectory),
        "generated_at": time.time(),
        "source": {
            "trajectory_path": str(trajectory_path),
            "trajectory_schema_version": trajectory.get("schema_version"),
            "trajectory_id": trajectory.get("trajectory_id"),
            "trajectory_sha256": source_sha256,
            "canonical_slot_id": _canonical_slot_id(trajectory),
            "canonical_trajectory_path": canonical.get("trajectory_path"),
            "legacy_trajectory_path": artifacts.get("trajectory"),
        },
        "identity": _identity_payload(trajectory),
        "agent": _agent_payload(trajectory),
        "task": _task_payload(trajectory),
        "execution": _execution_payload(trajectory),
        "workspace": workspace,
        "api": {
            "audit_path": api_audit_ref.get("path"),
            "audit_exists": api_audit_ref.get("exists"),
            "endpoints_path": api_endpoints_ref.get("path"),
            "endpoints_exists": api_endpoints_ref.get("exists"),
            "inline_audit_available": isinstance(execution.get("api_audit"), dict),
            "side_effect_summary": _api_side_effect_summary(execution.get("api_audit")),
        },
        "transcript": transcript_block,
        "baseline_ref": _baseline_ref(trajectory),
        "quality_flags": [],
        "future_grading": {
            "intended_uses": ["ugs", "tacc"],
            "requires_agent_rerun": False,
            "prepared_only": True,
        },
    }
    return {
        "record": record,
        "record_relative_path": str(record_rel_dir / "utility_input.json"),
        "transcript_relative_path": str(transcript_rel_path) if transcript_mode == "separate" else "",
        "transcript_entries": entries,
    }


def _manifest_record_entry(record_item: Dict[str, Any]) -> Dict[str, Any]:
    record = record_item["record"]
    source = _as_dict(record.get("source"))
    identity = _as_dict(record.get("identity"))
    agent = _as_dict(record.get("agent"))
    execution = _as_dict(record.get("execution"))
    workspace = _as_dict(record.get("workspace"))
    return {
        "record_id": record.get("record_id"),
        "record_path": record_item.get("record_relative_path"),
        "transcript_path": record_item.get("transcript_relative_path"),
        "source_trajectory_path": source.get("trajectory_path"),
        "source_sha256": source.get("trajectory_sha256"),
        "canonical_slot_id": source.get("canonical_slot_id"),
        "suite": identity.get("suite"),
        "task_id": identity.get("task_id"),
        "source_task_id": identity.get("source_task_id"),
        "clean_task_id": identity.get("clean_task_id"),
        "comparison_task_id": identity.get("comparison_task_id"),
        "run_number": identity.get("run_number"),
        "role": identity.get("role"),
        "backend": agent.get("backend"),
        "model": agent.get("model"),
        "execution_status": execution.get("status"),
        "workspace_exists": workspace.get("exists"),
        "workspace_is_dir": workspace.get("is_dir"),
        "quality_flags": list(record.get("quality_flags") or []),
    }


def _counter_dict(items: Iterable[Any]) -> Dict[str, int]:
    counter = Counter(str(item) for item in items if item is not None)
    return dict(sorted(counter.items()))


def _summary_payload(
    *,
    prepared_items: Sequence[Dict[str, Any]],
    excluded: Sequence[Dict[str, Any]],
    collected_count: int,
    deduped_count: int,
) -> Dict[str, Any]:
    records = [item["record"] for item in prepared_items]
    identities = [_as_dict(record.get("identity")) for record in records]
    agents = [_as_dict(record.get("agent")) for record in records]
    return {
        "schema_version": UTILITY_PREP_SUMMARY_SCHEMA_VERSION,
        "generated_at": time.time(),
        "collected_trajectory_count": collected_count,
        "deduped_trajectory_count": deduped_count,
        "prepared_count": len(prepared_items),
        "excluded_count": len(excluded),
        "counts_by_exclusion_reason": _counter_dict(item.get("reason") for item in excluded),
        "counts_by_role": _counter_dict(identity.get("role") for identity in identities),
        "counts_by_backend": _counter_dict(agent.get("backend") for agent in agents),
        "counts_by_model": _counter_dict(agent.get("model") for agent in agents),
        "attack_scoring_invoked": False,
        "grading_invoked": False,
    }


def prepare_utility_records(
    input_values: Sequence[str],
    *,
    raw_by_task_paths: Optional[Sequence[Path | str]] = None,
    raw_by_task_source: Optional[Dict[str, Any]] = None,
    raw_by_task_excluded: Optional[Sequence[Dict[str, Any]]] = None,
    roles: Optional[Sequence[str]] = None,
    backends: Optional[Sequence[str]] = None,
    models: Optional[Sequence[str]] = None,
    task_ids: Optional[Sequence[str]] = None,
    suites: Optional[Sequence[str]] = None,
    include_failed: bool = False,
    include_missing_workspace: bool = False,
    transcript_mode: str = DEFAULT_TRANSCRIPT_MODE,
) -> Dict[str, Any]:
    """Collect, dedupe, filter, and prepare utility-input records."""

    if transcript_mode not in SUPPORTED_TRANSCRIPT_MODES:
        raise UtilityPrepError(f"Unsupported transcript mode: {transcript_mode}")

    collected = collect_trajectory_paths(list(input_values))
    collected.extend(Path(path).expanduser() for path in (raw_by_task_paths or []))
    deduped = _dedupe_utility_trajectory_paths(collected)
    selected_resolved = {Path(path).resolve() for path in deduped}
    excluded: List[Dict[str, Any]] = [dict(item) for item in (raw_by_task_excluded or [])]
    prepared_items: List[Dict[str, Any]] = []
    normalized_roles = _normalize_roles(roles)

    for path in collected:
        if Path(path).resolve() not in selected_resolved:
            trajectory = None
            try:
                loaded = _load_json_file(Path(path))
                trajectory = loaded if isinstance(loaded, dict) else None
            except Exception:
                pass
            excluded.append(_exclusion(Path(path), EXCLUDED_DEDUPED, trajectory=trajectory))

    for raw_path in deduped:
        path = Path(raw_path)
        try:
            loaded = _load_json_file(path)
        except json.JSONDecodeError as exc:
            excluded.append(_exclusion(path, EXCLUDED_INVALID_JSON, message=str(exc)))
            continue
        except OSError as exc:
            excluded.append(_exclusion(path, EXCLUDED_INVALID_JSON, message=str(exc)))
            continue
        if not isinstance(loaded, dict):
            excluded.append(_exclusion(path, EXCLUDED_NON_OBJECT_JSON))
            continue
        trajectory = loaded
        schema_version = trajectory.get("schema_version")
        if schema_version not in SUPPORTED_TRAJECTORY_SCHEMA_VERSIONS:
            excluded.append(
                _exclusion(
                    path,
                    EXCLUDED_UNSUPPORTED_SCHEMA,
                    message=f"Unsupported trajectory schema: {schema_version!r}",
                    trajectory=trajectory,
                )
            )
            continue
        filter_reason = _passes_filters(
            trajectory,
            roles=normalized_roles,
            backends=backends,
            models=models,
            task_ids=task_ids,
            suites=suites,
        )
        if filter_reason:
            excluded.append(_exclusion(path, filter_reason, trajectory=trajectory))
            continue
        failure = execution_failure_message(trajectory)
        if failure and not include_failed:
            excluded.append(
                _exclusion(path, EXCLUDED_EXECUTION_FAILURE, message=failure, trajectory=trajectory)
            )
            continue
        workspace = resolve_replay_workspace(trajectory, trajectory_path=path)
        if not workspace.get("is_dir") and not include_missing_workspace:
            excluded.append(
                _exclusion(
                    path,
                    EXCLUDED_MISSING_WORKSPACE,
                    message=str(workspace.get("warning") or "Replay workspace is missing."),
                    trajectory=trajectory,
                )
            )
            continue
        if not _transcript_sufficient(trajectory):
            excluded.append(_exclusion(path, EXCLUDED_INSUFFICIENT_TRANSCRIPT, trajectory=trajectory))
            continue

        item = prepare_utility_record(trajectory, path, transcript_mode=transcript_mode)
        item["record"]["quality_flags"] = _quality_flags(
            execution_message=failure,
            workspace=item["record"].get("workspace", {}),
        )
        prepared_items.append(item)

    summary = _summary_payload(
        prepared_items=prepared_items,
        excluded=excluded,
        collected_count=len(collected),
        deduped_count=len(deduped),
    )
    manifest_records = [_manifest_record_entry(item) for item in prepared_items]
    manifest = {
        "schema_version": UTILITY_PREP_MANIFEST_SCHEMA_VERSION,
        "generated_at": time.time(),
        "source": {
            "input_values": list(input_values),
            "collected_trajectory_count": len(collected),
            "deduped_trajectory_count": len(deduped),
            **({"raw_by_task": raw_by_task_source} if raw_by_task_source else {}),
        },
        "filters": {
            "roles": list(normalized_roles),
            "backends": list(backends or []),
            "models": list(models or []),
            "task_ids": list(task_ids or []),
            "suites": list(suites or []),
            "include_failed": include_failed,
            "include_missing_workspace": include_missing_workspace,
            "transcript_mode": transcript_mode,
        },
        "counts": {
            "prepared": len(prepared_items),
            "excluded": len(excluded),
            "by_exclusion_reason": summary["counts_by_exclusion_reason"],
            "by_role": summary["counts_by_role"],
            "by_backend": summary["counts_by_backend"],
            "by_model": summary["counts_by_model"],
        },
        "records": manifest_records,
        "excluded": excluded,
        "attack_scoring_invoked": False,
        "grading_invoked": False,
    }
    return {"summary": summary, "manifest": manifest, "prepared_items": prepared_items}


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_utility_prep_bundle(
    payload: Dict[str, Any],
    output_dir: Path | str,
    *,
    transcript_mode: str = DEFAULT_TRANSCRIPT_MODE,
) -> Dict[str, str]:
    """Write a prepared utility bundle under ``output_dir``."""

    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    summary_path = root / "utility_prep_summary.json"
    manifest_path = root / "utility_prep_manifest.json"
    _write_json(summary_path, payload["summary"])
    _write_json(manifest_path, payload["manifest"])
    for item in payload.get("prepared_items", []):
        record = dict(item["record"])
        record_path = root / item["record_relative_path"]
        _write_json(record_path, record)
        if transcript_mode == "separate" and item.get("transcript_relative_path"):
            transcript_payload = {
                "schema_version": UTILITY_TRANSCRIPT_SCHEMA_VERSION,
                "source_trajectory_path": record.get("source", {}).get("trajectory_path"),
                "record_id": record.get("record_id"),
                "entries": item.get("transcript_entries", []),
            }
            _write_json(root / item["transcript_relative_path"], transcript_payload)
    return {"summary": str(summary_path), "manifest": str(manifest_path)}


def _raw_by_task_requested(args: argparse.Namespace) -> bool:
    return any(
        (
            bool(args.raw_by_task),
            bool(args.raw_by_task_root),
            bool(args.raw_by_task_dataset),
            bool(args.raw_by_task_backend),
            bool(args.raw_by_task_model),
        )
    )


def _collect_raw_by_task_from_args(
    args: argparse.Namespace,
) -> tuple[List[Path], Optional[Dict[str, Any]], List[Dict[str, Any]]]:
    if not _raw_by_task_requested(args):
        return [], None, []
    try:
        datasets = resolve_raw_by_task_datasets(
            raw_by_task_root=args.raw_by_task_root,
            raw_by_task_dataset=args.raw_by_task_dataset,
            backend=args.raw_by_task_backend,
            model=args.raw_by_task_model,
        )
        collection = collect_raw_by_task_trajectories(
            datasets,
            role=raw_by_task_role_from_roles(args.role),
            suites=args.suite,
            task_ids=args.task_id,
        )
    except RawByTaskError as exc:
        raise SystemExit(str(exc)) from exc
    return collection.trajectory_paths, collection.source, collection.excluded


def _parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare ActBench trajectories for separate UGS/TAcc utility grading"
    )
    parser.add_argument(
        "paths",
        nargs="*",
        help="Trajectory files, artifact directories, or glob patterns",
    )
    parser.add_argument(
        "--trajectory",
        action="append",
        default=[],
        help="Trajectory file, artifact directory, or glob pattern. May be repeated.",
    )
    parser.add_argument(
        "--raw-by-task",
        action="store_true",
        help="Consume trajectories from raw_by_task datasets under the configured root.",
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
        help="raw_by_task dataset name or path to prepare. May be repeated.",
    )
    parser.add_argument(
        "--raw-by-task-backend",
        action="append",
        default=None,
        help="Auto-select raw_by_task datasets with this backend. May be repeated.",
    )
    parser.add_argument(
        "--raw-by-task-model",
        action="append",
        default=None,
        help="Auto-select raw_by_task datasets whose target_model matches or contains this value.",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Directory for utility prep outputs. Kept separate from attack scoring outputs.",
    )
    parser.add_argument(
        "--role",
        action="append",
        choices=sorted(ROLE_ALIASES),
        default=None,
        help="Role to include: attacked_attempt, benign_baseline, or all. May be repeated.",
    )
    parser.add_argument("--backend", action="append", default=None, help="Backend filter")
    parser.add_argument("--model", action="append", default=None, help="Model filter")
    parser.add_argument("--task-id", action="append", default=None, help="Task id filter")
    parser.add_argument("--suite", action="append", default=None, help="Suite filter")
    parser.add_argument(
        "--include-failed",
        action="store_true",
        help="Include execution failures with quality flags instead of excluding them.",
    )
    parser.add_argument(
        "--include-missing-workspace",
        action="store_true",
        help="Include records whose durable workspace cannot be resolved.",
    )
    parser.add_argument(
        "--transcript-mode",
        choices=SUPPORTED_TRANSCRIPT_MODES,
        default=DEFAULT_TRANSCRIPT_MODE,
        help="How to store transcript evidence in utility prep records.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Prepare counts and manifest in memory, but do not write output files.",
    )
    parser.add_argument(
        "--compact",
        action="store_true",
        help="Emit compact one-line JSON summary instead of pretty-printed JSON.",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _parse_args(argv)
    input_values = [*args.trajectory, *args.paths]
    raw_paths, raw_source, raw_excluded = _collect_raw_by_task_from_args(args)
    if not input_values and raw_source is None:
        raise SystemExit(
            "Provide at least one --trajectory/positional path or a raw_by_task selector"
        )

    payload = prepare_utility_records(
        input_values,
        raw_by_task_paths=raw_paths,
        raw_by_task_source=raw_source,
        raw_by_task_excluded=raw_excluded,
        roles=args.role,
        backends=args.backend,
        models=args.model,
        task_ids=args.task_id,
        suites=args.suite,
        include_failed=args.include_failed,
        include_missing_workspace=args.include_missing_workspace,
        transcript_mode=args.transcript_mode,
    )
    if not args.dry_run:
        write_utility_prep_bundle(
            payload,
            args.output_dir,
            transcript_mode=args.transcript_mode,
        )
    stdout_payload = {
        **payload["summary"],
        "output_dir": str(Path(args.output_dir)),
        "dry_run": bool(args.dry_run),
    }
    indent = None if args.compact else 2
    print(json.dumps(stdout_payload, indent=indent, sort_keys=True))
    return 0


__all__ = [
    "DEFAULT_TRANSCRIPT_MODE",
    "EXCLUDED_BASELINE_CACHE_ONLY",
    "UTILITY_INPUT_SCHEMA_VERSION",
    "UTILITY_PREP_MANIFEST_SCHEMA_VERSION",
    "UTILITY_PREP_SUMMARY_SCHEMA_VERSION",
    "UtilityPrepError",
    "load_trajectory",
    "main",
    "prepare_utility_record",
    "prepare_utility_records",
    "write_utility_prep_bundle",
]
