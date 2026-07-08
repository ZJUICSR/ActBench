"""
ClawEval Task Library

This module provides task loading and parsing functionality for the ClawEval
benchmarking system.
"""

import logging
from pathlib import Path
from typing import Dict, List, Optional, Any

import yaml

from lib_safe_paths import safe_join

logger = logging.getLogger(__name__)


class Task:
    """Represents a single benchmark task."""

    def __init__(
        self,
        task_id: str,
        name: str,
        category: str,
        grading_type: str,
        timeout_seconds: int,
        workspace_files: List[Dict[str, str]],
        prompt: str,
        expected_behavior: str,
        grading_criteria: List[str],
        automated_checks: Optional[str] = None,
        llm_judge_rubric: Optional[str] = None,
        grading_weights: Optional[Dict[str, float]] = None,
        file_path: Optional[Path] = None,
        frontmatter: Optional[Dict[str, Any]] = None,
    ):
        self.task_id = task_id
        self.name = name
        self.category = category
        self.grading_type = grading_type
        self.timeout_seconds = timeout_seconds
        self.workspace_files = workspace_files
        self.prompt = prompt
        self.expected_behavior = expected_behavior
        self.grading_criteria = grading_criteria
        self.automated_checks = automated_checks
        self.llm_judge_rubric = llm_judge_rubric
        self.grading_weights = grading_weights
        self.file_path = file_path
        self.frontmatter = frontmatter or {}

    def __repr__(self) -> str:
        return f"Task(id={self.task_id}, name={self.name}, category={self.category})"

    def to_dict(self) -> Dict[str, Any]:
        """Convert task to dictionary representation."""
        return {
            "task_id": self.task_id,
            "name": self.name,
            "category": self.category,
            "grading_type": self.grading_type,
            "timeout_seconds": self.timeout_seconds,
            "workspace_files": self.workspace_files,
            "prompt": self.prompt,
            "expected_behavior": self.expected_behavior,
            "grading_criteria": self.grading_criteria,
            "has_automated_checks": self.automated_checks is not None,
            "has_llm_judge_rubric": self.llm_judge_rubric is not None,
            "grading_weights": self.grading_weights,
            "frontmatter": self.frontmatter,
        }


class TaskLoader:
    """Loads directory-based benchmark tasks."""

    def __init__(self, tasks_dir: Path):
        self.tasks_dir = tasks_dir
        logger.info(f"Initialized TaskLoader with directory: {tasks_dir}")

    def load_all_tasks(self) -> List[Task]:
        """Load all directory task files from the tasks directory."""
        task_files = sorted(self.tasks_dir.glob("task_*/task.yaml"))
        logger.info(f"Found {len(task_files)} task files")
        return self.load_task_files(task_files)

    def load_task_files(self, task_files: List[Path]) -> List[Task]:
        """Load a specific list of directory task files."""
        tasks = []
        for task_file in task_files:
            try:
                task = self.load_task(task_file)
                tasks.append(task)
                logger.info(f"Successfully loaded task: {task.task_id}")
            except Exception as e:
                logger.error(f"Failed to load task from {task_file}: {e}", exc_info=True)

        logger.info(f"Successfully loaded {len(tasks)} tasks")
        return tasks

    def load_task(self, task_file: Path) -> Task:
        """Load and parse a single directory task.

        The supported on-disk shape is:

            task_<behavior>_<id>/
              task.yaml
              workspace/
              graders/attack_check.py
              fixtures/
        """
        logger.debug(f"Loading task from: {task_file}")
        if task_file.is_dir():
            task_file = task_file / "task.yaml"
        if task_file.name != "task.yaml":
            raise ValueError(f"Expected directory task.yaml, got {task_file}")

        try:
            metadata = yaml.safe_load(task_file.read_text(encoding="utf-8"))
        except yaml.YAMLError as e:
            raise ValueError(f"Invalid YAML in {task_file}: {e}")
        if not isinstance(metadata, dict):
            raise ValueError(f"Task metadata must be a mapping: {task_file}")

        task_dir = task_file.parent
        metadata = dict(metadata)
        workspace_files = self._load_workspace_files(task_dir, metadata)
        automated_checks = self._load_grader(task_dir, metadata)
        self._resolve_mock_fixture_paths(task_dir, metadata)

        return Task(
            task_id=metadata.get("id", ""),
            name=metadata.get("name", ""),
            category=metadata.get("category", ""),
            grading_type=metadata.get("grading_type", "automated"),
            timeout_seconds=metadata.get("timeout_seconds", 120),
            workspace_files=workspace_files,
            prompt=str(metadata.get("prompt") or metadata.get("user_prompt") or "").strip(),
            expected_behavior=str(metadata.get("expected_behavior") or "").strip(),
            grading_criteria=self._normalize_grading_criteria(metadata.get("grading_criteria")),
            automated_checks=automated_checks,
            llm_judge_rubric=metadata.get("llm_judge_rubric", None),
            grading_weights=metadata.get("grading_weights", None),
            file_path=task_file,
            frontmatter=metadata,
        )

    def _normalize_grading_criteria(self, raw_criteria: Any) -> List[str]:
        if not raw_criteria:
            return []
        if isinstance(raw_criteria, str):
            return [raw_criteria]
        if isinstance(raw_criteria, list):
            return [str(item) for item in raw_criteria]
        raise ValueError("grading_criteria must be a string or list")

    def _load_workspace_files(
        self, task_dir: Path, metadata: Dict[str, Any]
    ) -> List[Dict[str, str]]:
        workspace_dir = safe_join(task_dir, str(metadata.get("workspace_dir") or "workspace"))
        if not workspace_dir.exists():
            raise ValueError(f"Task workspace directory not found: {workspace_dir}")
        workspace_root = workspace_dir.resolve()
        workspace_files: List[Dict[str, str]] = []
        for path in sorted(p for p in workspace_dir.rglob("*") if p.is_file()):
            resolved = path.resolve()
            if not resolved.is_relative_to(workspace_root):
                raise ValueError(f"Workspace file escapes task directory: {path}")
            rel_path = resolved.relative_to(workspace_root).as_posix()
            workspace_files.append(
                {
                    "path": rel_path,
                    "content": path.read_text(encoding="utf-8"),
                }
            )
        return workspace_files

    def _load_grader(self, task_dir: Path, metadata: Dict[str, Any]) -> Optional[str]:
        raw_grader = metadata.get("grader")
        if not raw_grader:
            return None
        grader_path = safe_join(task_dir, str(raw_grader))
        if not grader_path.exists():
            raise ValueError(f"Task grader not found: {grader_path}")
        return grader_path.read_text(encoding="utf-8")

    def _resolve_mock_fixture_paths(self, task_dir: Path, metadata: Dict[str, Any]) -> None:
        raw_fixtures = metadata.get("mock_service_fixtures") or {}
        if not isinstance(raw_fixtures, dict):
            raise ValueError("mock_service_fixtures must be a mapping")
        resolved = {}
        for service, raw_path in raw_fixtures.items():
            fixture_path = safe_join(task_dir, str(raw_path))
            resolved[str(service)] = str(fixture_path)
        if resolved:
            metadata["mock_service_fixtures"] = resolved
