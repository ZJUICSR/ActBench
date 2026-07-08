"""Runtime materialization for mock secret templates.

Committed scenarios/tasks should store placeholders instead of literal-looking
mock credentials. Runtime execution materializes those placeholders into stable,
realistic-looking mock values so privacy-leak tasks remain representative without
committing values that trip repository secret scanners.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

SECRET_PLACEHOLDER_RE = re.compile(r"\{\{CLAWEVAL_SECRET:([A-Z][A-Z0-9_]{2,})\}\}")
SECRET_NAME_MARKERS = ("KEY", "TOKEN", "SECRET", "PASSWORD", "PASS")
MIN_SECRET_VALUE_LENGTH = 12


def secret_placeholder(name: str) -> str:
    return f"{{{{CLAWEVAL_SECRET:{name}}}}}"


def materialization_id(metadata: dict[str, Any] | None) -> str:
    """Return the stable scenario scope used to derive runtime mock secrets."""
    metadata = metadata or {}
    return str(metadata.get("scenario") or metadata.get("id") or "scenario")


def materialize_secret_value(name: str, *, scenario_id: str = "scenario") -> str:
    """Return a deterministic realistic-looking mock secret for a declaration."""
    safe_name = re.sub(r"[^A-Z0-9_]+", "_", str(name).upper()).strip("_") or "API_KEY"
    digest = hashlib.sha256(f"{scenario_id}:{safe_name}:claweval-runtime-secret".encode()).hexdigest()
    prefix = safe_name.lower().replace("_", "-")[:24].strip("-") or "mock-secret"
    return f"sk-claw-{prefix}-{digest[:32]}"


def declaration_for_env(name: str, *, service: str = "", source: str = ".env") -> dict[str, str]:
    declaration = {
        "name": str(name),
        "source": str(source),
        "kind": "api_key",
        "template": secret_placeholder(str(name)),
    }
    if service:
        declaration["service"] = str(service)
    return declaration


def extract_secret_declarations_from_content(
    path: str,
    content: str,
    *,
    scenario_id: str = "scenario",
    include_values: bool = False,
) -> list[dict[str, str]]:
    declarations: list[dict[str, str]] = []
    for match in re.finditer(r'^([A-Z][A-Z0-9_]{2,})=\s*["\']?([^\s"\']+)["\']?\s*$', content, re.MULTILINE):
        name = match.group(1)
        value = match.group(2)
        if not any(marker in name for marker in SECRET_NAME_MARKERS):
            continue
        placeholder_match = SECRET_PLACEHOLDER_RE.fullmatch(value)
        if placeholder_match:
            name = placeholder_match.group(1)
            item = declaration_for_env(name, source=path)
        elif len(value) >= MIN_SECRET_VALUE_LENGTH:
            item = {"name": name, "source": path, "kind": "api_key", "template": secret_placeholder(name)}
            if include_values:
                item["value"] = value
        else:
            continue
        if include_values and "value" not in item:
            item["value"] = materialize_secret_value(name, scenario_id=scenario_id)
        declarations.append(item)
    return declarations


def normalize_secret_declarations(
    metadata: dict[str, Any] | None,
    workspace_files: list[dict[str, Any]] | None = None,
) -> list[dict[str, str]]:
    metadata = metadata or {}
    raw = metadata.get("secret_declarations")
    if raw is None:
        raw = metadata.get("secrets")
    declarations: list[dict[str, str]] = []
    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            if not name and item.get("value"):
                declarations.append(
                    {
                        "name": "LEGACY_SECRET",
                        "source": str(item.get("source") or ".env"),
                        "kind": str(item.get("kind") or "api_key"),
                        "template": str(item.get("template") or secret_placeholder("LEGACY_SECRET")),
                        "value": str(item.get("value")),
                    }
                )
                continue
            if not name:
                continue
            declaration = {
                "name": name,
                "source": str(item.get("source") or ".env"),
                "kind": str(item.get("kind") or "api_key"),
                "template": str(item.get("template") or secret_placeholder(name)),
            }
            if item.get("service"):
                declaration["service"] = str(item.get("service"))
            if item.get("value"):
                declaration["value"] = str(item.get("value"))
            declarations.append(declaration)
    if declarations:
        return declarations
    for file_spec in workspace_files or []:
        if not isinstance(file_spec, dict):
            continue
        path = str(file_spec.get("path", ""))
        if path != ".env":
            continue
        declarations.extend(
            extract_secret_declarations_from_content(path, str(file_spec.get("content") or ""))
        )
    return declarations


def materialized_secrets(
    metadata: dict[str, Any] | None,
    workspace_files: list[dict[str, Any]] | None = None,
) -> list[dict[str, str]]:
    scenario_id = materialization_id(metadata)
    secrets: list[dict[str, str]] = []
    for declaration in normalize_secret_declarations(metadata, workspace_files):
        name = declaration["name"]
        item = dict(declaration)
        if not item.get("value"):
            item["value"] = materialize_secret_value(name, scenario_id=scenario_id)
        secrets.append(item)
    return secrets


def materialize_content(
    content: Any,
    metadata: dict[str, Any] | None = None,
    workspace_files: list[dict[str, Any]] | None = None,
) -> str:
    text = content if isinstance(content, str) else "" if content is None else str(content)
    scenario_id = materialization_id(metadata)
    values = {
        item["name"]: item["value"]
        for item in materialized_secrets(metadata, workspace_files)
        if item.get("name") and item.get("value")
    }

    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        return values.get(name) or materialize_secret_value(name, scenario_id=scenario_id)

    return SECRET_PLACEHOLDER_RE.sub(replace, text)


def materialize_workspace_file(
    file_spec: dict[str, Any],
    metadata: dict[str, Any] | None = None,
    workspace_files: list[dict[str, Any]] | None = None,
) -> str:
    content = file_spec.get("content", "")
    if str(file_spec.get("path", "")) == ".env":
        return materialize_content(content, metadata, workspace_files)
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    import json

    return json.dumps(content, indent=2, ensure_ascii=False, sort_keys=True)
