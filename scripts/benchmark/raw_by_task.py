"""Read-only helpers for consuming raw-by-task ActBench packs."""

from __future__ import annotations

import copy
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from benchmark.task_fingerprint import (
    TASK_HASH_ALGORITHM,
    clean_source_content_hash_from_payload,
    fingerprint_task_payload,
    task_prompt_from_payload,
    task_prompt_sha256_from_payload,
    task_spec_sha256_from_payload,
)

RAW_BY_TASK_SCHEMA_VERSION = "actbench.raw_by_task.v1"
DEFAULT_RAW_BY_TASK_ROOT = Path.home() / "pack" / "raw_by_task"
RAW_BY_TASK_GLOBAL_MANIFEST = "raw_by_task_manifest.json"
BASELINE_CACHE_ONLY_REASON = "baseline_cache_only"
PROTECTED_VALUE_LEAK_REASON = "protected_value_leak"
PROTECTED_VALUE_SCAN_ERROR_REASON = "protected_value_scan_error"
TASK_VERSION_MISMATCH_REASON = "task_version_mismatch"

RAW_ROLE_ATTACKED = "attacked"
RAW_ROLE_BENIGN = "benign"
RAW_ROLE_ALL = "all"

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CURRENT_TASKS_ROOT = _REPO_ROOT / "tasks"
_CURRENT_TASK_PAYLOAD_CACHE: Dict[str, Optional[Dict[str, Any]]] = {}


class RawByTaskError(ValueError):
    """Raised when a raw-by-task pack cannot be resolved or validated."""


@dataclass(frozen=True)
class RawByTaskDataset:
    """Validated raw-by-task dataset directory and manifest."""

    path: Path
    manifest: Dict[str, Any]

    @property
    def name(self) -> str:
        return str(self.manifest.get("name") or self.path.name)

    @property
    def backend(self) -> str:
        return str(self.manifest.get("backend") or "")

    @property
    def target_model(self) -> str:
        return str(self.manifest.get("target_model") or "")

    def summary(self) -> Dict[str, Any]:
        fields = {
            "name": self.name,
            "path": str(self.path),
            "backend": self.manifest.get("backend"),
            "target_model": self.manifest.get("target_model"),
            "copied_success_runs": self.manifest.get("copied_success_runs"),
            "task_count": self.manifest.get("task_count"),
            "suite_counts": self.manifest.get("suite_counts"),
            "baseline_summary": self.manifest.get("baseline_summary"),
        }
        if self.manifest.get("merged_from"):
            fields["merged_from"] = self.manifest.get("merged_from")
        return {key: value for key, value in fields.items() if value is not None}


@dataclass(frozen=True)
class RawByTaskCollection:
    """Trajectory paths plus provenance/exclusions from a raw-by-task selection."""

    trajectory_paths: List[Path]
    excluded: List[Dict[str, Any]]
    source: Dict[str, Any]
    semantic_remaps: List[Dict[str, Any]]


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _expanded_path(value: Path | str | None, default: Path) -> Path:
    if value is None:
        return default.expanduser()
    return Path(value).expanduser()


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _load_optional_json(path: Path) -> Optional[Dict[str, Any]]:
    try:
        payload = _load_json(path)
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def load_raw_by_task_dataset_manifest(dataset_dir: Path | str) -> Dict[str, Any]:
    """Load and validate ``<dataset>/manifest.json``."""

    dataset_path = Path(dataset_dir).expanduser()
    manifest_path = dataset_path / "manifest.json"
    try:
        manifest = _load_json(manifest_path)
    except FileNotFoundError as exc:
        raise RawByTaskError(f"raw_by_task dataset manifest not found: {manifest_path}") from exc
    except json.JSONDecodeError as exc:
        raise RawByTaskError(f"raw_by_task dataset manifest is invalid JSON: {manifest_path}") from exc
    except OSError as exc:
        raise RawByTaskError(f"Cannot read raw_by_task dataset manifest: {manifest_path}") from exc
    if not isinstance(manifest, dict):
        raise RawByTaskError(f"raw_by_task dataset manifest must be a JSON object: {manifest_path}")
    schema_version = manifest.get("schema_version")
    if schema_version != RAW_BY_TASK_SCHEMA_VERSION:
        raise RawByTaskError(
            f"Unsupported raw_by_task manifest schema {schema_version!r} in {manifest_path}; "
            f"expected {RAW_BY_TASK_SCHEMA_VERSION!r}"
        )
    return manifest


