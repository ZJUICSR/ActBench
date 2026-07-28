"""Pack trajectory-first ActBench runner outputs into raw-by-task datasets."""

from __future__ import annotations

import argparse
import json
import shutil
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Optional, Sequence

from lib_training_artifacts import atomic_write_json, safe_artifact_name

from benchmark.artifacts import artifact_run_dir
from benchmark.raw_by_task import (
    DEFAULT_RAW_BY_TASK_ROOT,
    RAW_BY_TASK_SCHEMA_VERSION,
    RAW_ROLE_ATTACKED,
    RAW_ROLE_BENIGN,
    collect_raw_by_task_trajectories,
    load_raw_by_task_dataset_manifest,
)
from benchmark.trajectories import SUPPORTED_TRAJECTORY_SCHEMA_VERSIONS

PACK_RAW_BY_TASK_SCHEMA_VERSION = "actbench.pack_raw_by_task.v1"
TOOL_NAME = "actbench-pack-raw-by-task"


class PackRawByTaskError(ValueError):
    """Raised when runner output cannot be packed into raw_by_task format."""


@dataclass(frozen=True)
class PackRawByTaskOptions:
    """Options for converting runner outputs into one raw_by_task dataset."""

    dataset_name: str
    result_paths: Sequence[Path | str] = field(default_factory=tuple)
    output_dirs: Sequence[Path | str] = field(default_factory=tuple)
    artifact_roots: Sequence[Path | str] = field(default_factory=tuple)
    raw_by_task_root: Path | str = DEFAULT_RAW_BY_TASK_ROOT
    suites: Sequence[str] = field(default_factory=tuple)
    task_ids: Sequence[str] = field(default_factory=tuple)
    run_numbers: Sequence[int] = field(default_factory=tuple)
    include_baselines: bool = True
    dry_run: bool = False
    allow_existing: bool = False
    overwrite: bool = False
    validate: bool = True


@dataclass(frozen=True)
class _SourceRun:
    suite: str
    task_id: str
    run_number: int
    trajectory_path: Path
    trajectory: dict[str, Any]
    artifact_roots: tuple[Path, ...]
    artifact_run_dirs: tuple[Path, ...]
    training_artifact_key: Optional[str]
    task_entry: dict[str, Any]
    result_path: Optional[Path]
    output_dir: Optional[Path]
    backend: str
    model: str
    status: str
    timed_out: bool


@dataclass
class _BaselinePlan:
    suite: str
    task_id: str
    attacked_trajectory: Path
    trajectory_path: Optional[Path] = None
    trajectory: Optional[dict[str, Any]] = None
    cache_path: Optional[Path] = None
    artifact_roots: tuple[Path, ...] = ()
    artifact_run_dirs: tuple[Path, ...] = ()
    source_task_id: Optional[str] = None
    clean_task_id: Optional[str] = None


