"""Benign baseline cache and generation helpers."""

from __future__ import annotations

import json
import logging
import os
import hashlib
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from lib_agent import slugify_model
from lib_tasks import Task

from benchmark.backends.base import AgentBackend, BackendRunContext

from benchmark.transcript import _extract_transcript_file_ops, _summarize_transcript
from lib_scene_bundle import load_scene

logger = logging.getLogger("benchmark")
BASELINE_CACHE_DIR = Path(
    os.environ.get(
        "ACTBENCH_BASELINE_CACHE_DIR",
        str(Path(__file__).resolve().parents[2] / "results" / "benign_baselines"),
    )
)


def _resolve_task_scenario(task: Task) -> Optional[str]:
    """Return the source scenario id from current or legacy task metadata."""
    fm = task.frontmatter or {}
    for key in ("scenario", "scene_id", "source_scene_id", "scenario_id"):
        value = fm.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _resolve_clean_source_path(task: Task, raw_path: Any) -> Optional[Path]:
    if not raw_path:
        return None
    path = Path(str(raw_path))
    candidates: List[Path] = []
    if path.is_absolute():
        candidates.append(path)
    else:
        task_dir = None
        task_path = getattr(task, "file_path", None) or getattr(task, "source_path", None)
        if task_path:
            task_dir = Path(str(task_path)).parent
        if task_dir is not None:
            candidates.extend([task_dir / path, task_dir.parent / path])
        candidates.extend(
            [
                BASELINE_CACHE_DIR.parents[1] / path,
                Path.cwd() / path,
            ]
        )
    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()
    return None


def _normalize_clean_scene(scene: Dict[str, Any], bundle_dir: Path) -> Dict[str, Any]:
    normalized = dict(scene)
    normalized.setdefault("_fixture_base_dir", str(bundle_dir))
    fixtures = normalized.get("mock_service_fixtures") or {}
    if isinstance(fixtures, dict):
        normalized["mock_service_fixtures"] = {
            service: str((bundle_dir / str(path)).resolve()) if not Path(str(path)).is_absolute() else str(path)
            for service, path in fixtures.items()
        }
    return normalized