def is_raw_by_task_dataset_dir(path: Path | str) -> bool:
    """Return true when ``path`` is a validated raw-by-task dataset directory."""

    try:
        load_raw_by_task_dataset_manifest(path)
    except RawByTaskError:
        return False
    return True


def find_raw_by_task_dataset_dir(path: Path | str | None) -> Optional[Path]:
    """Find the nearest raw-by-task dataset ancestor for a path, if any."""

    if path is None:
        return None
    current = Path(path).expanduser()
    if current.is_file() or current.name == "trajectory.json":
        current = current.parent
    for candidate in (current, *current.parents):
        manifest_path = candidate / "manifest.json"
        manifest = _load_optional_json(manifest_path)
        if manifest and manifest.get("schema_version") == RAW_BY_TASK_SCHEMA_VERSION:
            return candidate
    return None


def is_raw_by_task_trajectory_path(path: Path | str | None) -> bool:
    """Return true when ``path`` is inside a raw-by-task dataset."""

    return find_raw_by_task_dataset_dir(path) is not None


def load_raw_by_task_global_manifest(raw_by_task_root: Path | str | None = None) -> Optional[Dict[str, Any]]:
    """Load the optional global ``raw_by_task_manifest.json`` for a pack root."""

    root = _expanded_path(raw_by_task_root, DEFAULT_RAW_BY_TASK_ROOT)
    candidates = [root / RAW_BY_TASK_GLOBAL_MANIFEST, root.parent / RAW_BY_TASK_GLOBAL_MANIFEST]
    seen: set[Path] = set()
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        payload = _load_optional_json(candidate)
        if payload:
            return payload
    return None


def _dataset_from_dir(dataset_dir: Path) -> RawByTaskDataset:
    return RawByTaskDataset(path=dataset_dir, manifest=load_raw_by_task_dataset_manifest(dataset_dir))


def list_raw_by_task_datasets(raw_by_task_root: Path | str | None = None) -> List[RawByTaskDataset]:
    """List validated dataset directories under a raw-by-task root."""

    root = _expanded_path(raw_by_task_root, DEFAULT_RAW_BY_TASK_ROOT)
    if not root.exists():
        return []
    if root.is_dir() and (root / "manifest.json").exists():
        return [_dataset_from_dir(root)]
    datasets: List[RawByTaskDataset] = []
    for child in sorted(root.iterdir(), key=lambda item: item.name):
        if not child.is_dir() or not (child / "manifest.json").exists():
            continue
        datasets.append(_dataset_from_dir(child))
    return datasets


def _explicit_dataset_path(raw_by_task_root: Path, value: str) -> Path:
    raw = Path(value).expanduser()
    candidates: List[Path] = []
    if raw.exists():
        candidates.append(raw)
    if not raw.is_absolute():
        candidates.append(raw_by_task_root / raw)
        candidates.append(raw)
    else:
        candidates.append(raw)
    for candidate in candidates:
        if (candidate / "manifest.json").exists():
            return candidate
    return candidates[0]


def _matches_filter(value: str, filters: Optional[Sequence[str]], *, fuzzy: bool = False) -> bool:
    if not filters:
        return True
    for item in filters:
        needle = str(item)
        if value == needle:
            return True
        if fuzzy and needle and needle in value:
            return True
    return False


def _merged_superseded_names(
    datasets: Sequence[RawByTaskDataset],
    raw_by_task_root: Path,
) -> set[str]:
    names = {dataset.name for dataset in datasets}
    superseded: set[str] = set()
    for dataset in datasets:
        merged_from = dataset.manifest.get("merged_from")
        if isinstance(merged_from, list):
            superseded.update(str(item) for item in merged_from)
    global_manifest = load_raw_by_task_global_manifest(raw_by_task_root)
    groups = _as_dict(_as_dict(global_manifest).get("merged_dataset_groups"))
    for group in groups.values():
        group_data = _as_dict(group)
        merged_name = str(group_data.get("dataset") or "")
        if merged_name not in names:
            continue
        superseded.update(str(item) for item in _as_list(group_data.get("merged_from")))
    return superseded


