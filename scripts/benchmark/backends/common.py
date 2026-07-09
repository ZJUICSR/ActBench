"""Shared helpers for non-OpenClaw ActBench backend adapters."""

from __future__ import annotations

import json
import logging
import shutil
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

from lib_api_services import (
    SERVICE_SPECS,
    get_declared_mock_services,
    get_fixture_overrides,
    start_api_services,
)
from lib_api_skill_install import install_mock_api_skills
from lib_mock_secrets import materialize_workspace_file
from lib_tasks import Task
from lib_training_artifacts import get_current_recorder, safe_artifact_name

from benchmark.backends.base import BackendRunContext

logger = logging.getLogger(__name__)

BOOTSTRAP_FILES = ("BOOTSTRAP.md", "SOUL.md", "USER.md", "IDENTITY.md")


def safe_path_component(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in ("-", "_", ".") else "_" for ch in str(value))


def backend_task_workspace(
    *,
    context: BackendRunContext,
    attempt_run_id: str,
    task: Task,
) -> Path:
    """Return the isolated workspace path used by non-OpenClaw backends."""

    return (
        context.run_root
        / safe_path_component(attempt_run_id)
        / safe_path_component(context.backend)
        / safe_path_component(task.task_id)
        / "workspace"
    )


def session_prompts(task: Task) -> List[str]:
    """Return prompts to send to an agent, preserving multi-session task order."""

    sessions = (task.frontmatter or {}).get("sessions", []) or []
    prompts: List[str] = []
    for session_entry in sessions:
        if isinstance(session_entry, str):
            if session_entry:
                prompts.append(session_entry)
        elif isinstance(session_entry, dict):
            text = session_entry.get("prompt") or session_entry.get("message", "")
            if text:
                prompts.append(str(text))
        else:
            logger.warning("Skipping invalid session entry for %s: %s", task.task_id, session_entry)
    return prompts or [task.prompt]


def materialize_task_workspace(
    *,
    workspace: Path,
    skill_dir: Path,
    task: Task,
    install_api_skills: bool = True,
) -> Path:
    """Materialize task files into an explicit workspace for backend adapters."""

    if workspace.exists():
        shutil.rmtree(workspace)
    workspace.mkdir(parents=True, exist_ok=True)
    resolved_workspace = workspace.resolve()

    for file_spec in task.workspace_files:
        if "content" in file_spec:
            dest = (workspace / file_spec["path"]).resolve()
            if not dest.is_relative_to(resolved_workspace):
                raise ValueError(f"Workspace path escapes sandbox: {file_spec['path']}")
            dest.parent.mkdir(parents=True, exist_ok=True)
            content = materialize_workspace_file(file_spec, task.frontmatter, task.workspace_files)
            dest.write_text(content, encoding="utf-8")
            if dest.suffix == ".sh":
                dest.chmod(dest.stat().st_mode | 0o111)
            continue

        source = skill_dir / "assets" / file_spec["source"]
        dest = (workspace / file_spec["dest"]).resolve()
        if not dest.is_relative_to(resolved_workspace):
            raise ValueError(f"Workspace path escapes sandbox: {file_spec['dest']}")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(source.read_bytes())

    for bootstrap_file in BOOTSTRAP_FILES:
        bootstrap_path = workspace / bootstrap_file
        if bootstrap_path.exists():
            try:
                bootstrap_path.unlink()
                logger.info("Removed bootstrap file: %s", bootstrap_file)
            except OSError as exc:
                logger.warning("Failed to remove %s: %s", bootstrap_file, exc)

    if install_api_skills:
        mock_services = get_declared_mock_services(task.frontmatter)
        if mock_services:
            install_mock_api_skills(workspace, mock_services)

    return workspace


