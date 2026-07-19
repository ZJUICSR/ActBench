"""
OpenClaw agent execution helpers for ClawEval.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib import error, request

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

logger = logging.getLogger(__name__)


class ModelValidationError(Exception):
    """Raised when a model ID is invalid or inaccessible."""

    pass


MAX_OPENCLAW_MESSAGE_CHARS = int(os.environ.get("CLAWEVAL_MAX_MSG_CHARS", "4000"))


def _artifact_fixture_paths(config: Dict[str, Any]) -> Dict[str, Path]:
    overrides = get_fixture_overrides(config)
    paths: Dict[str, Path] = {}
    for service in get_declared_mock_services(config):
        spec = SERVICE_SPECS.get(service)
        paths[service] = overrides.get(service) or (spec.fixture_path if spec else Path(""))
    return paths


def _coerce_subprocess_output(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def slugify_model(model_id: str) -> str:
    return model_id.replace("/", "-").replace(".", "-").lower()


def _normalized_agent_id(agent_id: str) -> str:
    return agent_id.replace(":", "-").lower()


def _list_openclaw_agents() -> List[Dict[str, Any]] | None:
    """Return OpenClaw agent metadata from the stable JSON CLI output."""
    try:
        list_result = subprocess.run(
            ["openclaw", "agents", "list", "--json"],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        logger.error("openclaw CLI not found while listing agents")
        return None

    if list_result.returncode != 0:
        logger.warning("Agent list returned %s: %s", list_result.returncode, list_result.stderr)
        return None

    try:
        payload = json.loads(list_result.stdout or "[]")
    except json.JSONDecodeError as exc:
        logger.warning("Failed to parse OpenClaw agents JSON: %s", exc)
        return None

    if not isinstance(payload, list):
        logger.warning("Unexpected OpenClaw agents JSON payload: %r", type(payload).__name__)
        return None
    return [entry for entry in payload if isinstance(entry, dict)]


def _find_openclaw_agent(agent_id: str) -> Dict[str, Any] | None:
    agents = _list_openclaw_agents()
    if agents is None:
        return None
    candidate_ids = {agent_id.lower(), _normalized_agent_id(agent_id)}
    for entry in agents:
        entry_id = entry.get("id")
        if isinstance(entry_id, str) and entry_id.lower() in candidate_ids:
            return entry
    return None


def _openclaw_agent_command(*, agent_id: str, session_id: str, message: str) -> List[str]:
    """Build the OpenClaw 5.18 local execution command used by ActBench."""
    return [
        "openclaw",
        "agent",
        "--local",
        "--agent",
        agent_id,
        "--session-id",
        session_id,
        "--message",
        message,
    ]


def validate_openrouter_model(model_id: str, timeout_seconds: float = 10.0) -> bool:
    """
    Validate that a model ID exists on OpenRouter.

    Args:
        model_id: Model ID (with or without openrouter/ prefix)
        timeout_seconds: HTTP request timeout

    Returns:
        True if model is valid and accessible

    Raises:
        ModelValidationError: If model doesn't exist or validation fails
    """
    # Strip openrouter/ prefix if present
    bare_model_id = model_id
    if bare_model_id.startswith("openrouter/"):
        bare_model_id = bare_model_id[len("openrouter/") :]

    # Skip validation for non-OpenRouter models
    if "/" not in bare_model_id:
        logger.info("Skipping model validation for non-OpenRouter model: %s", model_id)
        return True

    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        logger.warning("OPENROUTER_API_KEY not set, skipping model validation")
        return True

    logger.info("🔍 Validating model: %s", bare_model_id)

    headers = {
        "Authorization": f"Bearer {api_key}",
        "HTTP-Referer": "https://github.com/ZJUICSR/ClawEval",
        "X-Title": "ClawEval",
    }

    # First, try the specific model endpoint (fast path for valid models)
    encoded_model_id = bare_model_id.replace("/", "%2F")
    specific_endpoint = f"https://openrouter.ai/api/v1/models/{encoded_model_id}"
    req = request.Request(specific_endpoint, headers=headers, method="GET")
    try:
        with request.urlopen(req, timeout=timeout_seconds) as resp:
            # Model exists - validation passed
            logger.info("✅ Model validated: %s", bare_model_id)
            return True
    except error.HTTPError as exc:
        if exc.code == 404:
            # Model not found - fall through to fetch full catalog for suggestions
            pass
        else:
            logger.warning("OpenRouter API error during validation: %s", exc)
            return True
    except error.URLError as exc:
        logger.warning("Network error during model validation: %s", exc)
        return True

    # Model not found - fetch full catalog for "did you mean" suggestions
    catalog_endpoint = "https://openrouter.ai/api/v1/models"
    req = request.Request(catalog_endpoint, headers=headers, method="GET")
    try:
        with request.urlopen(req, timeout=timeout_seconds) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except error.HTTPError as exc:
        logger.warning("OpenRouter API error fetching model catalog: %s", exc)
        raise ModelValidationError(f"Model '{bare_model_id}' not found on OpenRouter.")
    except error.URLError as exc:
        logger.warning("Network error fetching model catalog: %s", exc)
        raise ModelValidationError(f"Model '{bare_model_id}' not found on OpenRouter.")
    except json.JSONDecodeError as exc:
        logger.warning("Failed to parse OpenRouter response: %s", exc)
        raise ModelValidationError(f"Model '{bare_model_id}' not found on OpenRouter.")

    models = data.get("data", [])
    model_ids = {
        mid
        for m in models
        if isinstance(m, dict)
        for mid in [m.get("id")]
        if isinstance(mid, str) and mid
    }

    # Some OpenRouter model detail lookups intermittently return 404 for valid
    # IDs. Treat an exact catalog hit as authoritative to avoid false negatives.
    if bare_model_id in model_ids:
        logger.info("✅ Model validated via catalog fallback: %s", bare_model_id)
        return True

    # Check for close matches (typos)
    close_matches = []
    bare_lower = bare_model_id.lower()
    for mid in model_ids:
        mid_lower = mid.lower()
        if mid_lower == bare_lower:
            continue
        if bare_lower in mid_lower or mid_lower in bare_lower:
            close_matches.append(mid)

    error_msg = f"Model '{bare_model_id}' not found on OpenRouter."
    if close_matches:
        close_matches_str = ", ".join(sorted(close_matches)[:5])
        error_msg += f" Did you mean: {close_matches_str}?"
    else:
        # Try to suggest based on provider
        provider = bare_model_id.split("/")[0] if "/" in bare_model_id else None
        if provider:
            provider_models = [m for m in model_ids if m.startswith(f"{provider}/")]
            if provider_models:
                error_msg += (
                    f" Available {provider} models: {', '.join(sorted(provider_models)[:5])}"
                )

    raise ModelValidationError(error_msg)


def _get_agent_workspace(agent_id: str) -> Path | None:
    """Get the workspace path for an agent from OpenClaw config."""
    agent = _find_openclaw_agent(agent_id)
    if not agent:
        return None
    workspace = agent.get("workspace")
    if not isinstance(workspace, str) or not workspace:
        return None
    return Path(workspace).expanduser()


def _get_agent_model(agent_id: str) -> str | None:
    """Get the configured model id for an agent from OpenClaw config."""
    agent = _find_openclaw_agent(agent_id)
    if not agent:
        return None
    model = agent.get("model")
    if not isinstance(model, str) or not model:
        return None
    return model


def ensure_agent_exists(agent_id: str, model_id: str, workspace_dir: Path) -> bool:
    """Ensure the OpenClaw agent exists with the correct workspace and model.

    If the agent already exists but points to a different workspace or model, it
    is deleted and recreated so that the new configuration takes effect.
    Returns True if the agent was (re)created.
    """
    workspace_dir.mkdir(parents=True, exist_ok=True)

    existing_agent = _find_openclaw_agent(agent_id)
    if existing_agent:
        current_workspace = _get_agent_workspace(agent_id)
        current_model = _get_agent_model(agent_id)
        workspace_matches = (
            current_workspace is not None and current_workspace.resolve() == workspace_dir.resolve()
        )
        model_matches = current_model is None or current_model == model_id
        if workspace_matches and model_matches:
            logger.info("Agent %s already exists with correct workspace and model", agent_id)
            return False
        delete_name = existing_agent.get("id")
        if not isinstance(delete_name, str) or not delete_name:
            delete_name = _normalized_agent_id(agent_id)
        logger.info(
            "Agent %s exists with stale config (workspace %s != %s or model %s != %s), recreating",
            agent_id,
            current_workspace,
            workspace_dir,
            current_model,
            model_id,
        )
        subprocess.run(
            ["openclaw", "agents", "delete", delete_name, "--force"],
            capture_output=True,
            text=True,
            check=False,
        )

    logger.info("Creating OpenClaw agent %s", agent_id)
    try:
        create_result = subprocess.run(
            [
                "openclaw",
                "agents",
                "add",
                agent_id,
                "--model",
                model_id,
                "--workspace",
                str(workspace_dir),
                "--non-interactive",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        logger.error("openclaw CLI not found while creating agent")
        return False

    if create_result.returncode != 0:
        logger.warning(
            "Agent creation returned %s: %s", create_result.returncode, create_result.stderr
        )
    return True


def cleanup_agent_sessions(agent_id: str) -> None:
    """Remove stored session transcripts for an agent to avoid unbounded growth."""
    agent_dir = _get_agent_store_dir(agent_id)
    sessions_dir = agent_dir / "sessions"
    if not sessions_dir.exists():
        return
    removed = 0
    for pattern in ("*.jsonl", "*.jsonl.lock", "*.ndjson"):
        for path in sessions_dir.rglob(pattern):
            try:
                path.unlink()
                removed += 1
            except OSError as exc:
                logger.warning("Failed to remove session file %s: %s", path, exc)
    sessions_store = sessions_dir / "sessions.json"
    if sessions_store.exists():
        try:
            sessions_store.unlink()
        except OSError as exc:
            logger.warning("Failed to remove session store %s: %s", sessions_store, exc)
    if removed:
        logger.info("Removed %s old OpenClaw session transcripts for %s", removed, agent_id)


def prepare_task_workspace(skill_dir: Path, run_id: str, task: Task, agent_id: str) -> Path:
    """
    Prepare workspace for a task by copying fixtures.
    Uses the agent's configured workspace to ensure files are in the right place.
    """
    import shutil

    # Get agent's workspace from agent config
    workspace = _get_agent_workspace(agent_id)
    if workspace is None:
        # Fallback to task-specific workspace if agent workspace not found
        logger.warning("Could not find agent workspace, using fallback")
        workspace = Path(f"/tmp/claweval/{run_id}/{task.task_id}")

    # Reset the workspace between tasks but preserve
    # .openclaw state so OpenClaw can keep any required local metadata.
    if workspace.exists():
        openclaw_state = workspace / ".openclaw"
        saved_state = None
        if openclaw_state.exists():
            saved_state = Path(f"/tmp/claweval/{run_id}/_state_{task.task_id}")
            if saved_state.exists():
                shutil.rmtree(saved_state)
            shutil.copytree(openclaw_state, saved_state)
        shutil.rmtree(workspace)
        workspace.mkdir(parents=True, exist_ok=True)
        if saved_state and saved_state.exists():
            shutil.copytree(saved_state, openclaw_state)
            shutil.rmtree(saved_state)
    else:
        workspace.mkdir(parents=True, exist_ok=True)

    resolved_workspace = workspace.resolve()

    for file_spec in task.workspace_files:
        if "content" in file_spec:
            dest = (workspace / file_spec["path"]).resolve()
            if not dest.is_relative_to(resolved_workspace):
                logger.error("Path traversal blocked: %s", file_spec["path"])
                raise ValueError(f"Workspace path escapes sandbox: {file_spec['path']}")
            dest.parent.mkdir(parents=True, exist_ok=True)
            content = materialize_workspace_file(file_spec, task.frontmatter, task.workspace_files)
            dest.write_text(content, encoding="utf-8")
            if dest.suffix == ".sh":
                dest.chmod(dest.stat().st_mode | 0o111)  # ensure shell scripts are executable
            continue

        source = skill_dir / "assets" / file_spec["source"]
        dest = (workspace / file_spec["dest"]).resolve()
        if not dest.is_relative_to(resolved_workspace):
            logger.error("Path traversal blocked: %s", file_spec["dest"])
            raise ValueError(f"Workspace path escapes sandbox: {file_spec['dest']}")
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            dest.write_bytes(source.read_bytes())
        except FileNotFoundError:
            logger.error("Workspace file not found: %s", source)
            raise

    # Remove bootstrap files that would trigger the onboarding flow
    # These interfere with benchmark tasks
    for bootstrap_file in ["BOOTSTRAP.md", "SOUL.md", "USER.md", "IDENTITY.md"]:
        bootstrap_path = workspace / bootstrap_file
        if bootstrap_path.exists():
            try:
                bootstrap_path.unlink()
                logger.info("Removed bootstrap file: %s", bootstrap_file)
            except OSError as exc:
                logger.warning("Failed to remove %s: %s", bootstrap_file, exc)

    mock_services = get_declared_mock_services(task.frontmatter)
    if mock_services:
        install_mock_api_skills(workspace, mock_services)

    return workspace


def _get_agent_store_dir(agent_id: str) -> Path:
    base_dir = Path.home() / ".openclaw" / "agents"
    # OpenClaw normalizes agent IDs to lowercase and replaces colons with dashes
    normalized_id = agent_id.replace(":", "-").lower()
    direct_dir = base_dir / agent_id
    if direct_dir.exists():
        return direct_dir
    normalized_dir = base_dir / normalized_id
    if normalized_dir.exists():
        return normalized_dir
    return direct_dir


def _resolve_session_id_from_store(
    agent_id: str,
    explicit_session_id: str | None = None,
) -> str | None:
    agent_dir = _get_agent_store_dir(agent_id)
    sessions_store = agent_dir / "sessions" / "sessions.json"
    if not sessions_store.exists():
        return None
    try:
        sessions_payload = json.loads(sessions_store.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        logger.warning("Failed to parse sessions store: %s", exc)
        return None
    if not isinstance(sessions_payload, dict):
        return None

    normalized_id = agent_id.replace(":", "-").lower()
    preferred_keys = []
    if explicit_session_id:
        preferred_keys.extend(
            [
                f"agent:{agent_id}:explicit:{explicit_session_id}",
                f"agent:{normalized_id}:explicit:{explicit_session_id}",
            ]
        )
    preferred_keys.extend(
        [
            f"agent:{agent_id}:main",
            f"agent:{agent_id}:default",
            f"agent:{normalized_id}:main",
            f"agent:{normalized_id}:default",
        ]
    )
    for key in preferred_keys:
        entry = sessions_payload.get(key)
        if isinstance(entry, dict) and entry.get("sessionId"):
            return entry["sessionId"]

    newest_entry = None
    newest_timestamp = -1
    for entry in sessions_payload.values():
        if not isinstance(entry, dict):
            continue
        if "sessionId" not in entry:
            continue
        updated_at = entry.get("updatedAt")
        if isinstance(updated_at, (int, float)) and updated_at > newest_timestamp:
            newest_timestamp = updated_at
            newest_entry = entry
    if newest_entry:
        return newest_entry.get("sessionId")
    return None


def _find_transcript_path_from_sessions_store(
    agent_id: str,
    *,
    requested_session_id: str | None = None,
    resolved_session_id: str | None = None,
) -> Optional[Path]:
    """Best-effort transcript path resolution from scoped sessions.json values."""
    agent_dir = _get_agent_store_dir(agent_id)
    sessions_store = agent_dir / "sessions" / "sessions.json"
    if not sessions_store.exists():
        return None
    try:
        payload = json.loads(sessions_store.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None

    def _iter_strings(node: Any):
        if isinstance(node, str):
            yield node
        elif isinstance(node, dict):
            for value in node.values():
                yield from _iter_strings(value)
        elif isinstance(node, list):
            for value in node:
                yield from _iter_strings(value)

    normalized_id = agent_id.replace(":", "-").lower()
    scoped_entries: List[Any] = []
    seen_keys: set[str] = set()
    preferred_keys: List[str] = []
    if requested_session_id:
        preferred_keys.extend(
            [
                f"agent:{agent_id}:explicit:{requested_session_id}",
                f"agent:{normalized_id}:explicit:{requested_session_id}",
            ]
        )
    preferred_keys.extend(
        [
            f"agent:{agent_id}:main",
            f"agent:{agent_id}:default",
            f"agent:{normalized_id}:main",
            f"agent:{normalized_id}:default",
        ]
    )
    for key in preferred_keys:
        entry = payload.get(key)
        if isinstance(entry, dict):
            scoped_entries.append(entry)
            seen_keys.add(key)

    target_session_ids = {value for value in (requested_session_id, resolved_session_id) if value}
    for key, entry in payload.items():
        if key in seen_keys or not isinstance(entry, dict):
            continue
        if entry.get("sessionId") in target_session_ids:
            scoped_entries.append(entry)

    suffixes = (".jsonl", ".ndjson")
    session_root = agent_dir / "sessions"
    for entry in scoped_entries:
        for value in _iter_strings(entry):
            if not value.endswith(suffixes):
                continue
            candidate = Path(value)
            if not candidate.is_absolute():
                candidate = session_root / value
            if candidate.exists() and candidate.is_file():
                return candidate
    return None


def _find_recent_session_path(agent_dir: Path, started_at: float) -> Path | None:
    sessions_dir = agent_dir / "sessions"
    if not sessions_dir.exists():
        return None
    candidates: List[tuple[Path, float]] = []
    for pattern in ("*.jsonl", "*.ndjson"):
        for path in sessions_dir.rglob(pattern):
            try:
                candidates.append((path, path.stat().st_mtime))
            except OSError:
                continue
    if not candidates:
        return None
    tolerance_seconds = 5.0
    recent_candidates = [
        item for item in candidates if item[1] >= (started_at - tolerance_seconds)
    ]
    pool = recent_candidates or candidates
    return max(pool, key=lambda item: item[1])[0]


def _session_id_from_transcript_path(path: Path) -> str | None:
    if path.name in {"transcript.jsonl", "events.jsonl"} and path.parent.name:
        return path.parent.name
    if path.suffix in {".jsonl", ".ndjson"}:
        return path.stem
    return None


def _transcript_source(
    *,
    kind: str,
    agent_id: str,
    requested_session_id: str | None,
    resolved_session_id: str | None = None,
    transcript_path: Path | None = None,
    fallback_used: bool = False,
    attempts: int = 0,
    started_at: float | None = None,
    **extra: Any,
) -> Dict[str, Any]:
    source: Dict[str, Any] = {
        "kind": kind,
        "agent_id": agent_id,
        "requested_session_id": requested_session_id,
        "resolved_session_id": resolved_session_id,
        "transcript_path": str(transcript_path) if transcript_path is not None else None,
        "fallback_used": fallback_used,
        "attempts": attempts,
    }
    if started_at is not None:
        source["started_at"] = started_at
    source.update({key: value for key, value in extra.items() if value is not None})
    return source


def _read_transcript_file(transcript_path: Path) -> List[Dict[str, Any]]:
    transcript: List[Dict[str, Any]] = []
    for line in transcript_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            transcript.append(json.loads(line))
        except json.JSONDecodeError as exc:
            logger.warning("Failed to parse transcript line: %s", exc)
            transcript.append({"raw": line, "parse_error": str(exc)})
    return transcript


def _load_transcript_with_source(
    agent_id: str,
    session_id: str,
    started_at: float,
) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
    agent_dir = _get_agent_store_dir(agent_id)
    transcript_path: Path | None = None
    source_kind = "missing"
    resolved_session_id: str | None = None
    fallback_used = False
    attempts_used = 0

    # OpenClaw ignores the --session-id we pass and generates its own UUID-based
    # session ID internally.  We need to discover the actual transcript path.
    #
    # Strategy (with retries to handle write-delay):
    #   1. Resolve the real session ID from sessions.json
    #   2. Parse transcript-like paths embedded in sessions.json values
    #   3. Try our passed-in session ID as a last resort
    #   4. Glob for any .jsonl in the sessions dir (most-recently-modified)
    for attempt in range(15):
        attempts_used = attempt + 1
        # 1. Try sessions.json first — OpenClaw writes the real UUID here
        resolved_session_id = _resolve_session_id_from_store(agent_id, session_id)
        if resolved_session_id:
            session_dir = agent_dir / "sessions"
            for candidate in (
                session_dir / f"{resolved_session_id}.jsonl",
                session_dir / f"{resolved_session_id}.ndjson",
                session_dir / resolved_session_id / "transcript.jsonl",
                session_dir / resolved_session_id / "events.jsonl",
            ):
                if candidate.exists():
                    transcript_path = candidate
                    source_kind = "sessions_json"
                    logger.info(
                        "Found transcript via sessions.json: %s (attempt %s)",
                        candidate.name,
                        attempt + 1,
                    )
                    break
            if transcript_path is not None:
                break

        # 1b. Parse transcript-like paths from the matching sessions.json entry
        candidate_from_store = _find_transcript_path_from_sessions_store(
            agent_id,
            requested_session_id=session_id,
            resolved_session_id=resolved_session_id,
        )
        if candidate_from_store is not None:
            transcript_path = candidate_from_store
            source_kind = "sessions_json_embedded_path"
            resolved_session_id = resolved_session_id or _session_id_from_transcript_path(
                candidate_from_store
            )
            logger.info(
                "Found transcript via sessions.json path: %s (attempt %s)",
                candidate_from_store,
                attempt + 1,
            )
            break

        # 2. Try our passed-in session ID (unlikely to work, but exact if it does)
        for direct_path in (
            agent_dir / "sessions" / f"{session_id}.jsonl",
            agent_dir / "sessions" / f"{session_id}.ndjson",
        ):
            if direct_path.exists():
                transcript_path = direct_path
                source_kind = "passed_session_id"
                resolved_session_id = session_id
                logger.info(
                    "Found transcript via passed session ID: %s (attempt %s)",
                    direct_path.name,
                    attempt + 1,
                )
                break
        if transcript_path is not None:
            break

        # 3. Glob fallback — pick the most recently modified .jsonl
        recent_path = _find_recent_session_path(agent_dir, started_at)
        if recent_path is not None:
            transcript_path = recent_path
            source_kind = "recent_glob"
            resolved_session_id = _session_id_from_transcript_path(recent_path)
            fallback_used = True
            logger.info(
                "Found transcript via glob fallback: %s (attempt %s)",
                recent_path.name,
                attempt + 1,
            )
            break

        if attempt < 14:
            time.sleep(1.0)

    if transcript_path is None:
        sessions_dir = agent_dir / "sessions"
        if sessions_dir.exists():
            all_files = list(sessions_dir.iterdir())
            logger.warning(
                "Transcript not found for agent %s. Sessions dir contents: %s",
                agent_id,
                [f.name for f in all_files],
            )
            sessions_store = sessions_dir / "sessions.json"
            if sessions_store.exists():
                try:
                    payload_preview = sessions_store.read_text(encoding="utf-8")[:1200]
                    logger.warning("sessions.json preview: %s", payload_preview)
                except OSError as exc:
                    logger.warning("Could not read sessions.json preview: %s", exc)
        else:
            logger.warning(
                "Transcript not found — sessions dir does not exist: %s",
                sessions_dir,
            )
        return [], _transcript_source(
            kind="missing",
            agent_id=agent_id,
            requested_session_id=session_id,
            resolved_session_id=resolved_session_id,
            fallback_used=False,
            attempts=attempts_used,
            started_at=started_at,
        )

    source = _transcript_source(
        kind=source_kind,
        agent_id=agent_id,
        requested_session_id=session_id,
        resolved_session_id=resolved_session_id,
        transcript_path=transcript_path,
        fallback_used=fallback_used,
        attempts=attempts_used,
        started_at=started_at,
    )
    try:
        return _read_transcript_file(transcript_path), source
    except OSError as exc:
        logger.warning("Failed to read transcript %s: %s", transcript_path, exc)
        source.update({"kind": "missing", "read_error": str(exc), "fallback_used": True})
        return [], source


def _load_transcript(agent_id: str, session_id: str, started_at: float) -> List[Dict[str, Any]]:
    transcript, _source = _load_transcript_with_source(agent_id, session_id, started_at)
    return transcript


def _extract_usage_from_transcript(transcript: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Sum token usage and cost from all assistant messages in transcript."""
    totals = {
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_read_tokens": 0,
        "cache_write_tokens": 0,
        "total_tokens": 0,
        "cost_usd": 0.0,
        "request_count": 0,
    }

    for entry in transcript:
        if entry.get("type") != "message":
            continue
        msg = entry.get("message", {})
        if msg.get("role") != "assistant":
            continue
        totals["request_count"] += 1
        usage = msg.get("usage", {})
        totals["input_tokens"] += usage.get("input", 0)
        totals["output_tokens"] += usage.get("output", 0)
        totals["cache_read_tokens"] += usage.get("cacheRead", 0)
        totals["cache_write_tokens"] += usage.get("cacheWrite", 0)
        totals["total_tokens"] += usage.get("totalTokens", 0)
        cost = usage.get("cost", {})
        totals["cost_usd"] += cost.get("total", 0.0)

    return totals


