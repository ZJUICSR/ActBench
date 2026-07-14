"""Shared helpers for ActBench per-run artifact paths and writes."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from lib_training_artifacts import TrainingArtifactRecorder, safe_artifact_name


def artifact_run_dir(training_artifact_key: str) -> Path:
    """Return the recorder-relative run directory for one execution artifact key."""

    return Path("runs") / safe_artifact_name(str(training_artifact_key))


def build_artifact_refs(
    *,
    training_artifact_key: str,
    recorder: Optional[TrainingArtifactRecorder] = None,
    backend_name: Optional[str] = None,
) -> Dict[str, Any]:
    """Return the standard artifact reference map for one ActBench execution."""

    run_dir = artifact_run_dir(training_artifact_key)
    refs: Dict[str, Any] = {
        "run_dir": str(run_dir),
        "task": str(run_dir / "task.json"),
        "agent_execution": str(run_dir / "agent_execution.json"),
        "backend_execution": str(run_dir / "agent_execution.json"),
        "evaluation": str(run_dir / "evaluation.json"),
        "baseline": str(run_dir / "baseline.json"),
        "workspace_before": str(run_dir / "workspace_before"),
        "workspace_before_manifest": str(run_dir / "workspace_before" / "files_manifest.json"),
        "workspace_after": str(run_dir / "workspace_after"),
        "workspace_after_manifest": str(run_dir / "workspace_after" / "files_manifest.json"),
        "api_endpoints": str(run_dir / "api" / "endpoints.json"),
        "api_audit": str(run_dir / "api" / "audit.json"),
        "api_fixture_overrides": str(run_dir / "api" / "fixture_overrides.json"),
        "api_fixtures_dir": str(run_dir / "api" / "fixtures"),
        "api_logs_dir": str(run_dir / "api" / "logs"),
        "trajectory": str(run_dir / "trajectory.json"),
    }
    if backend_name == "openclaw":
        refs["openclaw_execution"] = str(run_dir / "openclaw_execution.json")
    if recorder is not None:
        root = recorder.root
        refs["artifact_root"] = str(root)
        refs["run_dir_absolute"] = str(root / run_dir)
        refs["workspace_after_absolute"] = str(root / run_dir / "workspace_after")
        refs["workspace_before_absolute"] = str(root / run_dir / "workspace_before")
        refs["trajectory_absolute"] = str(root / run_dir / "trajectory.json")
    return refs


def write_execution_artifacts(
    *,
    recorder: TrainingArtifactRecorder,
    backend_name: str,
    training_artifact_key: str,
    execution_result: Dict[str, Any],
    evaluation_payload: Dict[str, Any],
    baseline_payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Write standard per-run execution artifacts and return their refs."""

    run_dir = artifact_run_dir(training_artifact_key)
    refs = build_artifact_refs(
        training_artifact_key=training_artifact_key,
        recorder=recorder,
        backend_name=backend_name,
    )
    execution_result["training_artifact_key"] = safe_artifact_name(str(training_artifact_key))
    recorder.write_json(run_dir / "agent_execution.json", execution_result)
    if backend_name == "openclaw":
        recorder.write_json(run_dir / "openclaw_execution.json", execution_result)
    recorder.write_json(run_dir / "evaluation.json", evaluation_payload)
    if baseline_payload is not None:
        baseline_payload["artifacts"] = refs
        recorder.write_json(run_dir / "baseline.json", baseline_payload)
    return refs
