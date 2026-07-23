"""Task and scene loading helpers for benchmark runs."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import yaml

from lib_tasks import Task
from lib_taxonomy import (
    TAXONOMY_VERSION_LEGACY,
    behavior_code_for_type,
    behavior_type_for_id,
    infer_behavior_from_metadata,
    legacy_behavior_id_for_type,
    normalize_behavior_type,
    normalize_risk_type,
)
from lib_scene_bundle import load_scene

logger = logging.getLogger("benchmark")

LEGACY_RISK_CODE_TO_TYPE = {
    "R1": "execution_flow_hijack",
    "R2": "unauthorized_execution",
    "R3": "tool_abuse",
    "R4": "privacy_leak",
    "R5": "execution_deception",
    "R6": "resource_exhaustion",
}


@dataclass(frozen=True)
class TaskIndexEntry:
    """Lightweight task metadata used to select suites before loading workspaces."""

    task_id: str
    grading_type: str
    file_path: Path
    frontmatter: Dict[str, Any]


def _read_markdown_frontmatter(path: Path) -> Optional[Dict[str, Any]]:
    try:
        content = path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("Failed to read scene file %s: %s", path, exc)
        return None
    frontmatter_match = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)
    if not frontmatter_match:
        return None
    try:
        metadata = yaml.safe_load(frontmatter_match.group(1))
    except yaml.YAMLError as exc:
        logger.warning("Invalid YAML frontmatter in scene file %s: %s", path, exc)
        return None
    if not isinstance(metadata, dict):
        return None
    metadata["_path"] = str(path)
    return metadata


def _build_scene_index(skill_root: Path) -> Dict[str, Dict[str, Any]]:
    scene_index: Dict[str, Dict[str, Any]] = {}
    scenes_root = skill_root / "scenes"
    if not scenes_root.exists():
        return scene_index
    for scene_file in scenes_root.rglob("scene_*.md"):
        metadata = _read_markdown_frontmatter(scene_file)
        if not metadata:
            continue
        scene_id = metadata.get("id")
        if isinstance(scene_id, str) and scene_id:
            scene_index[scene_id] = metadata
    for scenario_path in sorted(scenes_root.rglob("scenario.yaml")):
        scenario_dir = scenario_path.parent
        try:
            metadata = load_scene(scenario_dir)
        except (OSError, ValueError, yaml.YAMLError) as exc:
            logger.warning("Failed to load directory scenario %s: %s", scenario_dir, exc)
            continue
        scene_id = metadata.get("id")
        if isinstance(scene_id, str) and scene_id:
            scene_index[scene_id] = metadata
    return scene_index


def _read_task_index_entry(task_file: Path) -> TaskIndexEntry:
    try:
        raw_metadata = task_file.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ValueError(f"failed to read task metadata from {task_file}: {exc}") from exc
    try:
        metadata = yaml.safe_load(raw_metadata)
    except yaml.YAMLError as exc:
        raise ValueError(f"invalid YAML in task metadata {task_file}: {exc}") from exc
    if not isinstance(metadata, dict):
        raise ValueError(f"task metadata must be a mapping: {task_file}")
    return TaskIndexEntry(
        task_id=str(metadata.get("id") or ""),
        grading_type=str(metadata.get("grading_type") or "automated"),
        file_path=task_file,
        frontmatter=metadata,
    )


def _build_task_index(tasks_dir: Path) -> List[TaskIndexEntry]:
    task_files = sorted(tasks_dir.glob("task_*/task.yaml"))
    logger.info("Found %d task files", len(task_files))
    return [_read_task_index_entry(task_file) for task_file in task_files]


def _behavior_suite_matches(tasks: Sequence[Task | TaskIndexEntry], token: str) -> List[str]:
    token_text = token.strip()
    token_lower = token_text.lower()
    legacy_prefixes = ("old:", "legacy:", "v1:")
    try:
        if token_lower.startswith(legacy_prefixes):
            _, raw_legacy_id = token_text.split(":", 1)
            token_behavior = behavior_type_for_id(
                raw_legacy_id,
                taxonomy_version=TAXONOMY_VERSION_LEGACY,
            )
        else:
            token_behavior = normalize_behavior_type(token_text)
    except ValueError:
        return []
    token_code = behavior_code_for_type(token_behavior)
    matched: List[str] = []
    for task in tasks:
        try:
            inference = infer_behavior_from_metadata(task.frontmatter or {}, path=task.file_path)
        except ValueError:
            continue
        if inference.behavior_type == token_behavior or inference.behavior_id == token_code:
            matched.append(task.task_id)
    return matched


def _task_alias_ids(
    task: Task | TaskIndexEntry,
    *,
    include_legacy_behavior_aliases: bool = False,
) -> List[str]:
    aliases: List[str] = []
    fm = task.frontmatter or {}
    value = fm.get("legacy_task_id")
    if value:
        aliases.append(str(value))

    if include_legacy_behavior_aliases:
        value = fm.get("legacy_behavior_task_id")
        if value:
            aliases.append(str(value))

        match = re.match(r"^task_B(?:[1-9]|1[0-5])_T(\d+)$", task.task_id)
        if match:
            try:
                inference = infer_behavior_from_metadata(fm, path=task.file_path)
                legacy_behavior_id = legacy_behavior_id_for_type(inference.behavior_type)
                aliases.append(f"task_{legacy_behavior_id}_T{match.group(1)}")
            except ValueError:
                pass

    unique: List[str] = []
    seen: set[str] = set()
    for alias in aliases:
        key = alias.lower()
        if key in seen or key == task.task_id.lower():
            continue
        seen.add(key)
        unique.append(alias)
    return unique


def _legacy_task_id(task: Task | TaskIndexEntry) -> str | None:
    aliases = _task_alias_ids(task)
    return aliases[0] if aliases else None


def _build_legacy_task_id_map(
    tasks: Sequence[Task | TaskIndexEntry],
    *,
    include_legacy_behavior_aliases: bool = False,
) -> Dict[str, str]:
    legacy_task_ids: Dict[str, str] = {}
    for task in tasks:
        for legacy_task_id in _task_alias_ids(
            task,
            include_legacy_behavior_aliases=include_legacy_behavior_aliases,
        ):
            key = legacy_task_id.lower()
            if key in legacy_task_ids:
                logger.warning(
                    "Duplicate legacy_task_id %s maps to both %s and %s; keeping %s",
                    legacy_task_id,
                    legacy_task_ids[key],
                    task.task_id,
                    legacy_task_ids[key],
                )
                continue
            legacy_task_ids[key] = task.task_id
    return legacy_task_ids


def _legacy_risk_suite_matches(tasks: Sequence[Task | TaskIndexEntry], token: str) -> List[str]:
    normalized_token = token.strip().upper()
    risk_type = LEGACY_RISK_CODE_TO_TYPE.get(normalized_token)
    if risk_type is None:
        try:
            risk_type = normalize_risk_type(token)
        except ValueError:
            return []
    matched: List[str] = []
    for task in tasks:
        fm = task.frontmatter or {}
        task_risk = fm.get("legacy_risk_type") or fm.get("risk_type") or fm.get("risk")
        try:
            if normalize_risk_type(task_risk) == risk_type:
                matched.append(task.task_id)
        except ValueError:
            continue
    return matched


def _task_prefix_matches(
    tasks: Sequence[Task | TaskIndexEntry],
    token: str,
    *,
    include_legacy_behavior_aliases: bool = False,
    include_current_ids: bool = True,
) -> List[str]:
    token = token.strip().lower()
    prefixes = [f"task_{token}_"]
    if token.startswith("task_"):
        prefixes.append(f"{token}_")
    matched: List[str] = []
    seen: set[str] = set()
    for task in tasks:
        task_ids = [task.task_id.lower()] if include_current_ids else []
        task_ids.extend(
            alias.lower()
            for alias in _task_alias_ids(
                task,
                include_legacy_behavior_aliases=include_legacy_behavior_aliases,
            )
        )
        if any(any(task_id.startswith(prefix) for prefix in prefixes) for task_id in task_ids):
            if task.task_id not in seen:
                matched.append(task.task_id)
                seen.add(task.task_id)
    return matched


def _select_task_ids(tasks: Sequence[Task | TaskIndexEntry], suite: str) -> Optional[List[str]]:
    if suite == "all":
        return None
    if suite == "automated-only":
        return [task.task_id for task in tasks if task.grading_type == "automated"]
    all_task_ids = {task.task_id.lower(): task.task_id for task in tasks}
    include_legacy_behavior_aliases = bool(re.search(r"(?:^|,)\s*(?:old|legacy|v1):", suite, re.IGNORECASE))
    legacy_task_ids = _build_legacy_task_id_map(
        tasks,
        include_legacy_behavior_aliases=include_legacy_behavior_aliases,
    )
    selected: List[str] = []
    for token in suite.split(","):
        token = token.strip()
        if not token:
            continue
        token_key = token.lower()
        legacy_behavior_token = None
        if re.match(r"^(?:old|legacy|v1):", token, re.IGNORECASE):
            legacy_behavior_token = token.split(":", 1)[1].strip()
        if token_key in all_task_ids:
            selected.append(all_task_ids[token_key])
            continue
        if token_key in legacy_task_ids:
            selected.append(legacy_task_ids[token_key])
            continue
        if legacy_behavior_token:
            legacy_behavior_key = legacy_behavior_token.lower()
            if legacy_behavior_key in legacy_task_ids:
                selected.append(legacy_task_ids[legacy_behavior_key])
                continue
        legacy_risk_matched = _legacy_risk_suite_matches(tasks, token)
        if legacy_risk_matched:
            selected.extend(legacy_risk_matched)
            continue
        behavior_matched = _behavior_suite_matches(tasks, token)
        if behavior_matched:
            selected.extend(behavior_matched)
            continue
        prefix_matched = _task_prefix_matches(tasks, token)
        if not prefix_matched and legacy_behavior_token:
            prefix_matched = _task_prefix_matches(
                tasks,
                legacy_behavior_token,
                include_legacy_behavior_aliases=True,
                include_current_ids=False,
            )
        if prefix_matched:
            selected.extend(prefix_matched)
        else:
            # Fall back to exact token so the suite resolver can report the miss.
            selected.append(token)
    return selected


def _unique_preserving_order(values: Sequence[str]) -> List[str]:
    seen: set[str] = set()
    unique: List[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        unique.append(value)
    return unique


def _direct_task_files_for_exact_ids(tasks_dir: Path, suite: str) -> Optional[List[Path]]:
    tokens = [token.strip().lower() for token in suite.split(",") if token.strip()]
    if not tokens:
        return []
    if not all(token.startswith("task_") for token in tokens):
        return None
    task_files = sorted(tasks_dir.glob("task_*/task.yaml"))
    files_by_dir_id = {task_file.parent.name.lower(): task_file for task_file in task_files}
    if not all(token in files_by_dir_id for token in tokens):
        return None
    selected: set[Path] = set()
    for token in tokens:
        task_file = files_by_dir_id[token]
        entry = _read_task_index_entry(task_file)
        alias_ids = {alias.lower() for alias in _task_alias_ids(entry)}
        if entry.task_id.lower() != token and token not in alias_ids:
            raise ValueError(
                f"task directory {task_file.parent} declares id {entry.task_id!r}, not {token!r}"
            )
        selected.add(task_file)
    return [task_file for task_file in task_files if task_file in selected]


def select_task_files_for_suite(tasks_dir: Path, suite: str) -> List[Path]:
    """Resolve a suite selector to task.yaml files without loading task workspaces.

    This keeps targeted benchmark runs from reading every workspace/grader just to
    run one task, while preserving the historical suite selector semantics.
    """

    direct_task_files = _direct_task_files_for_exact_ids(tasks_dir, suite)
    if direct_task_files is not None:
        logger.info("Suite %r selected %d exact task id(s)", suite, len(direct_task_files))
        return direct_task_files

    index = _build_task_index(tasks_dir)
    task_ids = _select_task_ids(index, suite)
    if task_ids is None:
        logger.info("Suite %r selected all %d tasks", suite, len(index))
        return [entry.file_path for entry in index]

    requested_ids = _unique_preserving_order(task_ids)
    entries_by_id = {entry.task_id: entry for entry in index}
    missing_ids = [task_id for task_id in requested_ids if task_id not in entries_by_id]
    if missing_ids:
        known_hint = ", ".join(entry.task_id for entry in index[:5])
        if len(index) > 5:
            known_hint += ", ..."
        raise ValueError(
            f"Suite {suite!r} referenced unknown task selector(s): {', '.join(missing_ids)}. "
            f"Known task examples: {known_hint or '(none)'}"
        )

    selected_id_set = set(requested_ids)
    selected = [entry.file_path for entry in index if entry.task_id in selected_id_set]
    logger.info("Suite %r selected %d/%d tasks", suite, len(selected), len(index))
    return selected