def _load_clean_source_scene_for_task(task: Task) -> Optional[Dict[str, Any]]:
    clean_source = (task.frontmatter or {}).get("clean_source")
    if not isinstance(clean_source, dict):
        return None
    bundle_path = _resolve_clean_source_path(task, clean_source.get("bundle_path"))
    if bundle_path and (bundle_path / "scenario.yaml").exists():
        try:
            return _normalize_clean_scene(load_scene(bundle_path), bundle_path)
        except Exception as exc:
            logger.warning("Failed to load clean_source bundle for %s: %s", task.task_id, exc)
            return None
    scene_path = _resolve_clean_source_path(task, clean_source.get("scene_file"))
    if scene_path and scene_path.exists():
        try:
            scene = json.loads(scene_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to read clean_source scene for %s: %s", task.task_id, exc)
            return None
        return _normalize_clean_scene(scene, scene_path.parent)
    return None


def _scene_for_task(task: Task, scene_index: Dict[str, Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    clean_scene = _load_clean_source_scene_for_task(task)
    if clean_scene:
        return clean_scene
    scenario = _resolve_task_scenario(task)
    if scenario:
        return scene_index.get(scenario)
    return None


def _baseline_cache_path(
    task: Task,
    model: str,
    scene: Optional[Dict[str, Any]] = None,
    *,
    backend_name: str = "openclaw",
) -> Optional[Path]:
    scenario = _resolve_task_scenario(task) if hasattr(task, "frontmatter") else None
    if not scenario:
        return None
    slug = str(scenario)
    clean_source = (task.frontmatter or {}).get("clean_source")
    if isinstance(clean_source, dict) and clean_source.get("content_hash"):
        slug = f"{slug}_{str(clean_source['content_hash'])[:12]}"
    elif scene and scene.get("_fixture_base_dir"):
        slug = f"{slug}_{hashlib.sha256(str(scene.get('_fixture_base_dir')).encode()).hexdigest()[:12]}"
    model_slug = slugify_model(model)
    if backend_name and backend_name != "openclaw":
        return BASELINE_CACHE_DIR / f"{slug}_{backend_name}_{model_slug}.json"
    return BASELINE_CACHE_DIR / f"{slug}_{model_slug}.json"


def _normalize_content(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    return json.dumps(content, sort_keys=True, ensure_ascii=False)


def _fixture_digest(raw_path: Any) -> Dict[str, str]:
    path = Path(str(raw_path))
    if not path.exists() or not path.is_file():
        return {"path": str(raw_path), "sha256": ""}
    try:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        digest = ""
    return {"path": str(raw_path), "sha256": digest}


def baseline_content_hash(task: Task, scene: Dict[str, Any]) -> str:
    """Hash the benign scene content that a cached baseline depends on."""
    workspace_files = []
    for spec in scene.get("workspace_files") or []:
        if not isinstance(spec, dict):
            continue
        path = spec.get("path")
        if not isinstance(path, str) or not path:
            continue
        workspace_files.append(
            {
                "path": path,
                "content": _normalize_content(spec.get("content", "")),
            }
        )
    workspace_files.sort(key=lambda item: item["path"])

    fixtures = scene.get("mock_service_fixtures") or {}
    fixture_hashes = {}
    if isinstance(fixtures, dict):
        fixture_hashes = {
            str(service): _fixture_digest(path) for service, path in sorted(fixtures.items())
        }

    user_prompt = scene.get("user_prompt") or task.prompt or ""
    payload = {
        "scenario": _resolve_task_scenario(task) or scene.get("id"),
        "user_prompt": str(user_prompt),
        "workspace_files": workspace_files,
        "mock_service_fixtures": fixture_hashes,
        "attack_check_code": _normalize_content(scene.get("attack_check_code", "")),
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _load_baseline_for_task(
    task: Task,
    model: str,
    scene: Optional[Dict[str, Any]] = None,
    *,
    backend_name: str = "openclaw",
) -> Optional[Dict[str, Any]]:
    """Load the cached benign baseline for this task's source scene + model.

    Tasks carry the source scene id in their YAML metadata as ``scenario``;
    legacy/imported tasks may use ``scene_id``, ``source_scene_id``, or
    ``scenario_id``. The baseline cache is keyed by (scene_id,
    slugify_model(model)). Returns None on any miss; benchmark proceeds as
    normal in that case.
    """
    scenario = _resolve_task_scenario(task) if hasattr(task, "frontmatter") else None
    if not scenario:
        return None
    cache_path = _baseline_cache_path(task, model, scene, backend_name=backend_name)
    if cache_path is None:
        return None
    if not cache_path.exists():
        return None
    try:
        baseline = json.loads(cache_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to read baseline cache %s: %s", cache_path.name, exc)
        return None
    if scene is None:
        return baseline
    expected_hash = baseline_content_hash(task, scene)
    cached_hash = baseline.get("content_hash")
    if cached_hash != expected_hash:
        logger.info(
            "Ignoring stale baseline cache for %s: content_hash %s != %s",
            scenario,
            cached_hash or "<missing>",
            expected_hash,
        )
        return None
    return baseline


def _baseline_written_content(workspace_path: Any, files_written: List[str]) -> Dict[str, Dict[str, Any]]:
    workspace = Path(str(workspace_path)) if workspace_path else None
    if not workspace or not workspace.exists():
        return {}
    resolved_workspace = workspace.resolve()
    content: Dict[str, Dict[str, Any]] = {}
    for rel_path in files_written:
        try:
            candidate = (resolved_workspace / rel_path).resolve()
            candidate.relative_to(resolved_workspace)
        except (OSError, ValueError):
            continue
        if not candidate.is_file():
            continue
        try:
            data = candidate.read_bytes()
        except OSError:
            continue
        try:
            preview = data[:4000].decode("utf-8", errors="replace")
        except Exception:
            preview = ""
        content[rel_path] = {
            "sha256": hashlib.sha256(data).hexdigest(),
            "preview": preview,
            "bytes": len(data),
        }
    return content


def _generate_baseline_for_task(
    *,
    task: Task,
    scene: Dict[str, Any],
    model: str,
    backend: AgentBackend,
    context: BackendRunContext,
    run_id: str,
    attempt_run_id: str | None = None,
) -> Optional[Dict[str, Any]]:
    """Run a benign (no-attack) execution for the scene and cache the result.

    Used by _pregenerate_baselines() before the main benchmark loop so that
    evaluate_attack() gets delta-aware scoring instead of absolute scoring.
    Returns the cached baseline dict, or None on failure (non-fatal).
    """
    scenario = _resolve_task_scenario(task)
    if not scenario:
        return None
    if attempt_run_id is None:
        attempt_run_id = f"{run_id}_bl_{scenario[-10:]}"

    cache_path = _baseline_cache_path(task, model, scene, backend_name=backend.name)
    if cache_path is None:
        return None
    expected_hash = baseline_content_hash(task, scene)
    cached = _load_baseline_for_task(task, model, scene=scene, backend_name=backend.name)
    if cached is not None:
        return cached

    clean_workspace = scene.get("workspace_files") or []
    if not isinstance(clean_workspace, list):
        clean_workspace = []
    user_prompt = scene.get("user_prompt") or task.prompt or ""
    if not isinstance(user_prompt, str):
        user_prompt = str(user_prompt)

    clean_task = Task(
        task_id=f"{task.task_id}_baseline",
        name=f"{task.name} (baseline)",
        category=task.category,
        grading_type="automated",
        timeout_seconds=task.timeout_seconds,
        workspace_files=clean_workspace,
        prompt=user_prompt,
        expected_behavior="",
        grading_criteria=[],
        frontmatter={
            key: value
            for key, value in dict(task.frontmatter).items()
            if key
            not in {
                "attack_payload_paths",
                "source_payload",
                "malicious_skill_names",
                "mock_service_fixtures",
                "clean_source",
            }
        },
    )
    clean_task.frontmatter["mock_services"] = scene.get("mock_services") or []
    if scene.get("mock_service_fixtures"):
        clean_task.frontmatter["mock_service_fixtures"] = scene.get("mock_service_fixtures")

    try:
        result = backend.execute_task(
            task=clean_task,
            context=context,
            attempt_run_id=attempt_run_id,
        )
    except Exception as exc:
        logger.warning("Baseline generation failed for %s: %s", scenario, exc)
        return None

    if result.get("status") != "success":
        logger.warning(
            "Baseline run for %s returned status=%s; skipping cache", scenario, result.get("status")
        )
        return None

    transcript = result.get("transcript") or []
    file_ops = _extract_transcript_file_ops(transcript)
    files_written_content = _baseline_written_content(result.get("workspace"), file_ops["files_written"])

    if not file_ops["files_read"] and not file_ops["files_written"]:
        logger.info(
            "Baseline for %s: no file ops (text-output task); "
            "caching transcript for judge delta comparison",
            scenario,
        )

    baseline = {
        "scene_id": scenario,
        "target_model": model,
        "backend": backend.name,
        "content_hash": expected_hash,
        "user_prompt": user_prompt,
        "transcript_summary": _summarize_transcript(transcript),
        "transcript": transcript,
        "files_read": file_ops["files_read"],
        "files_written": file_ops["files_written"],
        "files_written_content": files_written_content,
        "execution_time": result.get("execution_time"),
    }

    try:
        BASELINE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        tmp_path = cache_path.with_suffix(".json.tmp")
        tmp_path.write_text(json.dumps(baseline, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp_path, cache_path)
        logger.info(
            "Baseline cached for %s (%d read, %d written) → %s",
            scenario,
            len(file_ops["files_read"]),
            len(file_ops["files_written"]),
            cache_path.name,
        )
    except OSError as exc:
        logger.warning("Failed to write baseline cache for %s: %s", scenario, exc)

    return baseline


def _pregenerate_baselines(
    *,
    tasks: List[Task],
    scene_index: Dict[str, Dict[str, Any]],
    model: str,
    backend: AgentBackend,
    context: BackendRunContext,
    run_id: str,
    context_factory: Callable[[Task, str, str, int], BackendRunContext] | None = None,
) -> None:
    """Pre-generate benign baselines for any tasks that don't have a cached one.

    Mirrors ActBench's per-scene baseline generation so evaluate_attack() can use
    delta-aware scoring (scoring only novel behaviors, not benign ones).
    Skips silently when scene files are unavailable (evaluation falls back to
    absolute scoring in that case).
    """
    missing: List[Task] = []
    seen_cache_keys: set[str] = set()
    for task in tasks:
        scenario = _resolve_task_scenario(task)
        if not scenario:
            continue
        scene = _scene_for_task(task, scene_index)
        cache_path = _baseline_cache_path(task, model, scene, backend_name=backend.name)
        clean_source = (task.frontmatter or {}).get("clean_source")
        cache_key = str(cache_path) if cache_path is not None else f"{scenario}:{_normalize_content(clean_source)}"
        if cache_key in seen_cache_keys:
            continue
        seen_cache_keys.add(cache_key)
        if scene and _load_baseline_for_task(task, model, scene=scene, backend_name=backend.name) is None:
            missing.append(task)
        elif not scene and cache_path is not None and not cache_path.exists():
            missing.append(task)

    if not missing:
        logger.info("🧪 Baselines: all %d cache entries already cached", len(seen_cache_keys))
        return

    logger.info("🧪 Generating baselines for %d scenes without a cache entry...", len(missing))
    for baseline_index, task in enumerate(missing):
        scenario = _resolve_task_scenario(task)
        scene = _scene_for_task(task, scene_index)
        if not scene:
            logger.warning("  Skipping baseline for %s: scene file not found in index", scenario)
            continue
        attempt_run_id = f"{run_id}_bl_{scenario[-10:] if scenario else task.task_id}"
        baseline_context = (
            context_factory(task, scenario or task.task_id, attempt_run_id, baseline_index)
            if context_factory is not None
            else context
        )
        logger.info("  Generating baseline for %s ...", scenario)
        _generate_baseline_for_task(
            task=task,
            scene=scene,
            model=model,
            backend=backend,
            context=baseline_context,
            run_id=run_id,
            attempt_run_id=attempt_run_id,
        )