@dataclass
class _PackState:
    options: PackRawByTaskOptions
    dataset_dir: Path
    warnings: list[str] = field(default_factory=list)
    copy_summary: dict[str, int] = field(
        default_factory=lambda: {
            "files_copied": 0,
            "directories_copied": 0,
            "json_written": 0,
            "skipped_existing": 0,
            "planned_files": 0,
            "planned_directories": 0,
            "planned_json": 0,
        }
    )

    @property
    def dry_run(self) -> bool:
        return bool(self.options.dry_run)

    @property
    def allow_existing(self) -> bool:
        return bool(self.options.allow_existing)

    @property
    def overwrite(self) -> bool:
        return bool(self.options.overwrite)


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _string_or_none(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _safe_int(value: Any, default: int = 1) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    return max(1, number)


def _expanded_path(value: Path | str) -> Path:
    return Path(value).expanduser()


def _safe_dataset_name(value: str) -> str:
    safe = safe_artifact_name(value)
    if safe in {".", ".."} or not safe.strip("."):
        safe = safe.replace(".", "_") or "unknown"
    return safe


def _resolve_path(value: Any, bases: Iterable[Path]) -> Optional[Path]:
    text = _string_or_none(value)
    if text is None:
        return None
    raw = Path(text).expanduser()
    if raw.is_absolute():
        return raw
    for base in bases:
        candidate = base / raw
        if candidate.exists():
            return candidate
    base_list = list(bases)
    return (base_list[0] / raw) if base_list else raw


def _path_candidates(value: Any, bases: Iterable[Path]) -> list[Path]:
    text = _string_or_none(value)
    if text is None:
        return []
    raw = Path(text).expanduser()
    if raw.is_absolute():
        return [raw]
    candidates: list[Path] = []
    seen: set[Path] = set()
    for base in bases:
        candidate = base / raw
        if candidate not in seen:
            seen.add(candidate)
            candidates.append(candidate)
    if raw not in seen:
        candidates.append(raw)
    return candidates


def _first_existing_file(candidates: Iterable[Optional[Path]]) -> Optional[Path]:
    for candidate in candidates:
        if candidate is not None and candidate.is_file():
            return candidate
    return None


def _first_existing_dir(candidates: Iterable[Optional[Path]]) -> Optional[Path]:
    for candidate in candidates:
        if candidate is not None and candidate.is_dir():
            return candidate
    return None


def _unique_paths(paths: Iterable[Optional[Path]]) -> tuple[Path, ...]:
    unique: list[Path] = []
    seen: set[Path] = set()
    for raw in paths:
        if raw is None:
            continue
        path = Path(raw).expanduser()
        key = path.resolve() if path.exists() else path
        if key in seen:
            continue
        seen.add(key)
        unique.append(path)
    return tuple(unique)


def _load_json_object(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise PackRawByTaskError(f"JSON payload is not an object: {path}")
    return payload


def _load_optional_json_object(path: Optional[Path]) -> Optional[dict[str, Any]]:
    if path is None or not path.is_file():
        return None
    try:
        payload = _load_json_object(path)
    except (OSError, json.JSONDecodeError, PackRawByTaskError):
        return None
    return payload


def _is_supported_trajectory(payload: dict[str, Any]) -> bool:
    return payload.get("schema_version") in SUPPORTED_TRAJECTORY_SCHEMA_VERSIONS


def _normalize_role(payload: dict[str, Any]) -> str:
    canonical = _as_dict(payload.get("canonical"))
    task = _as_dict(payload.get("task"))
    return str(payload.get("role") or canonical.get("role") or task.get("role") or "")


def _is_attacked_trajectory(payload: dict[str, Any]) -> bool:
    role = _normalize_role(payload)
    return role in {"", "attacked", "attacked_attempt"}


def _is_benign_baseline_trajectory(payload: dict[str, Any]) -> bool:
    return _normalize_role(payload) == "benign_baseline" and _is_supported_trajectory(payload)


def _parse_canonical_parts(path: Path | str) -> tuple[Optional[str], Optional[str], Optional[int]]:
    parts = list(Path(path).parts)
    try:
        index = parts.index("trajectories")
    except ValueError:
        return None, None, None
    try:
        suite = parts[index + 1]
        task_id = parts[index + 2]
        run_name = parts[index + 4]
    except IndexError:
        return None, None, None
    if index + 3 >= len(parts) or parts[index + 3] != "runs":
        return None, None, None
    if not run_name.startswith("run_"):
        return suite, task_id, None
    return suite, task_id, _safe_int(run_name.removeprefix("run_"), 1)


def _parse_slot_id(slot_id: Any) -> tuple[Optional[str], Optional[str], Optional[int]]:
    text = _string_or_none(slot_id)
    if text is None:
        return None, None, None
    parts = text.split("/")
    if len(parts) < 3:
        return None, None, None
    run_part = parts[2]
    run_number = _safe_int(run_part.removeprefix("run_"), 1) if run_part.startswith("run_") else None
    return parts[0] or None, parts[1] or None, run_number


def _suite_from_task_id(task_id: str) -> str:
    parts = str(task_id).split("_")
    if len(parts) >= 2 and parts[0] == "task" and parts[1]:
        return parts[1]
    return "unknown_suite"


def _trajectory_task_id(trajectory: dict[str, Any]) -> Optional[str]:
    task = _as_dict(trajectory.get("task"))
    canonical = _as_dict(trajectory.get("canonical"))
    return _string_or_none(task.get("task_id") or canonical.get("task_id"))


def _trajectory_suite(trajectory: dict[str, Any]) -> Optional[str]:
    canonical = _as_dict(trajectory.get("canonical"))
    run = _as_dict(trajectory.get("run"))
    context = _as_dict(run.get("context_metadata"))
    task = _as_dict(trajectory.get("task"))
    frontmatter = _as_dict(task.get("frontmatter"))
    return _string_or_none(canonical.get("suite") or context.get("suite") or frontmatter.get("behavior_id"))


def _trajectory_run_number(trajectory: dict[str, Any]) -> Optional[int]:
    canonical = _as_dict(trajectory.get("canonical"))
    run = _as_dict(trajectory.get("run"))
    value = canonical.get("run_number") or run.get("run_number") or run.get("run_index")
    return _safe_int(value, 1) if value is not None else None


def _source_identity(
    *,
    task_entry: dict[str, Any],
    trajectory: dict[str, Any],
    trajectory_path: Path,
) -> tuple[str, str, int]:
    refs = _as_dict(task_entry.get("trajectory"))
    suite, task_id, run_number = _parse_slot_id(refs.get("canonical_slot_id"))
    if suite is None or task_id is None or run_number is None:
        for value in (
            refs.get("canonical_path"),
            refs.get("canonical_absolute"),
            _as_dict(trajectory.get("canonical")).get("trajectory_path"),
            trajectory_path,
        ):
            path_suite, path_task, path_run = _parse_canonical_parts(Path(str(value)))
            suite = suite or path_suite
            task_id = task_id or path_task
            run_number = run_number or path_run
    task_id = task_id or _string_or_none(task_entry.get("task_id")) or _trajectory_task_id(trajectory)
    suite = suite or _trajectory_suite(trajectory)
    if task_id is None:
        task_id = "unknown_task"
    if suite is None:
        suite = _string_or_none(task_entry.get("behavior_id")) or _suite_from_task_id(task_id)
    run_number = run_number or _trajectory_run_number(trajectory) or _run_number_from_entry(task_entry)
    return safe_artifact_name(suite), safe_artifact_name(task_id), _safe_int(run_number, 1)


def _run_number_from_entry(task_entry: dict[str, Any]) -> int:
    backend_metadata = _as_dict(task_entry.get("backend_metadata"))
    for key in ("run_number", "run_index"):
        if task_entry.get(key) is not None:
            return _safe_int(task_entry.get(key), 1)
        if backend_metadata.get(key) is not None:
            return _safe_int(backend_metadata.get(key), 1)
    return 1


def _training_key_from_trajectory(trajectory: dict[str, Any]) -> Optional[str]:
    run = _as_dict(trajectory.get("run"))
    execution = _as_dict(trajectory.get("execution"))
    return _string_or_none(
        run.get("training_artifact_key")
        or execution.get("training_artifact_key")
        or trajectory.get("trajectory_id")
    )


def _artifact_roots_from_payloads(
    *,
    artifacts: dict[str, Any],
    bases: Sequence[Path],
) -> tuple[Path, ...]:
    candidates = list(_path_candidates(artifacts.get("artifact_root"), bases))
    return _unique_paths(candidates)


def _run_dirs_for_key(artifact_roots: Sequence[Path], training_key: Optional[str]) -> tuple[Path, ...]:
    if not training_key:
        return ()
    return _unique_paths(root / artifact_run_dir(training_key) for root in artifact_roots)


def _infer_artifact_root_from_trajectory_path(path: Path) -> Optional[Path]:
    resolved = path.resolve()
    if resolved.name != "trajectory.json" or len(resolved.parents) < 3:
        return None
    runs_dir = resolved.parent.parent
    if runs_dir.name != "runs":
        return None
    return runs_dir.parent


def _metadata_backend(entry: dict[str, Any], aggregate: dict[str, Any], trajectory: dict[str, Any]) -> str:
    backend = _as_dict(trajectory.get("backend"))
    execution = _as_dict(trajectory.get("execution"))
    return str(
        entry.get("backend")
        or backend.get("name")
        or execution.get("backend")
        or aggregate.get("backend")
        or "unknown"
    )


def _metadata_model(entry: dict[str, Any], aggregate: dict[str, Any], trajectory: dict[str, Any]) -> str:
    backend = _as_dict(trajectory.get("backend"))
    scoring_inputs = _as_dict(trajectory.get("scoring_inputs"))
    backend_metadata = _as_dict(entry.get("backend_metadata"))
    return str(
        backend_metadata.get("model")
        or backend.get("model")
        or scoring_inputs.get("target_model")
        or aggregate.get("model")
        or "unknown"
    )


def _execution_status(entry: dict[str, Any], trajectory: dict[str, Any]) -> tuple[str, bool]:
    execution = _as_dict(trajectory.get("execution"))
    status = str(entry.get("status") or execution.get("status") or "unknown")
    timed_out = bool(entry.get("timed_out") or execution.get("timed_out"))
    return status, timed_out


def _aggregate_output_dir(result_path: Path, aggregate: dict[str, Any]) -> Path:
    raw = _string_or_none(aggregate.get("canonical_output_dir"))
    if raw is None:
        return result_path.parent
    path = Path(raw).expanduser()
    if path.is_absolute():
        return path
    candidates = [result_path.parent / path, Path.cwd() / path]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return result_path.parent / path


def _aggregate_artifact_roots(
    *,
    aggregate: dict[str, Any],
    result_path: Path,
    output_dir: Path,
    explicit_roots: Sequence[Path],
) -> tuple[Path, ...]:
    bases = (result_path.parent, output_dir, Path.cwd())
    candidates: list[Path] = list(explicit_roots)
    candidates.extend(_path_candidates(aggregate.get("training_artifact_dir"), bases))
    return _unique_paths(candidates)


def _trajectory_candidates_from_entry(
    *,
    task_entry: dict[str, Any],
    output_dir: Path,
    artifact_roots: Sequence[Path],
) -> list[Path]:
    refs = _as_dict(task_entry.get("trajectory"))
    candidates: list[Path] = []
    candidates.extend(_path_candidates(refs.get("canonical_absolute"), (Path.cwd(), output_dir)))
    candidates.extend(_path_candidates(refs.get("canonical_path"), (output_dir, Path.cwd())))
    candidates.extend(_path_candidates(refs.get("attempt_absolute"), (Path.cwd(),)))
    for root in artifact_roots:
        candidates.extend(_path_candidates(refs.get("attempt_path"), (root,)))
        candidates.extend(_path_candidates(refs.get("legacy_path"), (root,)))
    training_key = _string_or_none(task_entry.get("training_artifact_key"))
    if training_key:
        for run_dir in _run_dirs_for_key(artifact_roots, training_key):
            candidates.append(run_dir / "trajectory.json")
    return candidates


def _source_run_from_path(
    *,
    path: Path,
    task_entry: dict[str, Any],
    aggregate: dict[str, Any],
    result_path: Optional[Path],
    output_dir: Optional[Path],
    artifact_roots: Sequence[Path],
    warnings: list[str],
) -> Optional[_SourceRun]:
    try:
        trajectory = _load_json_object(path)
    except (OSError, json.JSONDecodeError, PackRawByTaskError) as exc:
        warnings.append(f"Skipping unreadable trajectory {path}: {exc}")
        return None
    if not _is_supported_trajectory(trajectory):
        warnings.append(
            f"Skipping unsupported trajectory schema in {path}: {trajectory.get('schema_version')!r}"
        )
        return None
    if not _is_attacked_trajectory(trajectory):
        warnings.append(f"Skipping non-attacked trajectory {path}: role={_normalize_role(trajectory)!r}")
        return None

    suite, task_id, run_number = _source_identity(
        task_entry=task_entry,
        trajectory=trajectory,
        trajectory_path=path,
    )
    artifacts = _as_dict(trajectory.get("artifacts"))
    bases = tuple(item for item in (Path.cwd(), path.parent, output_dir) if item is not None)
    roots = list(artifact_roots)
    roots.extend(_artifact_roots_from_payloads(artifacts=artifacts, bases=bases))
    roots.append(_infer_artifact_root_from_trajectory_path(path))
    artifact_root_tuple = _unique_paths(roots)
    training_key = _string_or_none(task_entry.get("training_artifact_key")) or _training_key_from_trajectory(
        trajectory
    )
    run_dirs = list(_run_dirs_for_key(artifact_root_tuple, training_key))
    if path.parent.parent.name == "runs":
        run_dirs.append(path.parent)
    status, timed_out = _execution_status(task_entry, trajectory)
    return _SourceRun(
        suite=suite,
        task_id=task_id,
        run_number=run_number,
        trajectory_path=path,
        trajectory=trajectory,
        artifact_roots=artifact_root_tuple,
        artifact_run_dirs=_unique_paths(run_dirs),
        training_artifact_key=training_key,
        task_entry=task_entry,
        result_path=result_path,
        output_dir=output_dir,
        backend=_metadata_backend(task_entry, aggregate, trajectory),
        model=_metadata_model(task_entry, aggregate, trajectory),
        status=status,
        timed_out=timed_out,
    )


def _first_source_run_from_candidates(
    *,
    candidates: Sequence[Path],
    task_entry: dict[str, Any],
    aggregate: dict[str, Any],
    result_path: Optional[Path],
    output_dir: Optional[Path],
    artifact_roots: Sequence[Path],
    warnings: list[str],
) -> Optional[_SourceRun]:
    seen: set[Path] = set()
    found_existing = False
    for candidate in candidates:
        if not candidate.is_file():
            continue
        key = candidate.resolve()
        if key in seen:
            continue
        seen.add(key)
        found_existing = True
        source = _source_run_from_path(
            path=candidate,
            task_entry=task_entry,
            aggregate=aggregate,
            result_path=result_path,
            output_dir=output_dir,
            artifact_roots=artifact_roots,
            warnings=warnings,
        )
        if source is not None:
            return source
    if not found_existing:
        return None
    return None


def _discover_from_result(
    result_path: Path,
    *,
    explicit_roots: Sequence[Path],
    warnings: list[str],
) -> list[_SourceRun]:
    aggregate = _load_json_object(result_path)
    output_dir = _aggregate_output_dir(result_path, aggregate)
    artifact_roots = _aggregate_artifact_roots(
        aggregate=aggregate,
        result_path=result_path,
        output_dir=output_dir,
        explicit_roots=explicit_roots,
    )
    runs: list[_SourceRun] = []
    tasks = _as_list(aggregate.get("tasks"))
    for item in tasks:
        task_entry = item if isinstance(item, dict) else {}
        candidates = _trajectory_candidates_from_entry(
            task_entry=task_entry,
            output_dir=output_dir,
            artifact_roots=artifact_roots,
        )
        source = _first_source_run_from_candidates(
            candidates=candidates,
            task_entry=task_entry,
            aggregate=aggregate,
            result_path=result_path,
            output_dir=output_dir,
            artifact_roots=artifact_roots,
            warnings=warnings,
        )
        if source is None:
            task_id = task_entry.get("task_id") or "unknown_task"
            warnings.append(f"No usable trajectory found for aggregate task entry {task_id!r} in {result_path}")
            continue
        runs.append(source)
    return runs


def _trajectory_index_paths(
    output_dir: Path,
    *,
    explicit_roots: Sequence[Path],
) -> list[tuple[Path, dict[str, Any]]]:
    index_path = output_dir / "trajectory_index.json"
    index = _load_optional_json_object(index_path)
    if not index:
        return []
    entries = _as_dict(index.get("entries"))
    paths: list[tuple[Path, dict[str, Any]]] = []
    for value in entries.values():
        entry = value if isinstance(value, dict) else {}
        role = str(entry.get("role") or "attacked_attempt")
        if role not in {"attacked", "attacked_attempt"}:
            continue
        artifact_roots = _unique_paths(
            [*explicit_roots, *_path_candidates(entry.get("artifact_root"), (output_dir, Path.cwd()))]
        )
        candidates: list[Path] = []
        candidates.extend(_path_candidates(entry.get("canonical_trajectory_absolute"), (Path.cwd(),)))
        candidates.extend(_path_candidates(entry.get("canonical_trajectory_path"), (output_dir, Path.cwd())))
        candidates.extend(_path_candidates(entry.get("trajectory_path"), (output_dir, Path.cwd())))
        candidates.extend(_path_candidates(entry.get("attempt_trajectory_absolute"), (Path.cwd(),)))
        candidates.extend(
            _path_candidates(entry.get("attempt_trajectory_path"), (*artifact_roots, output_dir, Path.cwd()))
        )
        seen_candidates: set[Path] = set()
        for candidate in candidates:
            if not candidate.is_file():
                continue
            key = candidate.resolve()
            if key in seen_candidates:
                continue
            seen_candidates.add(key)
            paths.append((candidate, entry))
    return paths


def _scan_canonical_paths(output_dir: Path) -> list[Path]:
    root = output_dir / "trajectories"
    if not root.is_dir():
        return []
    return sorted(root.glob("*/*/runs/run_*/trajectory.json"))


def _discover_from_output_dir(
    output_dir: Path,
    *,
    explicit_roots: Sequence[Path],
    warnings: list[str],
) -> list[_SourceRun]:
    runs: list[_SourceRun] = []
    path_entries = list(_trajectory_index_paths(output_dir, explicit_roots=explicit_roots))
    seen_paths = {path.resolve() for path, _entry in path_entries if path.exists()}
    for path in _scan_canonical_paths(output_dir):
        key = path.resolve()
        if key in seen_paths:
            continue
        seen_paths.add(key)
        path_entries.append((path, {}))
    for path, entry in path_entries:
        task_entry: dict[str, Any] = {
            "task_id": entry.get("task_id"),
            "training_artifact_key": entry.get("training_artifact_key"),
            "status": entry.get("status"),
            "timed_out": entry.get("timed_out"),
            "backend_metadata": {
                "run_number": entry.get("run_number"),
                "run_index": entry.get("run_index"),
                "model": entry.get("model"),
            },
            "trajectory": {
                "canonical_slot_id": entry.get("slot_id"),
                "canonical_path": entry.get("canonical_trajectory_path") or entry.get("trajectory_path"),
                "canonical_absolute": entry.get("canonical_trajectory_absolute"),
                "attempt_path": entry.get("attempt_trajectory_path"),
                "attempt_absolute": entry.get("attempt_trajectory_absolute"),
            },
        }
        aggregate = {"backend": entry.get("backend"), "model": entry.get("model")}
        source = _source_run_from_path(
            path=path,
            task_entry=task_entry,
            aggregate=aggregate,
            result_path=None,
            output_dir=output_dir,
            artifact_roots=explicit_roots,
            warnings=warnings,
        )
        if source is not None:
            runs.append(source)
    return runs


def _matches_filter(value: str, filters: Sequence[str]) -> bool:
    return not filters or value in {str(item) for item in filters}


def _filter_runs(runs: Sequence[_SourceRun], options: PackRawByTaskOptions) -> list[_SourceRun]:
    run_numbers = {_safe_int(value, 1) for value in options.run_numbers}
    selected: list[_SourceRun] = []
    for run in runs:
        if not _matches_filter(run.suite, options.suites):
            continue
        if not _matches_filter(run.task_id, options.task_ids):
            continue
        if run_numbers and run.run_number not in run_numbers:
            continue
        selected.append(run)
    return selected


def _dedupe_runs(runs: Sequence[_SourceRun], warnings: list[str]) -> list[_SourceRun]:
    selected: list[_SourceRun] = []
    seen: set[tuple[str, str, int]] = set()
    for run in runs:
        key = (run.suite, run.task_id, run.run_number)
        if key in seen:
            warnings.append(
                "Skipping duplicate raw_by_task slot "
                f"{run.suite}/{run.task_id}/run_{run.run_number}: {run.trajectory_path}"
            )
            continue
        seen.add(key)
        selected.append(run)
    return selected


def _copy_file(state: _PackState, source: Path, dest: Path, *, label: str) -> bool:
    if state.dry_run:
        state.copy_summary["planned_files"] += 1
        return True
    if dest.exists():
        if state.overwrite:
            if dest.is_dir():
                shutil.rmtree(dest)
        elif state.allow_existing:
            state.copy_summary["skipped_existing"] += 1
            return False
        else:
            raise PackRawByTaskError(f"Destination {label} already exists: {dest}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, dest)
    state.copy_summary["files_copied"] += 1
    return True


def _copy_dir_missing_only(source: Path, dest: Path, state: _PackState) -> bool:
    copied_any = False
    for item in sorted(source.rglob("*")):
        rel = item.relative_to(source)
        target = dest / rel
        if item.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        if not item.is_file():
            continue
        if target.exists():
            state.copy_summary["skipped_existing"] += 1
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item, target)
        state.copy_summary["files_copied"] += 1
        copied_any = True
    return copied_any


def _copy_dir(state: _PackState, source: Path, dest: Path, *, label: str) -> bool:
    if state.dry_run:
        state.copy_summary["planned_directories"] += 1
        return True
    if dest.exists():
        if state.overwrite:
            if dest.is_dir():
                shutil.rmtree(dest)
            else:
                dest.unlink()
        elif state.allow_existing:
            return _copy_dir_missing_only(source, dest, state)
        else:
            raise PackRawByTaskError(f"Destination {label} already exists: {dest}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, dest)
    state.copy_summary["directories_copied"] += 1
    return True


def _write_json_sidecar(state: _PackState, payload: Any, dest: Path, *, label: str) -> bool:
    if state.dry_run:
        state.copy_summary["planned_json"] += 1
        return True
    if dest.exists():
        if state.overwrite:
            if dest.is_dir():
                shutil.rmtree(dest)
        elif state.allow_existing:
            state.copy_summary["skipped_existing"] += 1
            return False
        else:
            raise PackRawByTaskError(f"Destination {label} already exists: {dest}")
    atomic_write_json(dest, payload)
    state.copy_summary["json_written"] += 1
    return True


def _sidecar_file_candidates(run: _SourceRun, artifact_key: str, relative: Path) -> list[Path]:
    artifacts = _as_dict(run.trajectory.get("artifacts"))
    candidates: list[Path] = []
    candidates.extend(run_dir / relative for run_dir in run.artifact_run_dirs)
    candidates.extend(_path_candidates(artifacts.get(f"{artifact_key}_absolute"), (Path.cwd(),)))
    for root in run.artifact_roots:
        candidates.extend(_path_candidates(artifacts.get(artifact_key), (root,)))
    candidates.extend(_path_candidates(artifacts.get(artifact_key), (run.trajectory_path.parent, Path.cwd())))
    candidates.append(run.trajectory_path.parent / relative)
    return candidates


def _workspace_candidates(run: _SourceRun) -> list[Path]:
    artifacts = _as_dict(run.trajectory.get("artifacts"))
    scoring_inputs = _as_dict(run.trajectory.get("scoring_inputs"))
    candidates: list[Path] = []
    candidates.extend(run_dir / "workspace_after" for run_dir in run.artifact_run_dirs)
    candidates.extend(_path_candidates(artifacts.get("workspace_after_absolute"), (Path.cwd(),)))
    candidates.extend(
        _path_candidates(scoring_inputs.get("replay_workspace_absolute_path"), (Path.cwd(),))
    )
    for root in run.artifact_roots:
        candidates.extend(_path_candidates(artifacts.get("workspace_after"), (root,)))
        candidates.extend(_path_candidates(scoring_inputs.get("replay_workspace_path"), (root,)))
    candidates.extend(
        _path_candidates(artifacts.get("workspace_after"), (run.trajectory_path.parent, Path.cwd()))
    )
    candidates.append(run.trajectory_path.parent / "workspace_after")
    return candidates


def _copy_run_sidecars(state: _PackState, run: _SourceRun, dest_run_dir: Path) -> None:
    workspace = _first_existing_dir(_workspace_candidates(run))
    if workspace is not None:
        _copy_dir(state, workspace, dest_run_dir / "workspace_after", label="workspace_after")
    else:
        state.warnings.append(f"No workspace_after sidecar found for {run.trajectory_path}")

    execution = _as_dict(run.trajectory.get("execution"))
    for artifact_key, relative, inline_key in (
        ("api_audit", Path("api") / "audit.json", "api_audit"),
        ("api_endpoints", Path("api") / "endpoints.json", "api_endpoints"),
    ):
        source = _first_existing_file(_sidecar_file_candidates(run, artifact_key, relative))
        dest = dest_run_dir / relative
        if source is not None:
            _copy_file(state, source, dest, label=artifact_key)
            continue
        inline = execution.get(inline_key)
        if isinstance(inline, dict):
            _write_json_sidecar(state, inline, dest, label=artifact_key)


def _cache_path_candidates_from_payload(
    payload: dict[str, Any],
    *,
    bases: Sequence[Path],
) -> list[Path]:
    candidates: list[Path] = []
    for key in ("cache_path", "baseline_cache_path"):
        candidates.extend(_path_candidates(payload.get(key), bases))
    return candidates


def _baseline_artifact_roots(
    artifacts: dict[str, Any],
    *,
    run: _SourceRun,
    bases: Sequence[Path],
) -> tuple[Path, ...]:
    roots = list(run.artifact_roots)
    roots.extend(_artifact_roots_from_payloads(artifacts=artifacts, bases=bases))
    return _unique_paths(roots)


def _baseline_trajectory_candidates(
    *,
    baseline_payload: dict[str, Any],
    run: _SourceRun,
    bases: Sequence[Path],
) -> tuple[list[Path], tuple[Path, ...], Optional[str]]:
    artifacts = _as_dict(baseline_payload.get("artifacts"))
    roots = _baseline_artifact_roots(artifacts, run=run, bases=bases)
    training_key = _string_or_none(baseline_payload.get("training_artifact_key"))
    candidates: list[Path] = []
    candidates.extend(_path_candidates(artifacts.get("trajectory_absolute"), bases))
    candidates.extend(_path_candidates(artifacts.get("trajectory"), roots or bases))
    candidates.extend(_path_candidates(artifacts.get("run_dir"), roots or bases))
    candidates = [path / "trajectory.json" if path.name != "trajectory.json" else path for path in candidates]
    if training_key:
        for run_dir in _run_dirs_for_key(roots or run.artifact_roots, training_key):
            candidates.append(run_dir / "trajectory.json")
    return candidates, roots, training_key


def _is_baseline_cache_payload(payload: dict[str, Any]) -> bool:
    schema_version = str(payload.get("schema_version") or "")
    return _normalize_role(payload) == "benign_baseline" or schema_version.startswith(
        "actbench.benign_baseline."
    )


def _first_existing_baseline_cache(candidates: Iterable[Path]) -> Optional[Path]:
    for candidate in candidates:
        if not candidate.is_file():
            continue
        payload = _load_optional_json_object(candidate)
        if payload is not None and _is_baseline_cache_payload(payload):
            return candidate
    return None


def _baseline_payloads_for_run(run: _SourceRun) -> tuple[list[dict[str, Any]], list[Path]]:
    payloads: list[dict[str, Any]] = []
    cache_paths: list[Path] = []
    bases = _unique_paths(
        item for item in (run.trajectory_path.parent, run.output_dir, *run.artifact_roots, Path.cwd()) if item is not None
    )

    task_baseline = _as_dict(run.task_entry.get("baseline"))
    if task_baseline:
        payloads.append(task_baseline)
        cache_paths.extend(_cache_path_candidates_from_payload(task_baseline, bases=bases))

    scoring_inputs = _as_dict(run.trajectory.get("scoring_inputs"))
    scoring_baseline = _as_dict(scoring_inputs.get("baseline"))
    if scoring_baseline:
        payloads.append(scoring_baseline)
        cache_paths.extend(_cache_path_candidates_from_payload(scoring_baseline, bases=bases))

    cache_paths.extend(_path_candidates(scoring_inputs.get("baseline_cache_path"), bases))
    artifact_path = _resolve_path(scoring_inputs.get("baseline_artifact_path"), bases)
    artifact_payload = _load_optional_json_object(artifact_path)
    if artifact_payload:
        if _is_baseline_cache_payload(artifact_payload):
            payloads.append(artifact_payload)
            cache_paths.append(artifact_path)  # usable cache-only evidence if raw trajectory is unavailable
            cache_paths.extend(_cache_path_candidates_from_payload(artifact_payload, bases=bases))
        else:
            # Do not preserve arbitrary JSON as a benign baseline cache.
            pass

    seen_cache_payloads: set[Path] = set()
    for cache_path in _unique_paths(cache_paths):
        cache_payload = _load_optional_json_object(cache_path)
        if cache_payload is None or not _is_baseline_cache_payload(cache_payload):
            continue
        key = cache_path.resolve() if cache_path.exists() else cache_path
        if key in seen_cache_payloads:
            continue
        seen_cache_payloads.add(key)
        payloads.append(cache_payload)
        cache_paths.extend(_cache_path_candidates_from_payload(cache_payload, bases=bases))
    return payloads, cache_paths


def _baseline_identity(payload: dict[str, Any], *, suite: str, task_id: str) -> tuple[Optional[str], Optional[str]]:
    task = _as_dict(payload.get("task"))
    run = _as_dict(payload.get("run"))
    context = _as_dict(run.get("context_metadata"))
    frontmatter = _as_dict(task.get("frontmatter"))
    source_task_id = _string_or_none(
        payload.get("source_task_id")
        or task.get("source_task_id")
        or context.get("baseline_task_id")
        or frontmatter.get("source_task_id")
        or task_id
    )
    clean_task_id = _string_or_none(
        payload.get("clean_task_id")
        or task.get("clean_task_id")
        or (task.get("task_id") if str(task.get("task_id") or "").endswith("_baseline") else None)
    )
    return source_task_id, clean_task_id or f"{source_task_id}_baseline" if source_task_id else None


def _select_baseline_plan(
    suite: str,
    task_id: str,
    runs: Sequence[_SourceRun],
    warnings: list[str],
) -> _BaselinePlan:
    first_run = runs[0]
    all_cache_paths: list[Path] = []
    for run in runs:
        bases = _unique_paths(
            item
            for item in (run.trajectory_path.parent, run.output_dir, *run.artifact_roots, Path.cwd())
            if item is not None
        )
        payloads, cache_paths = _baseline_payloads_for_run(run)
        all_cache_paths.extend(cache_paths)
        for payload in payloads:
            candidates, roots, training_key = _baseline_trajectory_candidates(
                baseline_payload=payload,
                run=run,
                bases=bases,
            )
            seen_candidates: set[Path] = set()
            for candidate in candidates:
                if not candidate.is_file():
                    continue
                key = candidate.resolve()
                if key in seen_candidates:
                    continue
                seen_candidates.add(key)
                trajectory_payload = _load_optional_json_object(candidate)
                if trajectory_payload is None:
                    continue
                if not _is_benign_baseline_trajectory(trajectory_payload):
                    warnings.append(
                        f"Ignoring non-benign baseline trajectory candidate {candidate}: "
                        f"role={_normalize_role(trajectory_payload)!r}"
                    )
                    continue
                source_task_id, clean_task_id = _baseline_identity(
                    trajectory_payload,
                    suite=suite,
                    task_id=task_id,
                )
                run_dirs = list(_run_dirs_for_key(roots or run.artifact_roots, training_key))
                if candidate.parent.parent.name == "runs":
                    run_dirs.append(candidate.parent)
                return _BaselinePlan(
                    suite=suite,
                    task_id=task_id,
                    attacked_trajectory=run.trajectory_path,
                    trajectory_path=candidate,
                    trajectory=trajectory_payload,
                    cache_path=_first_existing_baseline_cache(all_cache_paths),
                    artifact_roots=roots or run.artifact_roots,
                    artifact_run_dirs=_unique_paths(run_dirs),
                    source_task_id=source_task_id,
                    clean_task_id=clean_task_id,
                )

    cache_path = _first_existing_baseline_cache(all_cache_paths)
    source_task_id, clean_task_id = _baseline_identity({}, suite=suite, task_id=task_id)
    return _BaselinePlan(
        suite=suite,
        task_id=task_id,
        attacked_trajectory=first_run.trajectory_path,
        cache_path=cache_path,
        artifact_roots=first_run.artifact_roots,
        artifact_run_dirs=(),
        source_task_id=source_task_id,
        clean_task_id=clean_task_id,
    )


def _baseline_run_from_plan(plan: _BaselinePlan) -> Optional[_SourceRun]:
    if plan.trajectory_path is None or plan.trajectory is None:
        return None
    return _SourceRun(
        suite=plan.suite,
        task_id=plan.task_id,
        run_number=1,
        trajectory_path=plan.trajectory_path,
        trajectory=plan.trajectory,
        artifact_roots=plan.artifact_roots,
        artifact_run_dirs=plan.artifact_run_dirs,
        training_artifact_key=_training_key_from_trajectory(plan.trajectory),
        task_entry={},
        result_path=None,
        output_dir=None,
        backend=str(_as_dict(plan.trajectory.get("backend")).get("name") or "unknown"),
        model=str(_as_dict(plan.trajectory.get("backend")).get("model") or "unknown"),
        status=str(_as_dict(plan.trajectory.get("execution")).get("status") or "unknown"),
        timed_out=bool(_as_dict(plan.trajectory.get("execution")).get("timed_out")),
    )


def _source_paths_payload(plan: _BaselinePlan) -> dict[str, Any]:
    payload = {
        "suite": plan.suite,
        "task_id": plan.task_id,
        "source_task_id": plan.source_task_id,
        "clean_task_id": plan.clean_task_id,
        "attacked_trajectory": str(plan.attacked_trajectory),
        "baseline_trajectory": str(plan.trajectory_path) if plan.trajectory_path else None,
        "baseline_cache_path": str(plan.cache_path) if plan.cache_path else None,
    }
    return {key: value for key, value in payload.items() if value is not None}


def _copy_baseline(state: _PackState, plan: _BaselinePlan, baseline_dir: Path) -> str:
    if state.overwrite and not state.dry_run and baseline_dir.exists():
        if baseline_dir.is_dir():
            shutil.rmtree(baseline_dir)
        else:
            baseline_dir.unlink()
    if plan.trajectory_path is not None and plan.trajectory is not None:
        copied = _copy_file(
            state,
            plan.trajectory_path,
            baseline_dir / "trajectory.json",
            label="baseline trajectory",
        )
        if not copied:
            state.warnings.append(
                "Skipped baseline sidecars because destination trajectory already exists: "
                f"{baseline_dir / 'trajectory.json'}"
            )
            return "copied"
        baseline_run = _baseline_run_from_plan(plan)
        if baseline_run is not None:
            _copy_run_sidecars(state, baseline_run, baseline_dir)
        if plan.cache_path is not None:
            _copy_file(state, plan.cache_path, baseline_dir / "baseline_cache.json", label="baseline cache")
        _write_json_sidecar(state, _source_paths_payload(plan), baseline_dir / "source_paths.json", label="source paths")
        return "copied"
    if plan.cache_path is not None:
        copied = _copy_file(state, plan.cache_path, baseline_dir / "baseline_cache.json", label="baseline cache")
        if copied:
            _write_json_sidecar(
                state,
                _source_paths_payload(plan),
                baseline_dir / "source_paths.json",
                label="source paths",
            )
        return "cache_only"
    return "missing"


def _copy_attacked_run(state: _PackState, run: _SourceRun) -> None:
    run_dir = state.dataset_dir / run.suite / run.task_id / f"run_{run.run_number}"
    if state.overwrite and not state.dry_run and run_dir.exists():
        if run_dir.is_dir():
            shutil.rmtree(run_dir)
        else:
            run_dir.unlink()
    copied = _copy_file(state, run.trajectory_path, run_dir / "trajectory.json", label="attacked trajectory")
    if not copied:
        state.warnings.append(
            "Skipped attacked sidecars because destination trajectory already exists: "
            f"{run_dir / 'trajectory.json'}"
        )
        return
    _copy_run_sidecars(state, run, run_dir)


def _path_key(path: Path) -> Path:
    return path.expanduser().resolve()


def _planned_consumed_paths(
    dataset_dir: Path,
    runs: Sequence[_SourceRun],
    baseline_plans: Sequence[_BaselinePlan],
) -> set[Path]:
    planned = {
        _path_key(dataset_dir / run.suite / run.task_id / f"run_{run.run_number}" / "trajectory.json")
        for run in runs
    }
    for plan in baseline_plans:
        baseline_dir = dataset_dir / "_baselines" / plan.suite / plan.task_id / "baseline"
        if plan.trajectory_path is not None and plan.trajectory is not None:
            planned.add(_path_key(baseline_dir / "trajectory.json"))
        if plan.cache_path is not None:
            planned.add(_path_key(baseline_dir / "baseline_cache.json"))
    return planned


def _existing_consumed_paths(dataset_dir: Path) -> list[Path]:
    if not dataset_dir.exists():
        return []
    paths = list(dataset_dir.glob("*/*/run_*/trajectory.json"))
    baselines_root = dataset_dir / "_baselines"
    if baselines_root.is_dir():
        paths.extend(baselines_root.glob("*/*/baseline/trajectory.json"))
        paths.extend(baselines_root.glob("*/*/baseline/baseline_cache.json"))
    return sorted(paths, key=lambda path: path.parts)


def _refuse_unplanned_overwrite(
    *,
    dataset_dir: Path,
    runs: Sequence[_SourceRun],
    baseline_plans: Sequence[_BaselinePlan],
) -> None:
    planned = _planned_consumed_paths(dataset_dir, runs, baseline_plans)
    stale = [path for path in _existing_consumed_paths(dataset_dir) if _path_key(path) not in planned]
    if stale:
        preview = ", ".join(str(path) for path in stale[:5])
        suffix = "" if len(stale) <= 5 else f", ... ({len(stale)} total)"
        raise PackRawByTaskError(
            "Existing dataset contains raw_by_task evidence outside this --overwrite selection; "
            f"refusing to leave stale files visible to consumers: {preview}{suffix}. "
            "Use a new --dataset-name or move/archive the old dataset manually."
        )


def _raw_run_from_dataset_path(path: Path, warnings: list[str]) -> Optional[_SourceRun]:
    try:
        trajectory = _load_json_object(path)
    except (OSError, json.JSONDecodeError, PackRawByTaskError) as exc:
        warnings.append(f"Skipping unreadable existing raw_by_task trajectory {path}: {exc}")
        return None
    try:
        suite = path.parent.parent.parent.name
        task_id = path.parent.parent.name
        run_number = _safe_int(path.parent.name.removeprefix("run_"), 1)
    except IndexError:
        warnings.append(f"Skipping existing trajectory with unexpected raw_by_task path: {path}")
        return None
    status, timed_out = _execution_status({}, trajectory)
    return _SourceRun(
        suite=suite,
        task_id=task_id,
        run_number=run_number,
        trajectory_path=path,
        trajectory=trajectory,
        artifact_roots=(),
        artifact_run_dirs=(),
        training_artifact_key=_training_key_from_trajectory(trajectory),
        task_entry={},
        result_path=None,
        output_dir=None,
        backend=_metadata_backend({}, {}, trajectory),
        model=_metadata_model({}, {}, trajectory),
        status=status,
        timed_out=timed_out,
    )


def _dataset_attacked_runs(dataset_dir: Path, warnings: list[str]) -> list[_SourceRun]:
    runs: list[_SourceRun] = []
    if not dataset_dir.exists():
        return runs
    for path in sorted(dataset_dir.glob("*/*/run_*/trajectory.json"), key=lambda item: item.parts):
        run = _raw_run_from_dataset_path(path, warnings)
        if run is not None:
            runs.append(run)
    return runs


def _baseline_summary_from_dataset(
    dataset_dir: Path,
    runs: Sequence[_SourceRun],
    *,
    skipped_existing: int,
) -> dict[str, int]:
    copied = 0
    cache_only = 0
    baseline_tasks: set[tuple[str, str]] = set()
    baselines_root = dataset_dir / "_baselines"
    if baselines_root.is_dir():
        for baseline_dir in sorted(baselines_root.glob("*/*/baseline"), key=lambda item: item.parts):
            suite = baseline_dir.parent.parent.name
            task_id = baseline_dir.parent.name
            if (baseline_dir / "trajectory.json").is_file():
                copied += 1
                baseline_tasks.add((suite, task_id))
            elif (baseline_dir / "baseline_cache.json").is_file():
                cache_only += 1
                baseline_tasks.add((suite, task_id))
    task_keys = {(run.suite, run.task_id) for run in runs}
    missing = len(task_keys - baseline_tasks)
    return {
        "cache_only": cache_only,
        "copied": copied,
        "missing": missing,
        "skipped_existing": skipped_existing,
    }


def _merge_source_paths(
    existing_manifest: Optional[dict[str, Any]],
    source_paths: dict[str, tuple[Path, ...]],
) -> dict[str, tuple[Path, ...]]:
    if not existing_manifest:
        return source_paths
    existing_source = _as_dict(existing_manifest.get("source"))
    merged: dict[str, tuple[Path, ...]] = {}
    for key in ("result_paths", "output_dirs", "artifact_roots"):
        existing = [Path(str(item)).expanduser() for item in _as_list(existing_source.get(key))]
        merged[key] = _unique_paths([*existing, *source_paths[key]])
    return merged


def _source_filters_payload(options: PackRawByTaskOptions) -> dict[str, Any]:
    filters: dict[str, Any] = {}
    if options.suites:
        filters["suite"] = list(options.suites)
    if options.task_ids:
        filters["task_id"] = list(options.task_ids)
    if options.run_numbers:
        filters["run_number"] = list(options.run_numbers)
    return filters


def _mixed_or_single(values: Iterable[str]) -> str:
    unique = sorted({str(value) for value in values if str(value)})
    if not unique:
        return "unknown"
    if len(unique) == 1:
        return unique[0]
    return "mixed"


def _manifest_payload(
    *,
    options: PackRawByTaskOptions,
    dataset_name: str,
    runs: Sequence[_SourceRun],
    source_result_paths: Sequence[Path],
    source_output_dirs: Sequence[Path],
    source_artifact_roots: Sequence[Path],
    baseline_summary: dict[str, int],
    copy_summary: dict[str, int],
    warnings: Sequence[str],
) -> dict[str, Any]:
    unique_tasks = sorted({(run.suite, run.task_id) for run in runs})
    suite_counts: dict[str, int] = {}
    for suite, task_id in unique_tasks:
        if task_id:
            suite_counts[suite] = suite_counts.get(suite, 0) + 1
    copied_success_runs = sum(1 for run in runs if run.status == "success" and not run.timed_out)
    return {
        "schema_version": RAW_BY_TASK_SCHEMA_VERSION,
        "name": dataset_name,
        "backend": _mixed_or_single(run.backend for run in runs),
        "target_model": _mixed_or_single(run.model for run in runs),
        "created_at": time.time(),
        "source": {
            "kind": "actbench_runner_output",
            "result_paths": [str(path) for path in source_result_paths],
            "output_dirs": [str(path) for path in source_output_dirs],
            "artifact_roots": [str(path) for path in source_artifact_roots],
        },
        "copied_runs": len(runs),
        "copied_success_runs": copied_success_runs,
        "task_count": len(unique_tasks),
        "suite_counts": dict(sorted(suite_counts.items())),
        "baseline_summary": dict(sorted(baseline_summary.items())),
        "packer": {
            "schema_version": PACK_RAW_BY_TASK_SCHEMA_VERSION,
            "tool": TOOL_NAME,
            "dry_run": bool(options.dry_run),
            "filters": _source_filters_payload(options),
        },
        "copy_summary": dict(sorted(copy_summary.items())),
        "warnings": list(warnings),
    }


def _validation_payload(dataset_dir: Path) -> dict[str, Any]:
    manifest = load_raw_by_task_dataset_manifest(dataset_dir)
    attacked = collect_raw_by_task_trajectories([dataset_dir], role=RAW_ROLE_ATTACKED)
    benign = collect_raw_by_task_trajectories([dataset_dir], role=RAW_ROLE_BENIGN)
    return {
        "manifest_name": manifest.get("name"),
        "attacked_trajectory_count": len(attacked.trajectory_paths),
        "benign_trajectory_count": len(benign.trajectory_paths),
        "benign_excluded_count": len(benign.excluded),
        "benign_excluded_by_reason": benign.source.get("excluded_by_reason", {}),
    }


def _normalize_option_paths(values: Sequence[Path | str]) -> tuple[Path, ...]:
    return _unique_paths(_expanded_path(value) for value in values)


def _discover_runs(options: PackRawByTaskOptions, warnings: list[str]) -> tuple[list[_SourceRun], dict[str, tuple[Path, ...]]]:
    result_paths = _normalize_option_paths(options.result_paths)
    output_dirs = _normalize_option_paths(options.output_dirs)
    explicit_artifact_roots = _normalize_option_paths(options.artifact_roots)
    runs: list[_SourceRun] = []
    for result_path in result_paths:
        if not result_path.is_file():
            raise PackRawByTaskError(f"Result JSON not found: {result_path}")
        runs.extend(
            _discover_from_result(
                result_path,
                explicit_roots=explicit_artifact_roots,
                warnings=warnings,
            )
        )
    for output_dir in output_dirs:
        if not output_dir.is_dir():
            raise PackRawByTaskError(f"Output directory not found: {output_dir}")
        runs.extend(
            _discover_from_output_dir(
                output_dir,
                explicit_roots=explicit_artifact_roots,
                warnings=warnings,
            )
        )
    source_output_dirs = list(output_dirs)
    source_output_dirs.extend(run.output_dir for run in runs if run.output_dir is not None)
    source_artifact_roots = list(explicit_artifact_roots)
    for run in runs:
        source_artifact_roots.extend(run.artifact_roots)
    return runs, {
        "result_paths": result_paths,
        "output_dirs": _unique_paths(source_output_dirs),
        "artifact_roots": _unique_paths(source_artifact_roots),
    }


def pack_raw_by_task(options: PackRawByTaskOptions) -> dict[str, Any]:
    """Copy selected runner trajectories into one raw_by_task dataset."""

    if options.allow_existing and options.overwrite:
        raise PackRawByTaskError("--allow-existing and --overwrite are mutually exclusive")
    if not options.result_paths and not options.output_dirs:
        raise PackRawByTaskError("Provide at least one --result or --output-dir source")
    dataset_name = _safe_dataset_name(options.dataset_name)
    raw_root = Path(options.raw_by_task_root).expanduser()
    dataset_dir = raw_root / dataset_name
    try:
        if dataset_dir.resolve() == raw_root.resolve():
            raise ValueError
        dataset_dir.resolve().relative_to(raw_root.resolve())
    except ValueError as exc:
        raise PackRawByTaskError(
            f"Sanitized dataset name {dataset_name!r} does not resolve inside {raw_root}"
        ) from exc
    if dataset_dir.exists() and not options.dry_run and not options.allow_existing and not options.overwrite:
        raise PackRawByTaskError(
            f"raw_by_task dataset already exists: {dataset_dir}. "
            "Use --allow-existing to fill missing files or --overwrite to replace pack files."
        )

    warnings: list[str] = []
    discovered_runs, source_paths = _discover_runs(options, warnings)
    selected_runs = _dedupe_runs(_filter_runs(discovered_runs, options), warnings)
    if not selected_runs:
        raise PackRawByTaskError("No attacked trajectories matched the requested sources and filters")

    state = _PackState(options=options, dataset_dir=dataset_dir, warnings=warnings)
    baseline_plans: list[_BaselinePlan] = []
    if options.include_baselines:
        runs_by_task: dict[tuple[str, str], list[_SourceRun]] = defaultdict(list)
        for run in selected_runs:
            runs_by_task[(run.suite, run.task_id)].append(run)
        for (suite, task_id), task_runs in sorted(runs_by_task.items()):
            baseline_plans.append(_select_baseline_plan(suite, task_id, task_runs, state.warnings))

    if options.overwrite and dataset_dir.exists() and not options.dry_run:
        _refuse_unplanned_overwrite(
            dataset_dir=dataset_dir,
            runs=selected_runs,
            baseline_plans=baseline_plans,
        )

    for run in selected_runs:
        _copy_attacked_run(state, run)

    baseline_summary = {"cache_only": 0, "copied": 0, "missing": 0, "skipped_existing": 0}
    for plan in baseline_plans:
        baseline_dir = dataset_dir / "_baselines" / plan.suite / plan.task_id / "baseline"
        before_skipped = state.copy_summary["skipped_existing"]
        status = _copy_baseline(state, plan, baseline_dir)
        baseline_summary[status] = baseline_summary.get(status, 0) + 1
        baseline_summary["skipped_existing"] += state.copy_summary["skipped_existing"] - before_skipped

    manifest_runs = selected_runs
    manifest_source_paths = source_paths
    existing_manifest: Optional[dict[str, Any]] = None
    manifest_path = dataset_dir / "manifest.json"
    if options.allow_existing and not options.dry_run and dataset_dir.exists():
        existing_manifest = _load_optional_json_object(manifest_path)
        manifest_runs = _dataset_attacked_runs(dataset_dir, state.warnings)
        baseline_summary = _baseline_summary_from_dataset(
            dataset_dir,
            manifest_runs,
            skipped_existing=baseline_summary.get("skipped_existing", 0),
        )
        manifest_source_paths = _merge_source_paths(existing_manifest, source_paths)

    manifest_written = False
    if options.dry_run:
        state.copy_summary["planned_json"] += 1
    else:
        state.copy_summary["json_written"] += 1
        manifest_written = True

    manifest = _manifest_payload(
        options=options,
        dataset_name=dataset_name,
        runs=manifest_runs,
        source_result_paths=manifest_source_paths["result_paths"],
        source_output_dirs=manifest_source_paths["output_dirs"],
        source_artifact_roots=manifest_source_paths["artifact_roots"],
        baseline_summary=baseline_summary,
        copy_summary=state.copy_summary,
        warnings=state.warnings,
    )

    if not options.dry_run:
        atomic_write_json(manifest_path, manifest)

    summary: dict[str, Any] = {
        "schema_version": PACK_RAW_BY_TASK_SCHEMA_VERSION,
        "dataset": dataset_name,
        "dataset_path": str(dataset_dir),
        "dry_run": bool(options.dry_run),
        "manifest_path": str(manifest_path),
        "manifest_written": manifest_written,
        "copied_runs": manifest["copied_runs"],
        "selected_runs": len(selected_runs),
        "copied_success_runs": manifest["copied_success_runs"],
        "task_count": manifest["task_count"],
        "suite_counts": manifest["suite_counts"],
        "baseline_summary": baseline_summary,
        "copy_summary": dict(sorted(state.copy_summary.items())),
        "warnings": list(state.warnings),
    }
    if options.validate and not options.dry_run and manifest_path.exists():
        summary["validation"] = _validation_payload(dataset_dir)
    return summary


def _split_values(values: Optional[Sequence[str]]) -> tuple[str, ...]:
    items: list[str] = []
    for value in values or []:
        for part in str(value).split(","):
            text = part.strip()
            if text:
                items.append(text)
    return tuple(items)


def _split_run_numbers(values: Optional[Sequence[str]], parser: argparse.ArgumentParser) -> tuple[int, ...]:
    numbers: list[int] = []
    for value in values or []:
        for part in str(value).split(","):
            text = part.strip()
            if not text:
                continue
            try:
                number = int(text)
            except ValueError:
                parser.error(f"--run-number must be a positive integer, got {text!r}")
            if number < 1:
                parser.error("--run-number must be a positive integer")
            numbers.append(number)
    return tuple(numbers)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Pack ActBench runner trajectories into a raw_by_task dataset."
    )
    parser.add_argument(
        "--result",
        dest="result_paths",
        action="append",
        default=[],
        help="Aggregate runner JSON to pack; may be repeated.",
    )
    parser.add_argument(
        "--output-dir",
        dest="output_dirs",
        action="append",
        default=[],
        help="Runner output directory to scan when no --result JSON is available; may be repeated.",
    )
    parser.add_argument(
        "--artifact-root",
        dest="artifact_roots",
        action="append",
        default=[],
        help="Additional raw artifact root containing runs/<training_artifact_key>/; may be repeated.",
    )
    parser.add_argument("--dataset-name", required=True, help="Destination raw_by_task dataset name.")
    parser.add_argument(
        "--raw-by-task-root",
        default=str(DEFAULT_RAW_BY_TASK_ROOT),
        help=f"raw_by_task root directory (default: {DEFAULT_RAW_BY_TASK_ROOT}).",
    )
    parser.add_argument("--suite", action="append", default=[], help="Suite filter; may be repeated or comma-separated.")
    parser.add_argument("--task-id", action="append", default=[], help="Task-id filter; may be repeated or comma-separated.")
    parser.add_argument(
        "--run-number",
        action="append",
        default=[],
        help="1-based repeat run filter; may be repeated or comma-separated.",
    )
    parser.add_argument("--no-baselines", dest="include_baselines", action="store_false", help="Do not copy linked benign baseline evidence.")
    parser.set_defaults(include_baselines=True)
    parser.add_argument("--dry-run", action="store_true", help="Report planned copies without writing files.")
    existing = parser.add_mutually_exclusive_group()
    existing.add_argument("--allow-existing", action="store_true", help="Fill missing files in an existing dataset without overwriting existing files.")
    existing.add_argument("--overwrite", action="store_true", help="Overwrite destination files/directories inside the selected dataset.")
    parser.add_argument("--no-validate", dest="validate", action="store_false", help="Skip post-write raw_by_task validation.")
    parser.set_defaults(validate=True)
    parser.add_argument("--compact", action="store_true", help="Print compact single-line JSON.")
    return parser


def _options_from_args(args: argparse.Namespace, parser: argparse.ArgumentParser) -> PackRawByTaskOptions:
    return PackRawByTaskOptions(
        result_paths=tuple(Path(value).expanduser() for value in args.result_paths),
        output_dirs=tuple(Path(value).expanduser() for value in args.output_dirs),
        artifact_roots=tuple(Path(value).expanduser() for value in args.artifact_roots),
        dataset_name=args.dataset_name,
        raw_by_task_root=Path(args.raw_by_task_root).expanduser(),
        suites=_split_values(args.suite),
        task_ids=_split_values(args.task_id),
        run_numbers=_split_run_numbers(args.run_number, parser),
        include_baselines=bool(args.include_baselines),
        dry_run=bool(args.dry_run),
        allow_existing=bool(args.allow_existing),
        overwrite=bool(args.overwrite),
        validate=bool(args.validate),
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    options = _options_from_args(args, parser)
    try:
        summary = pack_raw_by_task(options)
    except PackRawByTaskError as exc:
        parser.exit(2, f"{TOOL_NAME}: error: {exc}\n")
    print(json.dumps(summary, indent=None if args.compact else 2, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
