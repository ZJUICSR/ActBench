"""Attack evaluation helpers for benchmark task runs."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from lib_mock_secrets import materialized_secrets
from lib_reward import REWARD_JUDGE_MODEL, RewardResult, evaluate_attack
from lib_tasks import Task
from lib_taxonomy import BehaviorInference, infer_behavior_from_metadata, normalize_risk_type

from benchmark.baseline import _load_baseline_for_task, _load_clean_source_scene_for_task
from benchmark.scoring_guides import RISK_GUIDES

logger = logging.getLogger("benchmark")


def _normalize_file_content(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    return json.dumps(content, indent=2, ensure_ascii=False)


def _derive_attack_payload(task: Task, scene: Optional[Dict[str, Any]]) -> Dict[str, str]:
    # Preferred path: use the explicit attack_payload_paths list embedded in
    # public task metadata. This is accurate even when scene files are unavailable.
    payload_paths = (task.frontmatter or {}).get("attack_payload_paths")
    if isinstance(payload_paths, list) and payload_paths:
        task_files: Dict[str, str] = {
            file_spec["path"]: _normalize_file_content(file_spec.get("content", ""))
            for file_spec in task.workspace_files
            if isinstance(file_spec.get("path"), str) and file_spec["path"]
        }
        return {p: task_files[p] for p in payload_paths if p in task_files}

    # Fallback: diff task workspace against scene's original workspace.
    # Less accurate when scene files are absent (scene workspace_files=[]).
    scene_files: Dict[str, str] = {}
    for file_spec in (scene or {}).get("workspace_files", []) or []:
        if not isinstance(file_spec, dict):
            continue
        path = file_spec.get("path")
        if not isinstance(path, str) or not path:
            continue
        scene_files[path] = _normalize_file_content(file_spec.get("content", ""))

    attack_payload: Dict[str, str] = {}
    for file_spec in task.workspace_files:
        path = file_spec.get("path")
        if not isinstance(path, str) or not path or "content" not in file_spec:
            continue
        content = _normalize_file_content(file_spec.get("content", ""))
        if scene_files.get(path) != content:
            attack_payload[path] = content
    return attack_payload


def _extract_malicious_skill_names(task: Task, attack_payload: Dict[str, str]) -> List[str]:
    # Prefer explicit field from task frontmatter (single source of truth for
    # public scoring metadata).
    fm_names = task.frontmatter.get("malicious_skill_names")
    if isinstance(fm_names, list):
        return [str(n) for n in fm_names if n]
    # Legacy fallback: infer from file paths containing skills/<name>/
    skill_names = set()
    candidate_paths = list(attack_payload.keys())
    for file_spec in task.workspace_files:
        path = file_spec.get("path")
        if isinstance(path, str):
            candidate_paths.append(path)
    for rel_path in candidate_paths:
        parts = Path(rel_path).parts
        for idx, part in enumerate(parts):
            if part == "skills" and idx + 1 < len(parts):
                skill_names.add(parts[idx + 1])
    return sorted(skill_names)


def _resolve_task_risk_type(task: Task) -> Optional[str]:
    """Return the canonical risk type for a task, accepting legacy metadata aliases."""
    fm = task.frontmatter or {}
    candidates: List[object] = []
    if fm.get("risk_type"):
        candidates.append(fm.get("risk_type"))
    risk_label = fm.get("risk")
    if isinstance(risk_label, str) and "_" in risk_label:
        # Generated tasks use labels such as R4_privacy_leak. Strip only the Rn_
        # prefix so risk names that contain underscores remain intact.
        candidates.append(risk_label.split("_", 1)[1])
    if task.category:
        candidates.append(task.category)

    for candidate in candidates:
        try:
            return normalize_risk_type(candidate)
        except ValueError:
            continue
    return None


def _resolve_task_behavior(task: Task) -> Optional[BehaviorInference]:
    """Return canonical behavior metadata, inferring from legacy risk fields if needed."""
    fm = task.frontmatter or {}
    if not isinstance(fm, dict):
        return None
    inference = infer_behavior_from_metadata(fm, path=task.file_path)
    if inference.needs_manual_review:
        logger.warning(
            "Behavior inference for task %s needs manual review: %s (%s)",
            task.task_id,
            inference.behavior_id,
            inference.reason,
        )
    return inference


def _resolve_task_scenario(task: Task) -> Optional[str]:
    """Return the source scenario id from current or legacy task metadata."""
    fm = task.frontmatter or {}
    for key in ("scenario", "scene_id", "source_scene_id", "scenario_id"):
        value = fm.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _evaluate_attack_for_task(
    *,
    task: Task,
    execution_result: Dict[str, Any],
    scene_index: Dict[str, Dict[str, Any]],
    model: str,
    judge_model: Optional[str],
    verbose: bool,
    backend_name: str = "openclaw",
) -> Optional[RewardResult]:
    scenario = _resolve_task_scenario(task)
    if not scenario:
        return None

    behavior = _resolve_task_behavior(task)
    if not behavior:
        logger.warning(
            "No behavior/risk mapping for task %s (behavior_type=%r risk_type=%r risk=%r category=%r)",
            task.task_id,
            task.frontmatter.get("behavior_type"),
            task.frontmatter.get("risk_type"),
            task.frontmatter.get("risk"),
            task.category,
        )
        return None
    risk_type = behavior.legacy_risk_type

    scene = _load_clean_source_scene_for_task(task) or scene_index.get(scenario)
    if not scene:
        logger.warning(
            "No source scene found for %s (%s); falling back to task frontmatter metadata",
            task.task_id,
            scenario,
        )
        # Build a minimal scene dict from metadata embedded in the task.
        # This keeps scoring functional when scene files have been deleted or
        # moved after tasks were generated.
        fm = task.frontmatter
        scene = {
            "risk_goal": fm.get("risk_goal") or fm.get("attack_goal", ""),
            "user_prompt": fm.get("user_prompt", task.prompt),
            "attack_check_code": fm.get("attack_check_code", ""),
            "secrets": fm.get("secrets"),
            "workspace_files": [],
        }

    risk_guide = RISK_GUIDES.get(risk_type, {})
    reward_criteria = risk_guide.get("reward_criteria", {})
    attack_goal = scene.get("risk_goal") or task.frontmatter.get(
        "attack_goal", task.expected_behavior or task.prompt
    )
    if not isinstance(attack_goal, str):
        attack_goal = str(attack_goal)

    attack_payload = _derive_attack_payload(task, scene)
    malicious_skill_names = _extract_malicious_skill_names(task, attack_payload)
    baseline = _load_baseline_for_task(task, model, scene=scene, backend_name=backend_name)

    try:
        return evaluate_attack(
            behavior_type=behavior.behavior_type,
            scoring_family=behavior.scoring_family,
            risk_type=risk_type,
            attack_goal=attack_goal,
            attack_payload=attack_payload,
            transcript=execution_result.get("transcript", []),
            workspace_path=execution_result.get("workspace", ""),
            reward_criteria=reward_criteria,
            user_prompt=scene.get("user_prompt", ""),
            attack_check_code=task.automated_checks or scene.get("attack_check_code", ""),
            malicious_skill_names=malicious_skill_names or None,
            judge_model=judge_model or REWARD_JUDGE_MODEL,
            baseline=baseline,
            secrets=materialized_secrets(scene, scene.get("workspace_files", [])),
            execution_feedback=execution_result,
            verbose=verbose,
        )
    except Exception as exc:
        logger.warning("Attack evaluation failed for %s: %s", task.task_id, exc)
        return None
