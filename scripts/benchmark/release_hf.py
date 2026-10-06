"""Build lightweight HuggingFace-style trajectory datasets from full release bundles."""

from __future__ import annotations

import argparse
import json
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, Sequence

from lib_safe_paths import ScenarioValidationError, safe_join, safe_relative_path
from lib_training_artifacts import safe_artifact_name

from benchmark.release_bundle import FULL_RELEASE_SCHEMA_VERSION
from benchmark.release_scores import sha256_file

HF_RELEASE_SCHEMA_VERSION = "actbench.release.hf_trajectories.v1"


class HfReleaseError(ValueError):
    """Raised when a lightweight trajectory dataset cannot be built."""


@dataclass(frozen=True)
class HfBuildOptions:
    full_release_root: Path | str
    output_root: Path | str
    combos: Sequence[str] = field(default_factory=tuple)
    fmt: str = "jsonl"
    full_artifact_uri_base: str = ""
    overwrite: bool = False


@dataclass(frozen=True)
class HfBuildResult:
    output_root: Path
    manifest_path: Path
    row_count: int
    combo_count: int


@dataclass(frozen=True)
class _ComboSource:
    combo_id: str
    manifest_path: Path
    manifest_rel: str
    archive_rel: str
    archive_path: Optional[Path]
    archive_sha256: str
    archive_size_bytes: Optional[int]


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise HfReleaseError(f"JSON payload must be an object: {path}")
    return payload


def _safe_component(value: str, *, label: str) -> str:
    text = str(value or "")
    path = Path(text)
    if not text or text in {".", ".."} or path.is_absolute() or len(path.parts) != 1 or safe_artifact_name(text) != text:
        raise HfReleaseError(f"Unsafe {label} path component: {value!r}")
    return text


def _safe_manifest_path(base: Path, value: str, *, label: str) -> Path:
    try:
        rel = safe_relative_path(value)
        current = base
        for part in rel.parts:
            current = current / part
            if current.is_symlink():
                raise ScenarioValidationError(f"path contains symbolic link component: {value}")
        return safe_join(base, value)
    except ScenarioValidationError as exc:
        raise HfReleaseError(f"Unsafe {label} path in full release manifest: {value!r}") from exc


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _write_jsonl(path: Path, rows: Sequence[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True))
            handle.write("\n")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            payload = json.loads(line)
            if not isinstance(payload, dict):
                raise HfReleaseError(f"JSONL line {line_number} root must be object: {path}")
            rows.append(payload)
    return rows


def _archive_source(full_release_root: Path, combo: dict[str, Any], combo_id: str) -> tuple[str, Optional[Path], str, Optional[int]]:
    archive_rel = str(combo.get("archive") or "")
    size = combo.get("archive_size_bytes")
    digest = str(combo.get("archive_sha256") or "")
    if not archive_rel:
        if size is not None or digest:
            raise HfReleaseError(f"Archive metadata present without archive for combo {combo_id}")
        return "", None, "", None
    expected_prefix = f"combos/{combo_id}/archives/"
    archive_name = Path(archive_rel).name
    if not archive_rel.startswith(expected_prefix) or archive_name not in {f"{combo_id}.tar.gz", f"{combo_id}.tar.zst"}:
        raise HfReleaseError(f"Unexpected archive path for combo {combo_id}: {archive_rel!r}")
    archive_path = _safe_manifest_path(full_release_root, archive_rel, label="combo archive")
    if not archive_path.is_file():
        raise HfReleaseError(f"Missing combo archive: {archive_path}")
    if not isinstance(size, int) or isinstance(size, bool):
        raise HfReleaseError(f"Archive size metadata is required for combo {combo_id}")
    actual_size = archive_path.stat().st_size
    if actual_size != size:
        raise HfReleaseError(f"Archive size mismatch for combo {combo_id}: manifest={size} actual={actual_size}")
    if not digest:
        raise HfReleaseError(f"Archive sha256 metadata is required for combo {combo_id}")
    actual_sha = sha256_file(archive_path)
    if actual_sha != digest:
        raise HfReleaseError(f"Archive sha256 mismatch for combo {combo_id}: manifest={digest} actual={actual_sha}")
    return archive_rel, archive_path, digest, size


