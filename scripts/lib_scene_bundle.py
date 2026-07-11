"""Directory scenario loading helpers used by ActBench runtime."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict

import yaml


def load_scene(scene_path: Path) -> Dict[str, Any]:
    """Load a scene definition from markdown or a directory-based scenario bundle."""
    if scene_path.is_dir():
        scenario_path = scene_path / "scenario.yaml"
        if not scenario_path.exists():
            raise ValueError(f"Directory scene is missing scenario.yaml: {scene_path}")
        frontmatter = yaml.safe_load(scenario_path.read_text(encoding="utf-8"))
        if not isinstance(frontmatter, dict):
            raise ValueError(f"scenario.yaml must contain a mapping: {scenario_path}")
        report_path = frontmatter.get("generation_report")
        if report_path and "generation" not in frontmatter:
            path = Path(str(report_path))
            report_file = path if path.is_absolute() else scene_path / path
            if report_file.exists():
                report = yaml.safe_load(report_file.read_text(encoding="utf-8"))
                if isinstance(report, dict) and isinstance(report.get("generation"), dict):
                    frontmatter["generation"] = report["generation"]

        workspace_files: list[dict[str, Any]] = []
        workspace_dir = scene_path / "workspace"
        for spec in frontmatter.get("workspace_files", []) or []:
            if not isinstance(spec, dict):
                continue
            raw_path = str(spec.get("path", "")).strip()
            if not raw_path:
                continue
            path = workspace_dir / raw_path
            if not path.exists():
                raise ValueError(f"Declared workspace file is missing: {path}")
            item = dict(spec)
            item["content"] = path.read_text(encoding="utf-8")
            workspace_files.append(item)
        frontmatter["workspace_files"] = workspace_files

        fixtures = {}
        for service, raw_path in (frontmatter.get("mock_service_fixtures") or {}).items():
            path = Path(str(raw_path))
            fixtures[service] = str(path if path.is_absolute() else scene_path / path)
        frontmatter["mock_service_fixtures"] = fixtures

        graders = frontmatter.get("graders") or {}
        attack_grader_path = Path(str(graders.get("attack", "graders/attack_check.py")))
        if not attack_grader_path.is_absolute():
            attack_grader_path = scene_path / attack_grader_path
        if attack_grader_path.exists():
            frontmatter["attack_check_code"] = attack_grader_path.read_text(encoding="utf-8")

        frontmatter["body"] = frontmatter.get("description", "")
        frontmatter["file_path"] = str(scene_path)
        frontmatter["scenario_dir"] = str(scene_path)
        frontmatter["harness_dir"] = str(scene_path)
        return frontmatter

    content = scene_path.read_text(encoding="utf-8")
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", content, re.DOTALL)
    if not match:
        raise ValueError(f"No YAML frontmatter in scene file: {scene_path}")
    frontmatter = yaml.safe_load(match.group(1))
    if not isinstance(frontmatter, dict):
        raise ValueError(f"YAML frontmatter must contain a mapping: {scene_path}")
    frontmatter["body"] = match.group(2)
    frontmatter["file_path"] = str(scene_path)
    return frontmatter