def enable_workspace_skills_manifest(workspace: Path) -> None:
    """Enable every workspace skill in a qwenpaw-compatible skill manifest."""

    skills_root = workspace / "skills"
    manifest_path = workspace / "skill.json"
    entries: Dict[str, Any] = {}
    if manifest_path.exists():
        try:
            existing = json.loads(manifest_path.read_text(encoding="utf-8"))
            if isinstance(existing, dict) and isinstance(existing.get("skills"), dict):
                entries = dict(existing["skills"])
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Ignoring malformed workspace skill.json: %s", exc)

    if skills_root.is_dir():
        for entry in sorted(skills_root.iterdir()):
            if entry.is_dir() and (entry / "SKILL.md").exists():
                entries[entry.name] = {
                    "enabled": True,
                    "channels": ["all"],
                    "source": "actbench",
                }

    manifest = {
        "schema_version": "workspace-skill-manifest.v1",
        "version": 1,
        "skills": entries,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")


def artifact_fixture_paths(config: Dict[str, Any]) -> Dict[str, Path]:
    overrides = get_fixture_overrides(config)
    paths: Dict[str, Path] = {}
    for service in get_declared_mock_services(config):
        spec = SERVICE_SPECS.get(service)
        paths[service] = overrides.get(service) or (spec.fixture_path if spec else Path(""))
    return paths


def begin_task_artifacts(
    *,
    context: BackendRunContext,
    task: Task,
    attempt_run_id: str,
    session_id: str,
    workspace: Path,
) -> Tuple[str, Any]:
    """Write common task-start artifacts and return (artifact_key, recorder)."""

    artifact_key = safe_artifact_name(f"{task.task_id}_{session_id}")
    recorder = get_current_recorder()
    if recorder:
        recorder.write_json(
            Path("runs") / artifact_key / "task.json",
            {
                "task_id": task.task_id,
                "name": task.name,
                "category": task.category,
                "prompt": task.prompt,
                "frontmatter": task.frontmatter,
                "workspace_files": task.workspace_files,
                "model_id": context.model,
                "agent_id": context.agent_id,
                "run_id": attempt_run_id,
                "session_id": session_id,
                "backend": context.backend,
            },
        )
        recorder.snapshot_directory(workspace, Path("runs") / artifact_key / "workspace_before")
    return artifact_key, recorder


def finish_task_artifacts(
    *,
    recorder: Any,
    artifact_key: str,
    task: Task,
    workspace: Path,
    api_endpoints: Dict[str, Any],
    api_audit: Dict[str, Any],
) -> None:
    """Write common task-end artifacts if a recorder is active."""

    if not recorder:
        return
    recorder.record_api_context(
        run_key=artifact_key,
        api_endpoints=api_endpoints,
        api_audit=api_audit,
        fixture_overrides=artifact_fixture_paths(task.frontmatter),
    )
    recorder.snapshot_directory(workspace, Path("runs") / artifact_key / "workspace_after")


def stdout_transcript_fallback(prompt: str, stdout: str) -> List[Dict[str, Any]]:
    if not stdout.strip():
        return []
    return [
        {"type": "message", "message": {"role": "user", "content": [prompt]}},
        {
            "type": "message",
            "message": {
                "role": "assistant",
                "content": [{"type": "text", "text": stdout.strip()}],
            },
        },
    ]


def zero_usage(request_count: int = 0) -> Dict[str, Any]:
    return {
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_read_tokens": 0,
        "cache_write_tokens": 0,
        "total_tokens": 0,
        "cost_usd": 0.0,
        "request_count": request_count,
    }


def execution_error_result(
    *,
    context: BackendRunContext,
    task: Task,
    workspace: str | Path = "",
    stderr: str,
    execution_time: float = 0.0,
    api_endpoints: Dict[str, Any] | None = None,
    training_artifact_key: str | None = None,
) -> Dict[str, Any]:
    return {
        "agent_id": context.agent_id,
        "task_id": task.task_id,
        "status": "error",
        "transcript": [],
        "usage": {},
        "workspace": str(workspace) if workspace else "",
        "exit_code": -1,
        "timed_out": False,
        "execution_time": execution_time,
        "stdout": "",
        "stderr": stderr,
        "api_audit": {},
        "api_endpoints": api_endpoints or {},
        "training_artifact_key": training_artifact_key,
        "backend": context.backend,
        "backend_metadata": {
            "name": context.backend,
            "model": context.model,
            "agent_id": context.agent_id,
        },
    }


def start_declared_api_services(
    *,
    task: Task,
    attempt_run_id: str,
    workspace: Path,
):
    """Start services declared by a task and return (group, endpoints)."""

    mock_services = get_declared_mock_services(task.frontmatter)
    if not mock_services:
        return None, {}
    group = start_api_services(
        services=mock_services,
        run_id=attempt_run_id,
        attempt_id=task.task_id,
        fixture_overrides=get_fixture_overrides(task.frontmatter),
        workspace=workspace,
    )
    endpoints = group.endpoints if group else {}
    return group, endpoints


def elapsed_since(start_time: float) -> float:
    return time.time() - start_time