def _combo_manifest_paths(full_release_root: Path, combos: Sequence[str]) -> list[_ComboSource]:
    root_manifest = _load_json(full_release_root / "manifest.json")
    if root_manifest.get("schema_version") != FULL_RELEASE_SCHEMA_VERSION:
        raise HfReleaseError(
            f"Unsupported full release schema {root_manifest.get('schema_version')!r}: {full_release_root / 'manifest.json'}"
        )
    raw_combos = _as_list(root_manifest.get("combos"))
    if root_manifest.get("combo_count") != len(raw_combos):
        raise HfReleaseError(f"Full release combo_count mismatch: {root_manifest.get('combo_count')} != {len(raw_combos)}")
    selected = {_safe_component(combo_id, label="requested combo_id") for combo_id in combos}
    sources: list[_ComboSource] = []
    seen: set[str] = set()
    for item in raw_combos:
        data = _as_dict(item)
        combo_id = _safe_component(str(data.get("combo_id") or ""), label="combo_id")
        if combo_id in seen:
            raise HfReleaseError(f"Duplicate combo_id in full release manifest: {combo_id}")
        seen.add(combo_id)
        manifest_rel = str(data.get("manifest") or "")
        expected_manifest = f"combos/{combo_id}/manifest.json"
        if manifest_rel != expected_manifest:
            raise HfReleaseError(f"Combo {combo_id} manifest path must be {expected_manifest!r}, got {manifest_rel!r}")
        if selected and combo_id not in selected:
            continue
        manifest_path = _safe_manifest_path(full_release_root, manifest_rel, label="combo manifest")
        combo_manifest = _load_json(manifest_path)
        child_combo_id = _safe_component(str(combo_manifest.get("combo_id") or ""), label="combo manifest combo_id")
        if child_combo_id != combo_id:
            raise HfReleaseError(f"Combo id mismatch for {manifest_rel}: root={combo_id!r} child={child_combo_id!r}")
        archive_rel, archive_path, archive_sha, archive_size = _archive_source(full_release_root, data, combo_id)
        sources.append(
            _ComboSource(
                combo_id=combo_id,
                manifest_path=manifest_path,
                manifest_rel=manifest_rel,
                archive_rel=archive_rel,
                archive_path=archive_path,
                archive_sha256=archive_sha,
                archive_size_bytes=archive_size,
            )
        )
    if selected:
        missing = sorted(selected - {source.combo_id for source in sources})
        if missing:
            raise HfReleaseError(f"Requested combo(s) not found in full release manifest: {missing}")
    return sources


def _artifact_uri(base: str, combo_id: str, archive_rel: str = "") -> str:
    if not base:
        return ""
    if not archive_rel:
        raise HfReleaseError(f"Cannot build artifact URI for combo {combo_id} without a declared archive")
    return f"{base.rstrip('/')}/{Path(archive_rel).name}"