def resolve_raw_by_task_datasets(
    *,
    raw_by_task_root: Path | str | None = None,
    raw_by_task_dataset: Optional[Sequence[str]] = None,
    backend: Optional[Sequence[str]] = None,
    model: Optional[Sequence[str]] = None,
    prefer_merged_openagent: bool = True,
) -> List[RawByTaskDataset]:
    """Resolve raw-by-task dataset selections to validated dataset entries."""

    root = _expanded_path(raw_by_task_root, DEFAULT_RAW_BY_TASK_ROOT)
    explicit = [str(item) for item in (raw_by_task_dataset or []) if str(item)]
    if explicit:
        datasets = []
        for value in explicit:
            dataset_path = _explicit_dataset_path(root, value)
            datasets.append(_dataset_from_dir(dataset_path))
        return datasets

    datasets = [
        dataset
        for dataset in list_raw_by_task_datasets(root)
        if _matches_filter(dataset.backend, backend)
        and _matches_filter(dataset.target_model, model, fuzzy=True)
    ]
    if prefer_merged_openagent and datasets:
        superseded = _merged_superseded_names(datasets, root)
        if superseded:
            datasets = [dataset for dataset in datasets if dataset.name not in superseded]
    if not datasets:
        filter_bits = []
        if backend:
            filter_bits.append(f"backend={list(backend)!r}")
        if model:
            filter_bits.append(f"model={list(model)!r}")
        suffix = f" matching {' '.join(filter_bits)}" if filter_bits else ""
        raise RawByTaskError(f"No raw_by_task datasets found under {root}{suffix}")
    return datasets


def normalize_raw_by_task_role(role: str) -> str:
    """Normalize public role aliases to raw layout buckets."""

    text = str(role or RAW_ROLE_ATTACKED).strip()
    if text in {"attacked", "attacked_attempt"}:
        return RAW_ROLE_ATTACKED
    if text in {"benign", "benign_baseline", "clean"}:
        return RAW_ROLE_BENIGN
    if text == RAW_ROLE_ALL:
        return RAW_ROLE_ALL
    raise RawByTaskError(f"Unsupported raw_by_task role: {role!r}")


def raw_by_task_role_from_roles(roles: Optional[Sequence[str]]) -> str:
    """Map utility-prep role filters to one raw-by-task collection role."""

    if not roles:
        return RAW_ROLE_ALL
    normalized = {normalize_raw_by_task_role(str(role)) for role in roles}
    if RAW_ROLE_ALL in normalized or len(normalized) > 1:
        return RAW_ROLE_ALL
    return next(iter(normalized))


def _allowed(value: str, filters: Optional[Sequence[str]]) -> bool:
    return not filters or value in {str(item) for item in filters}


def _suite_dirs(dataset_dir: Path, *, suites: Optional[Sequence[str]]) -> List[Path]:
    dirs: List[Path] = []
    for child in sorted(dataset_dir.iterdir(), key=lambda item: item.name):
        if not child.is_dir() or child.name.startswith("_"):
            continue
        if not _allowed(child.name, suites):
            continue
        dirs.append(child)
    return dirs


def _task_dirs(suite_dir: Path, *, task_ids: Optional[Sequence[str]]) -> List[Path]:
    dirs: List[Path] = []
    for child in sorted(suite_dir.iterdir(), key=lambda item: item.name):
        if not child.is_dir():
            continue
        if not _allowed(child.name, task_ids):
            continue
        dirs.append(child)
    return dirs


def _run_name_sort_key(name: str) -> tuple[int, str]:
    try:
        return (int(name.rsplit("_", 1)[1]), name)
    except (IndexError, ValueError):
        return (0, name)


def _run_sort_key(path: Path) -> tuple[int, str]:
    return _run_name_sort_key(path.parent.name)


def _attack_trajectory_paths(
    dataset: RawByTaskDataset,
    *,
    suites: Optional[Sequence[str]],
    task_ids: Optional[Sequence[str]],
) -> List[Path]:
    paths: List[Path] = []
    for suite_dir in _suite_dirs(dataset.path, suites=suites):
        for task_dir in _task_dirs(suite_dir, task_ids=task_ids):
            for run_dir in sorted(task_dir.iterdir(), key=lambda item: _run_name_sort_key(item.name)):
                if not run_dir.is_dir() or not run_dir.name.startswith("run_"):
                    continue
                trajectory = run_dir / "trajectory.json"
                if trajectory.exists():
                    paths.append(trajectory)
    return sorted(paths, key=lambda path: (*path.parent.parent.parts, _run_sort_key(path)))