def _build_clean_cwd(run_id: str, task_id: str) -> Path:
    """Use a temp cwd instead of the agent workspace for stable transcript capture."""
    safe_task_id = task_id.replace("/", "_")
    clean_cwd = Path(f"/tmp/claweval/{run_id}/_cwd/{safe_task_id}")
    clean_cwd.mkdir(parents=True, exist_ok=True)
    return clean_cwd


def _stdout_transcript_fallback(prompt: str, stdout: str) -> List[Dict[str, Any]]:
    if not stdout.strip():
        return []
    return [
        {
            "type": "message",
            "message": {
                "role": "user",
                "content": [prompt],
            },
        },
        {
            "type": "message",
            "message": {
                "role": "assistant",
                "content": [{"type": "text", "text": stdout.strip()}],
            },
        },
    ]


def execute_openclaw_task(
    *,
    task: Task,
    agent_id: str,
    model_id: str,
    run_id: str,
    timeout_multiplier: float,
    skill_dir: Path,
    verbose: bool = False,
) -> Dict[str, Any]:
    logger.info("🤖 Agent [%s] starting task: %s", agent_id, task.task_id)
    logger.info("   Task: %s", task.name)
    logger.info("   Category: %s", task.category)
    if verbose:
        logger.info(
            "   Prompt: %s", task.prompt[:500] + "..." if len(task.prompt) > 500 else task.prompt
        )

    # Clean up previous session transcripts so we can reliably find this task's
    # transcript (OpenClaw uses its own UUID-based naming, not our session ID).
    cleanup_agent_sessions(agent_id)

    start_time = time.time()
    workspace = prepare_task_workspace(skill_dir, run_id, task, agent_id)
    clean_cwd = _build_clean_cwd(run_id, task.task_id)
    unique_suffix = uuid.uuid4().hex
    session_id = safe_artifact_name(f"{unique_suffix}_{run_id}_{agent_id}_{task.task_id}")
    artifact_key = safe_artifact_name(f"{session_id}_{task.task_id}")
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
                "model_id": model_id,
                "agent_id": agent_id,
                "run_id": run_id,
                "session_id": session_id,
            },
        )
        recorder.snapshot_directory(workspace, Path("runs") / artifact_key / "workspace_before")
    timeout_seconds = task.timeout_seconds * timeout_multiplier
    stdout = ""
    stderr = ""
    exit_code = -1
    timed_out = False
    api_group = None
    api_audit: Dict[str, Any] = {}
    api_endpoints: Dict[str, Any] = {}

    try:
        mock_services = get_declared_mock_services(task.frontmatter)
        if mock_services:
            api_group = start_api_services(
                services=mock_services,
                run_id=run_id,
                attempt_id=task.task_id,
                fixture_overrides=get_fixture_overrides(task.frontmatter),
                workspace=workspace,
            )
            api_endpoints = api_group.endpoints if api_group else {}
            logger.info("   Mock API services started: %s", ", ".join(mock_services))
    except Exception as exc:  # noqa: BLE001 - surface service startup failures as task errors
        execution_time = time.time() - start_time
        stderr = f"mock API service startup failed: {exc}"
        logger.warning("   %s", stderr)
        if api_group:
            api_group.stop()
        if recorder:
            recorder.record_api_context(
                run_key=artifact_key,
                api_endpoints=api_endpoints,
                api_audit={},
                fixture_overrides=_artifact_fixture_paths(task.frontmatter),
            )
            recorder.snapshot_directory(workspace, Path("runs") / artifact_key / "workspace_after")
        return {
            "agent_id": agent_id,
            "task_id": task.task_id,
            "status": "error",
            "transcript": [],
            "transcript_source": _transcript_source(
                kind="missing",
                agent_id=agent_id,
                requested_session_id=session_id,
                attempts=0,
                started_at=start_time,
                startup_error="mock_api_service_startup_failed",
            ),
            "usage": {},
            "workspace": str(workspace),
            "exit_code": -1,
            "timed_out": False,
            "execution_time": execution_time,
            "stdout": "",
            "stderr": stderr,
            "api_audit": {},
            "api_endpoints": api_endpoints,
            "training_artifact_key": artifact_key,
        }

    # Check if this is a multi-session task
    sessions = task.frontmatter.get("sessions", [])
    logger.info(f"Session: {str(sessions)}")

    if sessions:
        # Multi-session task: send each prompt in sequence
        logger.info(f"📋 Multi-session task with {len(sessions)} sessions")
        for i, session_entry in enumerate(sessions, 1):
            # Extract prompt text from session entry (handle both string and dict formats)
            if isinstance(session_entry, str):
                session_prompt = session_entry
            elif isinstance(session_entry, dict):
                session_prompt = session_entry.get("prompt") or session_entry.get("message", "")
            else:
                logger.warning("⚠️ Skipping invalid session entry: %s", session_entry)
                continue

            logger.info("   Session %d/%d", i, len(sessions))
            elapsed = time.time() - start_time
            remaining = timeout_seconds - elapsed
            if remaining <= 0:
                timed_out = True
                break
            try:
                result = subprocess.run(
                    _openclaw_agent_command(
                        agent_id=agent_id,
                        session_id=session_id,
                        message=session_prompt,
                    ),
                    capture_output=True,
                    text=True,
                    cwd=str(clean_cwd),
                    timeout=remaining,
                    check=False,
                )
                stdout += result.stdout
                stderr += result.stderr
                exit_code = result.returncode
                if result.returncode not in (0, -1):
                    break
            except subprocess.TimeoutExpired as exc:
                timed_out = True
                stdout += _coerce_subprocess_output(exc.stdout)
                stderr += _coerce_subprocess_output(exc.stderr)
                break
            except FileNotFoundError as exc:
                stderr = f"openclaw command not found: {exc}"
                break
    else:
        # Single-session task: send task.prompt once
        try:
            result = subprocess.run(
                _openclaw_agent_command(
                    agent_id=agent_id,
                    session_id=session_id,
                    message=task.prompt,
                ),
                capture_output=True,
                text=True,
                cwd=str(clean_cwd),
                timeout=timeout_seconds,
                check=False,
            )
            stdout = result.stdout
            stderr = result.stderr
            exit_code = result.returncode
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            stdout = _coerce_subprocess_output(exc.stdout)
            stderr = _coerce_subprocess_output(exc.stderr)
        except FileNotFoundError as exc:
            stderr = f"openclaw command not found: {exc}"

    transcript, transcript_source = _load_transcript_with_source(agent_id, session_id, start_time)
    if not transcript:
        fallback_prompt = task.prompt
        if sessions:
            session_prompts = []
            for session_entry in sessions:
                if isinstance(session_entry, str):
                    session_prompts.append(session_entry)
                elif isinstance(session_entry, dict):
                    session_prompts.append(
                        session_entry.get("prompt") or session_entry.get("message", "")
                    )
            fallback_prompt = "\n\n".join(p for p in session_prompts if p)
        fallback_transcript = _stdout_transcript_fallback(fallback_prompt, stdout)
        if fallback_transcript:
            transcript = fallback_transcript
            transcript_source = _transcript_source(
                kind="stdout_fallback",
                agent_id=agent_id,
                requested_session_id=session_id,
                resolved_session_id=transcript_source.get("resolved_session_id"),
                transcript_path=(
                    Path(str(transcript_source["transcript_path"]))
                    if transcript_source.get("transcript_path")
                    else None
                ),
                fallback_used=True,
                attempts=int(transcript_source.get("attempts") or 0),
                started_at=start_time,
                fallback_from=transcript_source.get("kind"),
            )
    usage = _extract_usage_from_transcript(transcript)
    execution_time = time.time() - start_time

    status = "success"
    if timed_out:
        status = "timeout"
    if not transcript:
        status = "error"
    if exit_code not in (0, -1) and not timed_out:
        status = "error"
    if stderr and "openclaw command not found" in str(stderr):
        status = "error"

    # Verbose logging for debugging
    if verbose:
        logger.info("   [VERBOSE] Exit code: %s", exit_code)
        logger.info("   [VERBOSE] Execution time: %.2fs", execution_time)
        logger.info("   [VERBOSE] Workspace: %s", workspace)
        if stdout:
            logger.info("   [VERBOSE] Stdout (first 1000 chars):\n%s", stdout[:1000])
        if stderr:
            logger.info("   [VERBOSE] Stderr:\n%s", stderr[:1000])
        logger.info("   [VERBOSE] Transcript entries: %d", len(transcript))

        # Show agent responses from transcript
        for entry in transcript:
            if entry.get("type") == "message":
                msg = entry.get("message", {})
                role = msg.get("role", "unknown")
                content = msg.get("content", "")
                if role == "assistant":
                    # Truncate long responses
                    preview = content[:500] + "..." if len(content) > 500 else content
                    logger.info("   [VERBOSE] Agent response: %s", preview)
                elif role == "user":
                    preview = content[:200] + "..." if len(content) > 200 else content
                    logger.info("   [VERBOSE] User message: %s", preview)

        # Show workspace files after task
        if workspace.exists():
            logger.info("   [VERBOSE] Workspace files after task:")
            for f in sorted(workspace.rglob("*")):
                if f.is_file():
                    try:
                        size = f.stat().st_size
                        logger.info("      %s (%d bytes)", f.relative_to(workspace), size)
                    except OSError:
                        logger.info("      %s", f.relative_to(workspace))

    if api_group:
        api_audit = api_group.collect_audit()
        api_group.stop()

    if recorder:
        recorder.record_api_context(
            run_key=artifact_key,
            api_endpoints=api_endpoints,
            api_audit=api_audit,
            fixture_overrides=_artifact_fixture_paths(task.frontmatter),
        )
        recorder.snapshot_directory(workspace, Path("runs") / artifact_key / "workspace_after")

    return {
        "agent_id": agent_id,
        "task_id": task.task_id,
        "status": status,
        "transcript": transcript,
        "transcript_source": transcript_source,
        "usage": usage,
        "workspace": str(workspace),
        "exit_code": exit_code,
        "timed_out": timed_out,
        "execution_time": execution_time,
        "stdout": stdout,
        "stderr": stderr,
        "api_audit": api_audit,
        "api_endpoints": api_endpoints,
        "training_artifact_key": artifact_key,
    }