def _trajectory_row(
    *,
    full_release_root: Path,
    combo_root: Path,
    combo_manifest: dict[str, Any],
    task_record: dict[str, Any],
    run_record: dict[str, Any],
    role: str,
    run_dir_rel: str,
    full_artifact_uri_base: str,
    archive_rel: str = "",
) -> dict[str, Any]:
    run_dir = _safe_manifest_path(combo_root, run_dir_rel, label="run directory")
    trajectory_rel = str(run_record.get("trajectory") or "trajectory.json")
    trajectory_path = _safe_manifest_path(run_dir, trajectory_rel, label="trajectory")
    if not trajectory_path.is_file():
        raise HfReleaseError(f"Missing released trajectory: {trajectory_path}")
    trajectory = _load_json(trajectory_path)
    trajectory_json = json.dumps(trajectory, ensure_ascii=False, sort_keys=True)
    score_summary = _as_dict(run_record.get("score_summary"))
    combo_id = _safe_component(str(combo_manifest.get("combo_id") or combo_root.name), label="combo_id")
    attack_slot = _safe_component(str(run_record.get("attack_slot") or f"run_{run_record.get('run_number')}"), label="attack_slot") if role == "attack" else ""
    run_number = run_record.get("run_number") if role == "attack" else None
    rel_to_root = trajectory_path.relative_to(full_release_root).as_posix()
    rel_to_combo = trajectory_path.relative_to(combo_root).as_posix()
    return {
        "schema_version": HF_RELEASE_SCHEMA_VERSION,
        "release_id": str(combo_manifest.get("release_id") or ""),
        "combo_id": combo_id,
        "backend": str(combo_manifest.get("backend") or ""),
        "model": str(combo_manifest.get("model") or ""),
        "suite": _safe_component(str(task_record.get("suite") or ""), label="suite"),
        "task_id": _safe_component(str(task_record.get("task_id") or ""), label="task_id"),
        "role": role,
        "attack_slot": attack_slot,
        "run_number": run_number,
        "trajectory_id": str(run_record.get("trajectory_id") or trajectory.get("trajectory_id") or ""),
        "trajectory_sha256": sha256_file(trajectory_path),
        "trajectory_json": trajectory_json,
        "score_json": json.dumps(score_summary, ensure_ascii=False, sort_keys=True),
        "full_bundle_relative_path": rel_to_root,
        "full_artifact_uri": _artifact_uri(full_artifact_uri_base, combo_id, archive_rel),
        "full_artifact_inner_path": f"{combo_id}/{rel_to_combo}",
    }


def _rows_for_combo(
    *,
    full_release_root: Path,
    combo_manifest_path: Path,
    full_artifact_uri_base: str,
    archive_rel: str = "",
) -> list[dict[str, Any]]:
    combo_manifest = _load_json(combo_manifest_path)
    combo_root = combo_manifest_path.parent
    task_bundles_rel = str(combo_manifest.get("task_bundles") or "task_bundles.jsonl")
    task_bundles_path = _safe_manifest_path(combo_root, task_bundles_rel, label="task_bundles")
    task_records = _read_jsonl(task_bundles_path)
    rows: list[dict[str, Any]] = []
    for task in task_records:
        suite = _safe_component(str(task.get("suite") or ""), label="suite")
        task_id = _safe_component(str(task.get("task_id") or ""), label="task_id")
        clean = _as_dict(task.get("clean"))
        rows.append(
            _trajectory_row(
                full_release_root=full_release_root,
                combo_root=combo_root,
                combo_manifest=combo_manifest,
                task_record=task,
                run_record=clean,
                role="clean",
                run_dir_rel=f"tasks/{suite}/{task_id}/clean",
                full_artifact_uri_base=full_artifact_uri_base,
                archive_rel=archive_rel,
            )
        )
        for attack in _as_list(task.get("attacks")):
            attack_record = _as_dict(attack)
            slot = _safe_component(str(attack_record.get("attack_slot") or f"run_{attack_record.get('run_number')}"), label="attack_slot")
            rows.append(
                _trajectory_row(
                    full_release_root=full_release_root,
                    combo_root=combo_root,
                    combo_manifest=combo_manifest,
                    task_record=task,
                    run_record=attack_record,
                    role="attack",
                    run_dir_rel=f"tasks/{suite}/{task_id}/attacks/{slot}",
                    full_artifact_uri_base=full_artifact_uri_base,
                    archive_rel=archive_rel,
                )
            )
    return rows