def _baseline_exclusion(dataset: RawByTaskDataset, baseline_dir: Path) -> Dict[str, Any]:
    task_dir = baseline_dir.parent
    suite_dir = task_dir.parent
    return {
        "dataset": dataset.name,
        "path": str(baseline_dir),
        "reason": BASELINE_CACHE_ONLY_REASON,
        "message": "Baseline cache exists but no raw trajectory.json is present; excluded from utility prep.",
        "role": "benign_baseline",
        "suite": suite_dir.name,
        "task_id": task_dir.name,
    }


def _protected_value_exclusion(
    dataset: RawByTaskDataset,
    trajectory_path: Path,
    protected_value_scan: Dict[str, Any],
    *,
    reason: str = PROTECTED_VALUE_LEAK_REASON,
    message: str = "Protected value scanner detected a leak; excluded from clean utility selection.",
) -> Dict[str, Any]:
    baseline_dir = trajectory_path.parent
    task_dir = baseline_dir.parent
    suite_dir = task_dir.parent
    return {
        "dataset": dataset.name,
        "path": str(trajectory_path),
        "reason": reason,
        "message": message,
        "role": "benign_baseline",
        "suite": suite_dir.name,
        "task_id": task_dir.name,
        "protected_value_scan": protected_value_scan,
    }


def _raw_baseline_execution(trajectory: Dict[str, Any]) -> Dict[str, Any]:
    execution = dict(_as_dict(trajectory.get("execution")))
    scoring_inputs = _as_dict(trajectory.get("scoring_inputs"))
    snapshot = _as_dict(scoring_inputs.get("execution_feedback_snapshot"))
    for key, value in snapshot.items():
        if value is not None:
            execution[key] = value
    return execution