def run_openclaw_prompt(
    *,
    agent_id: str,
    prompt: str,
    workspace: Path,
    timeout_seconds: float,
) -> Dict[str, Any]:
    """Run a single OpenClaw prompt for helper agents like the judge."""
    # Clean up previous session transcripts so we can reliably find this
    # prompt's transcript (OpenClaw uses its own UUID-based naming).
    cleanup_agent_sessions(agent_id)

    start_time = time.time()
    workspace.mkdir(parents=True, exist_ok=True)
    session_id = f"judge_{int(time.time() * 1000)}"
    stdout = ""
    stderr = ""
    exit_code = -1
    timed_out = False

    chunks = [
        prompt[i : i + MAX_OPENCLAW_MESSAGE_CHARS]
        for i in range(0, max(1, len(prompt)), MAX_OPENCLAW_MESSAGE_CHARS)
    ]
    if len(chunks) > 1:
        total_chunks = len(chunks)
        chunks = [
            (
                f"You are receiving a long prompt in {total_chunks} parts.\n"
                f"Ignore and do not respond until the final part.\n\n"
                f"Part 1/{total_chunks}:\n{chunks[0]}"
            )
        ] + [
            (
                f"Part {i + 2}/{total_chunks}:\n{chunks[i + 1]}"
                if i + 2 < total_chunks
                else (
                    f"Part {i + 2}/{total_chunks} (final):\n{chunks[i + 1]}\n"
                    "All parts received. Proceed with final judgment now."
                )
            )
            for i in range(0, total_chunks - 1)
        ]
    for chunk in chunks:
        elapsed = time.time() - start_time
        remaining = timeout_seconds - elapsed
        if remaining <= 0:
            timed_out = True
            break
        try:
            result = subprocess.run(
                _openclaw_agent_command(
                    agent_id=agent_id,
                    session_id=session_id,
                    message=chunk,
                ),
                capture_output=True,
                text=True,
                cwd=str(workspace),
                timeout=remaining,
                check=False,
            )
            stdout += result.stdout
            stderr += result.stderr
            exit_code = result.returncode
            if result.returncode not in (0, -1) and not timed_out:
                break
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            stdout += _coerce_subprocess_output(exc.stdout)
            stderr += _coerce_subprocess_output(exc.stderr)
            break
        except FileNotFoundError as exc:
            stderr += f"openclaw command not found: {exc}"
            break

    transcript = _load_transcript(agent_id, session_id, start_time)
    usage = _extract_usage_from_transcript(transcript)
    execution_time = time.time() - start_time

    status = "success"
    if timed_out:
        status = "timeout"
    if not transcript:
        status = "error"
    if exit_code not in (0, -1) and not timed_out:
        status = "error"
    if stderr and "openclaw command not found" in str(stderr):
        status = "error"

    return {
        "agent_id": agent_id,
        "status": status,
        "transcript": transcript,
        "usage": usage,
        "workspace": str(workspace),
        "exit_code": exit_code,
        "timed_out": timed_out,
        "execution_time": execution_time,
        "stdout": stdout,
        "stderr": stderr,
    }