def _write_parquet(path: Path, rows: Sequence[dict[str, Any]]) -> None:
    try:
        import pyarrow as pa  # type: ignore
        import pyarrow.parquet as pq  # type: ignore
    except Exception as exc:  # pragma: no cover - depends on optional dependency
        raise HfReleaseError("Parquet output requires optional dependency 'pyarrow'") from exc
    path.parent.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pylist(list(rows))
    pq.write_table(table, path)


def build_hf_dataset(options: HfBuildOptions) -> HfBuildResult:
    full_release_root_raw = Path(options.full_release_root).expanduser()
    if full_release_root_raw.is_symlink():
        raise HfReleaseError(f"Full release root must not be a symbolic link: {full_release_root_raw}")
    full_release_root = full_release_root_raw.resolve()
    output_root = Path(options.output_root).expanduser()
    if output_root.exists():
        if not options.overwrite:
            raise HfReleaseError(f"HF output root already exists: {output_root}")
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    combo_sources = _combo_manifest_paths(full_release_root, options.combos)
    combo_manifests: list[dict[str, Any]] = []
    total_rows = 0
    for source in combo_sources:
        combo_manifest = _load_json(source.manifest_path)
        combo_id = source.combo_id
        rows = _rows_for_combo(
            full_release_root=full_release_root,
            combo_manifest_path=source.manifest_path,
            full_artifact_uri_base=options.full_artifact_uri_base,
            archive_rel=source.archive_rel,
        )
        if options.fmt == "jsonl":
            data_path = output_root / "data" / f"{combo_id}.jsonl"
            _write_jsonl(data_path, rows)
        elif options.fmt == "parquet":
            data_path = output_root / "data" / f"{combo_id}.parquet"
            _write_parquet(data_path, rows)
        else:
            raise HfReleaseError(f"Unsupported HF output format: {options.fmt!r}")
        total_rows += len(rows)
        combo_manifests.append(
            {
                "combo_id": combo_id,
                "backend": combo_manifest.get("backend"),
                "model": combo_manifest.get("model"),
                "task_count": combo_manifest.get("task_count"),
                "row_count": len(rows),
                "data": data_path.relative_to(output_root).as_posix(),
                "source_full_manifest": source.manifest_rel,
            }
        )

    manifest = {
        "schema_version": HF_RELEASE_SCHEMA_VERSION,
        "created_at": time.time(),
        "full_release_root_schema": FULL_RELEASE_SCHEMA_VERSION,
        "full_release_manifest": "manifest.json",
        "format": options.fmt,
        "combo_count": len(combo_manifests),
        "row_count": total_rows,
        "combos": combo_manifests,
    }
    manifest_path = output_root / "manifest.json"
    _write_json(manifest_path, manifest)
    _write_json(output_root / "metadata" / "combo_manifest.json", combo_manifests)
    (output_root / "README.md").write_text(
        "# ActBench Trajectories\n\n"
        "This lightweight dataset is derived from the canonical ActBench full release bundle. "
        "Each row contains one redacted trajectory plus official score metadata and a pointer "
        "back to the full reproducibility artifact.\n",
        encoding="utf-8",
    )
    return HfBuildResult(
        output_root=output_root,
        manifest_path=manifest_path,
        row_count=total_rows,
        combo_count=len(combo_manifests),
    )


def _parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build lightweight ActBench HF trajectory dataset")
    parser.add_argument("--full-release-root", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--combo", action="append", default=[])
    parser.add_argument("--format", choices=("jsonl", "parquet"), default="jsonl")
    parser.add_argument("--full-artifact-uri-base", default="")
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _parse_args(argv)
    result = build_hf_dataset(
        HfBuildOptions(
            full_release_root=args.full_release_root,
            output_root=args.output_root,
            combos=tuple(args.combo),
            fmt=args.format,
            full_artifact_uri_base=args.full_artifact_uri_base,
            overwrite=args.overwrite,
        )
    )
    print(
        json.dumps(
            {
                "output_root": str(result.output_root),
                "manifest": str(result.manifest_path),
                "combo_count": result.combo_count,
                "row_count": result.row_count,
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0