def _string_or_none(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def _load_current_task_payload(task_id: str) -> Optional[Dict[str, Any]]:
    if task_id in _CURRENT_TASK_PAYLOAD_CACHE:
        return _CURRENT_TASK_PAYLOAD_CACHE[task_id]
    task_file = _CURRENT_TASKS_ROOT / task_id / "task.yaml"
    if not task_file.is_file():
        _CURRENT_TASK_PAYLOAD_CACHE[task_id] = None
        return None
    try:
        from lib_tasks import TaskLoader

        task = TaskLoader(_CURRENT_TASKS_ROOT).load_task(task_file)
    except Exception:
        _CURRENT_TASK_PAYLOAD_CACHE[task_id] = None
        return None
    payload = dict(task.to_dict())
    if task.file_path:
        payload["source_path"] = str(task.file_path)
    payload.update(fingerprint_task_payload(payload))
    _CURRENT_TASK_PAYLOAD_CACHE[task_id] = payload
    return payload


def load_current_task_payload(task_id: str) -> Optional[Dict[str, Any]]:
    """Return a defensive copy of the current registry task payload, if available."""

    payload = _load_current_task_payload(task_id)
    return copy.deepcopy(payload) if payload is not None else None


def _task_payload_fingerprints(payload: Dict[str, Any]) -> Dict[str, Optional[str]]:
    algorithm = _string_or_none(payload.get("task_hash_algorithm"))
    prompt_hash = None
    spec_hash = None
    if algorithm == TASK_HASH_ALGORITHM:
        prompt_hash = _string_or_none(payload.get("task_prompt_sha256"))
        spec_hash = _string_or_none(payload.get("task_spec_sha256"))
    return {
        "algorithm": algorithm,
        "prompt_sha256": prompt_hash or task_prompt_sha256_from_payload(payload),
        "spec_sha256": spec_hash or task_spec_sha256_from_payload(payload),
        "clean_source_content_hash": clean_source_content_hash_from_payload(payload),
    }


def _raw_baseline_declares_source_task(
    trajectory_path: Path,
    trajectory: Dict[str, Any],
    embedded_payload: Dict[str, Any],
    task_id: str,
) -> bool:
    """Return true when a raw baseline sidecar/task payload identifies ``task_id``.

    Some historical clean baseline trajectories embed the synthetic
    ``*_baseline`` task payload and its full task-spec hash.  The raw-by-task
    layout and sidecars still identify the source task unambiguously, so the
    reader can safely use prompt/source-task checks instead of treating a broad
    task-spec hash drift as a hard exclusion.
    """

    embedded_frontmatter = _as_dict(embedded_payload.get("frontmatter"))
    run = _as_dict(trajectory.get("run"))
    context_metadata = _as_dict(run.get("context_metadata"))
    source_paths = _load_optional_json(trajectory_path.parent / "source_paths.json") or {}
    baseline_cache = _load_optional_json(trajectory_path.parent / "baseline_cache.json") or {}
    source_task_id = _string_or_none(
        trajectory.get("source_task_id")
        or embedded_payload.get("source_task_id")
        or context_metadata.get("baseline_task_id")
        or embedded_frontmatter.get("source_task_id")
        or source_paths.get("source_task_id")
        or baseline_cache.get("source_task_id")
        or embedded_frontmatter.get("id")
    )
    if source_task_id != task_id:
        return False
    clean_task_id = _string_or_none(
        trajectory.get("clean_task_id")
        or embedded_payload.get("clean_task_id")
        or source_paths.get("clean_task_id")
        or baseline_cache.get("clean_task_id")
    )
    return clean_task_id in {None, f"{task_id}_baseline"}


def _task_version_mismatch_exclusion(
    dataset: RawByTaskDataset,
    trajectory_path: Path,
    *,
    mismatch_fields: Sequence[str],
    embedded_fingerprint: Dict[str, Optional[str]],
    current_fingerprint: Dict[str, Optional[str]],
) -> Dict[str, Any]:
    baseline_dir = trajectory_path.parent
    task_dir = baseline_dir.parent
    suite_dir = task_dir.parent
    return {
        "dataset": dataset.name,
        "path": str(trajectory_path),
        "reason": TASK_VERSION_MISMATCH_REASON,
        "message": (
            "Baseline trajectory embeds a different task prompt/spec than the current "
            "task registry; excluded from clean utility selection."
        ),
        "role": "benign_baseline",
        "suite": suite_dir.name,
        "task_id": task_dir.name,
        "mismatch_fields": list(mismatch_fields),
        "task_hash_algorithm": TASK_HASH_ALGORITHM,
        "embedded_task_hash_algorithm": embedded_fingerprint.get("algorithm"),
        "embedded_task_prompt_sha256": embedded_fingerprint.get("prompt_sha256"),
        "current_task_prompt_sha256": current_fingerprint.get("prompt_sha256"),
        "embedded_task_spec_sha256": embedded_fingerprint.get("spec_sha256"),
        "current_task_spec_sha256": current_fingerprint.get("spec_sha256"),
        "embedded_clean_source_content_hash": embedded_fingerprint.get(
            "clean_source_content_hash"
        ),
        "current_clean_source_content_hash": current_fingerprint.get(
            "clean_source_content_hash"
        ),
    }


def _task_version_mismatch_for_raw_baseline(
    dataset: RawByTaskDataset,
    trajectory_path: Path,
) -> Optional[Dict[str, Any]]:
    try:
        trajectory = _load_json(trajectory_path)
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(trajectory, dict):
        return None
    try:
        task_id = trajectory_path.parents[1].name
    except IndexError:
        return None
    current_payload = _load_current_task_payload(task_id)
    if current_payload is None:
        return None
    embedded_payload = _as_dict(trajectory.get("task"))
    if not embedded_payload:
        return None

    embedded_fingerprint = _task_payload_fingerprints(embedded_payload)
    current_fingerprint = _task_payload_fingerprints(current_payload)
    embedded_has_hash = bool(
        embedded_fingerprint.get("algorithm")
        or _string_or_none(embedded_payload.get("task_prompt_sha256"))
        or _string_or_none(embedded_payload.get("task_spec_sha256"))
    )
    embedded_frontmatter = _as_dict(embedded_payload.get("frontmatter"))
    embedded_has_registry_provenance = bool(
        _string_or_none(embedded_payload.get("source_path"))
        or _string_or_none(embedded_frontmatter.get("id"))
        or _string_or_none(embedded_frontmatter.get("legacy_task_id"))
    )
    embedded_has_comparison_provenance = bool(
        embedded_has_hash
        or embedded_fingerprint.get("clean_source_content_hash")
        or embedded_has_registry_provenance
    )

    mismatch_fields: list[str] = []
    embedded_prompt = task_prompt_from_payload(embedded_payload)
    current_prompt = task_prompt_from_payload(current_payload)
    if (
        embedded_has_comparison_provenance
        and embedded_prompt
        and current_prompt
        and embedded_fingerprint.get("prompt_sha256") != current_fingerprint.get("prompt_sha256")
    ):
        mismatch_fields.append("prompt")

    embedded_clean_hash = embedded_fingerprint.get("clean_source_content_hash")
    current_clean_hash = current_fingerprint.get("clean_source_content_hash")
    if embedded_clean_hash and current_clean_hash and embedded_clean_hash != current_clean_hash:
        mismatch_fields.append("clean_source.content_hash")

    if (
        embedded_fingerprint.get("algorithm") == TASK_HASH_ALGORITHM
        and embedded_fingerprint.get("spec_sha256")
        and current_fingerprint.get("spec_sha256")
        and embedded_fingerprint.get("spec_sha256") != current_fingerprint.get("spec_sha256")
    ):
        prompt_matches = bool(
            embedded_fingerprint.get("prompt_sha256")
            and current_fingerprint.get("prompt_sha256")
            and embedded_fingerprint.get("prompt_sha256") == current_fingerprint.get("prompt_sha256")
        )
        clean_source_compatible = not (
            embedded_clean_hash and current_clean_hash and embedded_clean_hash != current_clean_hash
        )
        if not (
            prompt_matches
            and clean_source_compatible
            and _raw_baseline_declares_source_task(
                trajectory_path,
                trajectory,
                embedded_payload,
                task_id,
            )
        ):
            mismatch_fields.append("task_spec_sha256")

    if not mismatch_fields:
        return None
    return _task_version_mismatch_exclusion(
        dataset,
        trajectory_path,
        mismatch_fields=mismatch_fields,
        embedded_fingerprint=embedded_fingerprint,
        current_fingerprint=current_fingerprint,
    )


def _raw_baseline_identity(
    trajectory: Dict[str, Any],
    *,
    suite: str,
    task_id: str,
) -> Dict[str, Optional[str]]:
    task = _as_dict(trajectory.get("task"))
    canonical = _as_dict(trajectory.get("canonical"))
    run = _as_dict(trajectory.get("run"))
    context_metadata = _as_dict(run.get("context_metadata"))
    frontmatter = _as_dict(task.get("frontmatter"))
    trajectory_task_id = str(task.get("task_id") or canonical.get("task_id") or task_id)
    source_task_id = _string_or_none(
        trajectory.get("source_task_id")
        or task.get("source_task_id")
        or context_metadata.get("baseline_task_id")
        or frontmatter.get("source_task_id")
        or frontmatter.get("id")
    )
    clean_task_id = _string_or_none(
        trajectory.get("clean_task_id")
        or task.get("clean_task_id")
        or (trajectory_task_id if trajectory_task_id.endswith("_baseline") else None)
    )
    return {
        "suite": suite,
        "task_id": task_id,
        "trajectory_task_id": trajectory_task_id,
        "source_task_id": source_task_id,
        "clean_task_id": clean_task_id,
    }


def _path_candidate(value: Any, *, base: Path) -> Optional[Path]:
    if not isinstance(value, (str, Path)):
        return None
    text = str(value)
    if not text:
        return None
    path = Path(text).expanduser()
    if not path.is_absolute():
        path = base / path
    return path


def _raw_baseline_workspace_after(
    trajectory_path: Path,
    trajectory: Dict[str, Any],
    execution: Dict[str, Any],
) -> Optional[Path]:
    scoring_inputs = _as_dict(trajectory.get("scoring_inputs"))
    artifacts = _as_dict(trajectory.get("artifacts"))
    candidates = [
        _path_candidate(artifacts.get("workspace_after"), base=trajectory_path.parent),
        _path_candidate(scoring_inputs.get("replay_workspace_path"), base=trajectory_path.parent),
        _path_candidate(scoring_inputs.get("replay_workspace_absolute_path"), base=Path("/")),
        _path_candidate(artifacts.get("workspace_after_absolute"), base=Path("/")),
        _path_candidate(execution.get("workspace"), base=trajectory_path.parent),
        trajectory_path.parent / "workspace_after",
    ]
    for workspace in candidates:
        if workspace is not None and workspace.is_dir():
            return workspace
    return next((workspace for workspace in candidates if workspace is not None), None)


def _protected_value_scan_for_raw_baseline(trajectory_path: Path) -> Optional[Dict[str, Any]]:
    try:
        trajectory = _load_json(trajectory_path)
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(trajectory, dict):
        return None
    try:
        task_dir = trajectory_path.parents[1]
        suite_dir = trajectory_path.parents[2]
    except IndexError:
        return None

    try:
        from benchmark.protected_value_scanner import (
            protected_value_scan_error,
            scan_protected_value_sinks,
        )
        from benchmark.utility_checkers.types import UtilityCheckContext
    except Exception:
        return None

    execution = _raw_baseline_execution(trajectory)
    transcript = _as_dict(trajectory.get("transcript"))
    identity = _raw_baseline_identity(
        trajectory,
        suite=suite_dir.name,
        task_id=task_dir.name,
    )
    ctx = UtilityCheckContext(
        suite=str(identity["suite"] or ""),
        task_id=str(identity["task_id"] or ""),
        trajectory_task_id=_string_or_none(identity.get("trajectory_task_id")),
        source_task_id=_string_or_none(identity.get("source_task_id")),
        clean_task_id=_string_or_none(identity.get("clean_task_id")),
        api_audit=_as_dict(execution.get("api_audit")),
        transcript_entries=_as_list(transcript.get("entries")),
        workspace_after=_raw_baseline_workspace_after(trajectory_path, trajectory, execution),
        trajectory_path=trajectory_path,
    )
    try:
        scan = scan_protected_value_sinks(ctx)
    except Exception as exc:
        return protected_value_scan_error(ctx.task_id, exc)
    return scan if isinstance(scan, dict) else None


def _baseline_trajectory_paths(
    dataset: RawByTaskDataset,
    *,
    suites: Optional[Sequence[str]],
    task_ids: Optional[Sequence[str]],
    semantic_remap_excluded: bool = False,
) -> tuple[List[Path], List[Dict[str, Any]], List[Dict[str, Any]]]:
    paths: List[Path] = []
    excluded: List[Dict[str, Any]] = []
    semantic_remaps: List[Dict[str, Any]] = []
    baselines_root = dataset.path / "_baselines"
    if not baselines_root.is_dir():
        return paths, excluded, semantic_remaps
    for suite_dir in sorted(baselines_root.iterdir(), key=lambda item: item.name):
        if not suite_dir.is_dir() or not _allowed(suite_dir.name, suites):
            continue
        for task_dir in _task_dirs(suite_dir, task_ids=task_ids):
            baseline_dir = task_dir / "baseline"
            if not baseline_dir.is_dir():
                continue
            trajectory = baseline_dir / "trajectory.json"
            if trajectory.exists():
                task_version_mismatch = _task_version_mismatch_for_raw_baseline(
                    dataset,
                    trajectory,
                )
                if task_version_mismatch is not None:
                    excluded.append(task_version_mismatch)
                    continue
                paths.append(trajectory)
                continue
            if (baseline_dir / "baseline_cache.json").exists():
                excluded.append(_baseline_exclusion(dataset, baseline_dir))
    return sorted(paths, key=lambda path: path.parts), excluded, semantic_remaps


def _source_summary(
    datasets: Sequence[RawByTaskDataset],
    *,
    role: str,
    trajectory_count: int,
    excluded: Sequence[Dict[str, Any]],
    semantic_remaps: Sequence[Dict[str, Any]],
    semantic_remap_excluded: bool,
    suites: Optional[Sequence[str]],
    task_ids: Optional[Sequence[str]],
) -> Dict[str, Any]:
    roots = sorted({str(dataset.path.parent) for dataset in datasets})
    reason_counts = Counter(str(item.get("reason")) for item in excluded if item.get("reason"))
    remap_status_counts = Counter(
        str(item.get("semantic_remap_status") or "included") for item in semantic_remaps
    )
    for item in excluded:
        status = item.get("semantic_remap_status")
        if status:
            remap_status_counts[str(status)] += 1
    source = {
        "enabled": True,
        "root": roots[0] if len(roots) == 1 else roots,
        "role": role,
        "datasets": [dataset.summary() for dataset in datasets],
        "selected_trajectory_count": trajectory_count,
        "excluded_count": len(excluded),
        "excluded_by_reason": dict(sorted(reason_counts.items())),
        "semantic_remap_excluded_enabled": bool(semantic_remap_excluded),
        "semantic_remap_included_count": len(semantic_remaps),
        "semantic_remap_by_status": dict(sorted(remap_status_counts.items())),
    }
    if suites:
        source["suites"] = list(suites)
    if task_ids:
        source["task_ids"] = list(task_ids)
    return source


def collect_raw_by_task_trajectories(
    dataset_dirs: Sequence[Path | str | RawByTaskDataset],
    *,
    role: str = RAW_ROLE_ATTACKED,
    suites: Optional[Sequence[str]] = None,
    task_ids: Optional[Sequence[str]] = None,
    semantic_remap_excluded: bool = False,
) -> RawByTaskCollection:
    """Collect trajectory paths from raw-by-task datasets for a specific role."""

    normalized_role = normalize_raw_by_task_role(role)
    datasets: List[RawByTaskDataset] = []
    for item in dataset_dirs:
        if isinstance(item, RawByTaskDataset):
            datasets.append(item)
        else:
            datasets.append(_dataset_from_dir(Path(item).expanduser()))

    paths: List[Path] = []
    excluded: List[Dict[str, Any]] = []
    semantic_remaps: List[Dict[str, Any]] = []
    if normalized_role in {RAW_ROLE_ATTACKED, RAW_ROLE_ALL}:
        for dataset in datasets:
            paths.extend(_attack_trajectory_paths(dataset, suites=suites, task_ids=task_ids))
    if normalized_role in {RAW_ROLE_BENIGN, RAW_ROLE_ALL}:
        for dataset in datasets:
            baseline_paths, baseline_excluded, baseline_semantic_remaps = _baseline_trajectory_paths(
                dataset,
                suites=suites,
                task_ids=task_ids,
                semantic_remap_excluded=semantic_remap_excluded,
            )
            paths.extend(baseline_paths)
            excluded.extend(baseline_excluded)
            semantic_remaps.extend(baseline_semantic_remaps)

    deduped: List[Path] = []
    seen: set[Path] = set()
    for path in sorted(paths, key=lambda item: item.parts):
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        deduped.append(path)

    source = _source_summary(
        datasets,
        role=normalized_role,
        trajectory_count=len(deduped),
        excluded=excluded,
        semantic_remaps=semantic_remaps,
        semantic_remap_excluded=semantic_remap_excluded,
        suites=suites,
        task_ids=task_ids,
    )
    return RawByTaskCollection(
        trajectory_paths=deduped,
        excluded=excluded,
        source=source,
        semantic_remaps=semantic_remaps,
    )


__all__ = [
    "BASELINE_CACHE_ONLY_REASON",
    "DEFAULT_RAW_BY_TASK_ROOT",
    "PROTECTED_VALUE_LEAK_REASON",
    "PROTECTED_VALUE_SCAN_ERROR_REASON",
    "TASK_VERSION_MISMATCH_REASON",
    "RAW_BY_TASK_SCHEMA_VERSION",
    "RAW_ROLE_ALL",
    "RAW_ROLE_ATTACKED",
    "RAW_ROLE_BENIGN",
    "RawByTaskCollection",
    "RawByTaskDataset",
    "RawByTaskError",
    "collect_raw_by_task_trajectories",
    "find_raw_by_task_dataset_dir",
    "is_raw_by_task_dataset_dir",
    "is_raw_by_task_trajectory_path",
    "list_raw_by_task_datasets",
    "load_current_task_payload",
    "load_raw_by_task_dataset_manifest",
    "load_raw_by_task_global_manifest",
    "normalize_raw_by_task_role",
    "raw_by_task_role_from_roles",
    "resolve_raw_by_task_datasets",
]
