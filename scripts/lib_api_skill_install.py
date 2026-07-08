"""Install standard mock API skills into ActBench task workspaces."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from lib_api_services import SERVICE_SPECS

REPO_ROOT = Path(__file__).resolve().parents[1]
API_SKILL_TEMPLATE_ROOT = REPO_ROOT / "skills" / "mock_apis"


def api_skill_name(service_name: str) -> str:
    return f"{service_name}_api"


def api_skill_template_dir(service_name: str) -> Path:
    return API_SKILL_TEMPLATE_ROOT / api_skill_name(service_name)


def api_skill_workspace_path(service_name: str) -> str:
    return f"skills/{api_skill_name(service_name)}/SKILL.md"


def install_mock_api_skills(
    workspace: Path,
    services: list[str],
    *,
    overwrite: bool = False,
) -> list[dict[str, Any]]:
    """Copy standard mock API skills into a workspace and return metadata."""
    installed: list[dict[str, Any]] = []
    dest_root = workspace / "skills"
    for service in services:
        service = str(service).strip()
        if not service:
            continue
        if service not in SERVICE_SPECS:
            raise ValueError(f"unknown mock API service for skill install: {service}")
        source = api_skill_template_dir(service)
        if not source.exists():
            raise FileNotFoundError(f"missing standard API skill template: {source}")
        name = api_skill_name(service)
        dest = dest_root / name
        if dest.exists() and overwrite:
            shutil.rmtree(dest)
        if not dest.exists():
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(source, dest)
        installed.append(
            {
                "service": service,
                "name": name,
                "path": api_skill_workspace_path(service),
                "source": str(source.relative_to(REPO_ROOT)),
            }
        )
    return installed
