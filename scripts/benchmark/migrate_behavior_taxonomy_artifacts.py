#!/usr/bin/env python3
"""Create v2-derived copies of historical ActBench result artifacts.

This migrates historical B-class result/raw_by_task artifacts from the v1
behavior-taxonomy numbering into the current v2 numbering.  It is intentionally
copy-only: sources are never modified, and existing destination files are never
overwritten.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from benchmark.raw_by_task import RAW_BY_TASK_SCHEMA_VERSION  # noqa: E402
from lib_taxonomy import (  # noqa: E402
    BEHAVIOR_DEFINITIONS,
    CURRENT_BEHAVIOR_ID_BY_TYPE,
    LEGACY_BEHAVIOR_ID_BY_TYPE,
    OLD_TO_NEW_BEHAVIOR_ID,
    TAXONOMY_VERSION_CURRENT,
    TAXONOMY_VERSION_LEGACY,
    behavior_type_for_id,
    current_behavior_id_for_type,
    legacy_behavior_id_for_type,
    normalize_behavior_type,
    normalize_taxonomy_version,
)

SCHEMA_VERSION = "actbench.behavior_taxonomy_artifact_migration.v1"
_TASK_ID_RE = re.compile(r"task_(B(?:[1-9]|1[0-5]))_T(\d+)")
_DISPLAY_TASK_ID_RE = re.compile(r"\b(B(?:[1-9]|1[0-5]))_T(\d+)\b")
_EXACT_BEHAVIOR_ID_RE = re.compile(r"^B(?:[1-9]|1[0-5])$")
_BEHAVIOR_KEY_RE = re.compile(r"^(B(?:[1-9]|1[0-5]))_([a-z][a-z0-9_]*)$")
_JSON_SUFFIXES = {".json"}
_EVIDENCE_DIR_NAMES = {"api", "workspace_after", "workspace_before"}
_EVIDENCE_JSON_NAMES = {"transcript.json"}

_TASK_ID_VALUE_KEYS = {
    "task_id",
    "source_task_id",
    "clean_task_id",
    "baseline_task_id",
    "trajectory_task_id",
    "target_task_id",
    "current_task_id",
    "display",
}
_TASK_ID_PRESERVE_KEYS = {
    "legacy_task_id",
    "legacy_behavior_task_id",
    "old_task_id",
    "source_legacy_task_id",
}
_SELECTOR_KEYS = {"suite", "requested_suite"}
_PATHISH_KEY_FRAGMENTS = (
    "path",
    "dir",
    "root",
    "artifact",
    "slot_id",
    "trajectory",
    "trajectory_id",
    "metadata",
    "training_artifact_key",
)
_BEHAVIOR_FIELD_KEYS = {
    "taxonomy_version",
    "behavior_id",
    "behavior_type",
    "behavior",
    "behavior_label",
    "behavior_key",
    "legacy_behavior_id",
    "scoring_family",
    "legacy_risk_type",
}


def _read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _write_json(path: Path, payload: Any, *, compact: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    separators = (",", ":") if compact else None
    text = json.dumps(
        payload,
        ensure_ascii=False,
        indent=None if compact else 2,
        sort_keys=True,
        separators=separators,
    )
    path.write_text(text + "\n", encoding="utf-8")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _file_info(path: Path) -> dict[str, Any]:
    stat = path.stat()
    return {"sha256": _sha256_file(path), "size_bytes": stat.st_size}


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _legacy_behavior_id_from_task_id(task_id: str) -> str | None:
    match = _TASK_ID_RE.search(str(task_id or ""))
    return match.group(1) if match else None


def _new_task_id_for_legacy_match(match: re.Match[str]) -> str:
    old_behavior_id = match.group(1)
    return f"task_{OLD_TO_NEW_BEHAVIOR_ID[old_behavior_id]}_T{match.group(2)}"


def _new_display_task_id_for_legacy_match(match: re.Match[str]) -> str:
    old_behavior_id = match.group(1)
    return f"{OLD_TO_NEW_BEHAVIOR_ID[old_behavior_id]}_T{match.group(2)}"


def _migrate_task_ids_in_text(text: str) -> str:
    migrated = _TASK_ID_RE.sub(_new_task_id_for_legacy_match, text)
    return _DISPLAY_TASK_ID_RE.sub(_new_display_task_id_for_legacy_match, migrated)


def _migrate_behavior_id(old_behavior_id: str) -> str:
    old = str(old_behavior_id or "").strip().upper()
    if old not in OLD_TO_NEW_BEHAVIOR_ID:
        return old
    return OLD_TO_NEW_BEHAVIOR_ID[old]


def _migrate_suite_value(value: str) -> str:
    text = str(value or "")
    if _EXACT_BEHAVIOR_ID_RE.fullmatch(text):
        return _migrate_behavior_id(text)
    return _migrate_task_ids_in_text(text)


def _migrate_behavior_key(value: str) -> str:
    text = str(value or "")
    match = _BEHAVIOR_KEY_RE.fullmatch(text)
    if not match:
        return text
    old_id, suffix = match.groups()
    try:
        behavior_type = normalize_behavior_type(suffix)
    except ValueError:
        behavior_type = behavior_type_for_id(old_id, taxonomy_version=TAXONOMY_VERSION_LEGACY)
    return f"{current_behavior_id_for_type(behavior_type)}_{behavior_type}"


def _migrate_path_segments(text: str) -> str:
    separator = "/" if "/" in text else ("\\" if "\\" in text else None)
    if separator is None:
        return _migrate_suite_value(text)
    parts = text.split(separator)
    return separator.join(_migrate_suite_value(part) for part in parts)


def _migrate_dict_key(key: str) -> str:
    if _BEHAVIOR_KEY_RE.fullmatch(key):
        return _migrate_behavior_key(key)
    if _EXACT_BEHAVIOR_ID_RE.fullmatch(key):
        return _migrate_behavior_id(key)
    if _TASK_ID_RE.search(key):
        return _migrate_task_ids_in_text(key)
    if "/" in key or "\\" in key:
        return _migrate_path_segments(key)
    return key


def _behavior_fields_for_type(behavior_type: str) -> dict[str, Any]:
    normalized = normalize_behavior_type(behavior_type)
    definition = BEHAVIOR_DEFINITIONS[normalized]
    return {
        "taxonomy_version": TAXONOMY_VERSION_CURRENT,
        "behavior_id": definition.id,
        "behavior_type": definition.type,
        "behavior_label": definition.label,
        "behavior_key": f"{definition.id}_{definition.type}",
        "legacy_behavior_id": legacy_behavior_id_for_type(definition.type),
        "scoring_family": definition.scoring_family,
        "legacy_risk_type": definition.legacy_risk_type,
    }


def _behavior_type_from_metadata(metadata: Mapping[str, Any]) -> str | None:
    raw_behavior_type = metadata.get("behavior_type") or metadata.get("behavior")
    if raw_behavior_type not in (None, ""):
        try:
            return normalize_behavior_type(raw_behavior_type)
        except ValueError:
            pass

    raw_legacy_behavior_id = metadata.get("legacy_behavior_id") or metadata.get("old_behavior_id")
    if raw_legacy_behavior_id not in (None, ""):
        try:
            return behavior_type_for_id(
                raw_legacy_behavior_id,
                taxonomy_version=TAXONOMY_VERSION_LEGACY,
            )
        except ValueError:
            pass

    raw_behavior_id = metadata.get("behavior_id") or metadata.get("target_behavior_id")
    if raw_behavior_id not in (None, ""):
        taxonomy_version = normalize_taxonomy_version(
            metadata.get("taxonomy_version") or metadata.get("behavior_taxonomy_version")
        )
        if taxonomy_version == TAXONOMY_VERSION_CURRENT:
            try:
                return behavior_type_for_id(raw_behavior_id)
            except ValueError:
                pass
        try:
            return behavior_type_for_id(
                raw_behavior_id,
                taxonomy_version=TAXONOMY_VERSION_LEGACY,
            )
        except ValueError:
            pass

    raw_task_id = (
        metadata.get("task_id")
        or metadata.get("id")
        or metadata.get("source_task_id")
        or metadata.get("baseline_task_id")
    )
    legacy_behavior_id = _legacy_behavior_id_from_task_id(str(raw_task_id or ""))
    if legacy_behavior_id:
        try:
            return behavior_type_for_id(
                legacy_behavior_id,
                taxonomy_version=TAXONOMY_VERSION_LEGACY,
            )
        except ValueError:
            pass
    return None


def _legacy_task_id_from_original(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    match = _TASK_ID_RE.search(value)
    if not match:
        return None
    return f"task_{match.group(1)}_T{match.group(2)}"


def _should_treat_as_task_id_key(key: str, value: Any) -> bool:
    if key in _TASK_ID_PRESERVE_KEYS:
        return False
    if key in _TASK_ID_VALUE_KEYS:
        return True
    if key == "id" and isinstance(value, str) and _TASK_ID_RE.fullmatch(value):
        return True
    return False


def _is_pathish_key(key: str) -> bool:
    lowered = key.lower()
    return any(fragment in lowered for fragment in _PATHISH_KEY_FRAGMENTS)


class ArtifactMigrator:
    def __init__(self, *, compact: bool = False) -> None:
        self.compact = compact
        self.task_id_mappings: Counter[str] = Counter()
        self.behavior_id_mappings: Counter[str] = Counter()
        self.json_files_migrated = 0
        self.files_copied = 0
        self.path_rewrites = 0
        self.fields_rewritten = 0
        self.provenance_records = 0
        self._active_source_root: Path | None = None
        self._active_destination_source_root: Path | None = None

    def _record_task_rewrite(self, before: str, after: str) -> None:
        if before != after:
            self.fields_rewritten += 1
            for match in _TASK_ID_RE.finditer(before):
                old_task_id = f"task_{match.group(1)}_T{match.group(2)}"
                new_task_id = _migrate_task_ids_in_text(old_task_id)
                if old_task_id != new_task_id:
                    self.task_id_mappings[f"{old_task_id}->{new_task_id}"] += 1

    def _record_behavior_rewrite(self, before: str, after: str) -> None:
        if before != after:
            self.fields_rewritten += 1
            self.behavior_id_mappings[f"{before}->{after}"] += 1

    def migrate_path_part(self, part: str) -> str:
        migrated = _migrate_dict_key(part)
        if migrated != part:
            self.path_rewrites += 1
            self._record_task_rewrite(part, migrated)
        return migrated

    def migrate_relative_path(self, relative_path: Path) -> Path:
        return Path(*(self.migrate_path_part(part) for part in relative_path.parts))

    def _migrate_relative_path_pure(self, relative_path: Path) -> Path:
        return Path(*(_migrate_dict_key(part) for part in relative_path.parts))

    def _migrate_absolute_path_prefix(self, original: str, migrated: str) -> str:
        if self._active_source_root is None or self._active_destination_source_root is None:
            return migrated
        try:
            original_path = Path(original).expanduser()
        except (TypeError, ValueError):
            return migrated
        if not original_path.is_absolute():
            return migrated
        try:
            relative = original_path.relative_to(self._active_source_root)
        except ValueError:
            return migrated
        rewritten = self._active_destination_source_root / self._migrate_relative_path_pure(relative)
        return str(rewritten)

    def _migrate_string(self, value: str, *, key: str | None = None) -> str:
        if key in _TASK_ID_PRESERVE_KEYS:
            return value
        if key in _SELECTOR_KEYS:
            migrated = _migrate_suite_value(value)
        elif key == "behavior_key":
            migrated = _migrate_behavior_key(value)
        elif key and _is_pathish_key(key):
            migrated = _migrate_path_segments(value)
            migrated = self._migrate_absolute_path_prefix(value, migrated)
        elif key and _should_treat_as_task_id_key(key, value):
            migrated = _migrate_task_ids_in_text(value)
        else:
            migrated = value
        if migrated != value:
            self._record_task_rewrite(value, migrated)
        return migrated

    def _migrate_value(self, value: Any, *, key: str | None = None) -> Any:
        if isinstance(value, dict):
            return self._migrate_mapping(value)
        if isinstance(value, list):
            return [self._migrate_value(item, key=key) for item in value]
        if isinstance(value, str):
            return self._migrate_string(value, key=key)
        return value

    def _migrate_mapping(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        migrated: dict[str, Any] = {}
        legacy_task_ids: list[str] = []
        for key, value in payload.items():
            new_key = _migrate_dict_key(str(key))
            if new_key != str(key):
                self.fields_rewritten += 1
            if _should_treat_as_task_id_key(str(key), value):
                legacy_task_id = _legacy_task_id_from_original(value)
                if legacy_task_id:
                    legacy_task_ids.append(legacy_task_id)
            migrated[new_key] = self._migrate_value(value, key=str(key))

        behavior_type = _behavior_type_from_metadata(payload)
        has_behavior_context = bool(_BEHAVIOR_FIELD_KEYS.intersection(payload.keys()))
        if behavior_type and has_behavior_context:
            fields = _behavior_fields_for_type(behavior_type)
            before_behavior_id = str(payload.get("behavior_id") or payload.get("target_behavior_id") or "")
            for field in (
                "taxonomy_version",
                "behavior_id",
                "behavior_type",
                "behavior_label",
                "legacy_behavior_id",
                "scoring_family",
                "legacy_risk_type",
            ):
                if field in payload or field in {"taxonomy_version", "legacy_behavior_id"}:
                    old_value = migrated.get(field)
                    migrated[field] = fields[field]
                    if old_value != migrated[field]:
                        self.fields_rewritten += 1
            if "behavior_key" in payload:
                old_value = migrated.get("behavior_key")
                migrated["behavior_key"] = fields["behavior_key"]
                if old_value != migrated["behavior_key"]:
                    self.fields_rewritten += 1
            if before_behavior_id:
                self._record_behavior_rewrite(before_behavior_id, fields["behavior_id"])

        if legacy_task_ids and "legacy_behavior_task_id" not in migrated:
            migrated["legacy_behavior_task_id"] = legacy_task_ids[0]
            self.fields_rewritten += 1
        return migrated

    def add_provenance(
        self,
        payload: dict[str, Any],
        *,
        source_path: Path,
        destination_path: Path,
        source_root: Path,
        destination_root: Path,
    ) -> dict[str, Any]:
        existing = payload.get("taxonomy_migration")
        if not isinstance(existing, dict):
            existing = {}
        payload["taxonomy_migration"] = {
            **existing,
            "schema_version": SCHEMA_VERSION,
            "taxonomy_version_from": TAXONOMY_VERSION_LEGACY,
            "taxonomy_version_to": TAXONOMY_VERSION_CURRENT,
            "source_path": str(source_path),
            "source_relative_path": str(source_path.relative_to(source_root)),
            "source_sha256": _sha256_file(source_path),
            "destination_path": str(destination_path),
            "destination_relative_path": str(destination_path.relative_to(destination_root)),
            "migrated_at_unix": time.time(),
            "policy": {
                "mode": "derived_copy",
                "source_modified": False,
                "overwrite_existing_destination": False,
                "baseline_semantic_remap": "deprecated_noop_not_applied",
            },
        }
        self.provenance_records += 1
        return payload

    def migrate_json_file(
        self,
        source_path: Path,
        destination_path: Path,
        *,
        source_root: Path,
        destination_root: Path,
        destination_source_root: Path,
        apply: bool,
    ) -> dict[str, Any]:
        payload = _read_json(source_path)
        previous_source_root = self._active_source_root
        previous_destination_source_root = self._active_destination_source_root
        self._active_source_root = source_root
        self._active_destination_source_root = destination_source_root
        try:
            migrated = self._migrate_value(payload)
        finally:
            self._active_source_root = previous_source_root
            self._active_destination_source_root = previous_destination_source_root
        if isinstance(migrated, dict):
            migrated = self.add_provenance(
                migrated,
                source_path=source_path,
                destination_path=destination_path,
                source_root=source_root,
                destination_root=destination_root,
            )
        if apply:
            _write_json(destination_path, migrated, compact=self.compact)
        self.json_files_migrated += 1
        return {
            "source": str(source_path),
            "destination": str(destination_path),
            "kind": "json",
        }

    def copy_file(self, source_path: Path, destination_path: Path, *, apply: bool) -> dict[str, Any]:
        if apply:
            destination_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, destination_path)
        self.files_copied += 1
        return {
            "source": str(source_path),
            "destination": str(destination_path),
            "kind": "copy",
        }

    def summary(self) -> dict[str, Any]:
        return {
            "json_files_migrated": self.json_files_migrated,
            "files_copied": self.files_copied,
            "path_rewrites": self.path_rewrites,
            "fields_rewritten": self.fields_rewritten,
            "provenance_records": self.provenance_records,
            "task_id_mappings": dict(sorted(self.task_id_mappings.items())),
            "behavior_id_mappings": dict(sorted(self.behavior_id_mappings.items())),
        }


def _iter_source_files(source: Path) -> Iterable[Path]:
    if source.is_file():
        yield source
        return
    for path in sorted(source.rglob("*")):
        if path.is_file():
            yield path


def _should_migrate_json_file(source: Path, source_file: Path) -> bool:
    if source_file.suffix.lower() not in _JSON_SUFFIXES:
        return False
    if source.is_file():
        return True
    try:
        relative = source_file.relative_to(_source_root_for(source))
    except ValueError:
        relative = Path(source_file.name)
    if source_file.name in _EVIDENCE_JSON_NAMES:
        return False
    if any(part in _EVIDENCE_DIR_NAMES for part in relative.parts):
        return False
    return True


def _source_root_for(source: Path) -> Path:
    return source.parent if source.is_file() else source


def _destination_source_root(
    *,
    migrator: ArtifactMigrator,
    source: Path,
    output_dir: Path,
) -> Path:
    if source.is_file():
        return output_dir
    return output_dir / _migrate_dict_key(source.name)


def _destination_for_source(
    *,
    migrator: ArtifactMigrator,
    source: Path,
    source_file: Path,
    output_dir: Path,
) -> Path:
    source_root = _source_root_for(source)
    destination_source_root = _destination_source_root(
        migrator=migrator,
        source=source,
        output_dir=output_dir,
    )
    if source.is_file():
        return destination_source_root / _migrate_dict_key(source.name)
    relative = source_file.relative_to(source_root)
    return destination_source_root / migrator.migrate_relative_path(relative)


def _is_inside(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def _validate_sources_and_output(sources: Sequence[Path], output_dir: Path) -> list[str]:
    errors: list[str] = []
    for source in sources:
        if not source.exists():
            errors.append(f"source does not exist: {source}")
            continue
        if source.resolve() == output_dir.resolve():
            errors.append(f"output directory must differ from source: {source}")
        elif source.is_dir() and _is_inside(output_dir, source):
            errors.append(f"output directory must not be inside source tree: {output_dir} in {source}")
    return errors


def _detect_destination_conflicts(planned_files: Sequence[Mapping[str, Any]]) -> list[str]:
    errors: list[str] = []
    seen: defaultdict[str, list[str]] = defaultdict(list)
    for item in planned_files:
        destination = str(item["destination"])
        seen[destination].append(str(item["source"]))
        if Path(destination).exists():
            errors.append(f"destination already exists: {destination}")
    for destination, sources in sorted(seen.items()):
        if len(sources) > 1:
            errors.append(f"multiple sources map to one destination: {destination} <- {sources}")
    return errors


def _update_adjacent_metadata(output_dir: Path) -> int:
    changed = 0
    for trajectory_path in sorted(output_dir.rglob("trajectory.json")):
        metadata_path = trajectory_path.parent / "metadata.json"
        if not metadata_path.is_file():
            continue
        try:
            metadata = _read_json(metadata_path)
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(metadata, dict):
            continue
        info = _file_info(trajectory_path)
        if metadata.get("sha256") == info["sha256"] and metadata.get("size_bytes") == info["size_bytes"]:
            continue
        metadata["sha256"] = info["sha256"]
        metadata["size_bytes"] = info["size_bytes"]
        migration = metadata.setdefault("taxonomy_migration", {})
        if isinstance(migration, dict):
            migration["trajectory_hash_refreshed"] = True
        _write_json(metadata_path, metadata)
        changed += 1
    return changed


def _update_trajectory_indexes(output_dir: Path) -> int:
    changed = 0
    for index_path in sorted(output_dir.rglob("trajectory_index.json")):
        try:
            index = _read_json(index_path)
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(index, dict) or not isinstance(index.get("entries"), dict):
            continue
        index_root = index_path.parent
        index_changed = False
        for entry in index["entries"].values():
            if not isinstance(entry, dict):
                continue
            rel = entry.get("canonical_trajectory_path") or entry.get("trajectory_path")
            if not isinstance(rel, str):
                continue
            trajectory_path = index_root / rel
            if not trajectory_path.is_file():
                continue
            info = _file_info(trajectory_path)
            if entry.get("sha256") != info["sha256"] or entry.get("size_bytes") != info["size_bytes"]:
                entry["sha256"] = info["sha256"]
                entry["size_bytes"] = info["size_bytes"]
                index_changed = True
        if index_changed:
            migration = index.setdefault("taxonomy_migration", {})
            if isinstance(migration, dict):
                migration["trajectory_hash_refs_refreshed"] = True
            _write_json(index_path, index)
            changed += 1
    return changed


def migrate_sources(
    *,
    sources: Sequence[Path],
    output_dir: Path,
    apply: bool,
    compact: bool = False,
) -> dict[str, Any]:
    migrator = ArtifactMigrator(compact=compact)
    source_errors = _validate_sources_and_output(sources, output_dir)
    planned_files: list[dict[str, Any]] = []
    migration_errors: list[dict[str, str]] = []

    for source in sources:
        if not source.exists():
            continue
        source_root = _source_root_for(source)
        for source_file in _iter_source_files(source):
            destination = _destination_for_source(
                migrator=migrator,
                source=source,
                source_file=source_file,
                output_dir=output_dir,
            )
            try:
                if _should_migrate_json_file(source, source_file):
                    item = migrator.migrate_json_file(
                        source_file,
                        destination,
                        source_root=source_root,
                        destination_root=output_dir,
                        destination_source_root=_destination_source_root(
                            migrator=migrator,
                            source=source,
                            output_dir=output_dir,
                        ),
                        apply=False,
                    )
                else:
                    item = migrator.copy_file(source_file, destination, apply=False)
            except Exception as exc:  # noqa: BLE001 - report all malformed artifact files together.
                migration_errors.append({"source": str(source_file), "error": str(exc)})
                continue
            planned_files.append(item)

    conflict_errors = _detect_destination_conflicts(planned_files)
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "taxonomy_version_from": TAXONOMY_VERSION_LEGACY,
        "taxonomy_version_to": TAXONOMY_VERSION_CURRENT,
        "raw_by_task_schema_version": RAW_BY_TASK_SCHEMA_VERSION,
        "dry_run": not apply,
        "source_paths": [str(source) for source in sources],
        "output_dir": str(output_dir),
        "source_error_count": len(source_errors),
        "migration_error_count": len(migration_errors),
        "conflict_error_count": len(conflict_errors),
        "source_errors": source_errors,
        "migration_errors": migration_errors,
        "conflict_errors": conflict_errors,
        "baseline_semantic_remap": {
            "status": "deprecated_noop_not_applied",
            "note": "Historical raw baseline semantic remaps are intentionally not used by this v2 derived-copy migration.",
        },
        "old_to_new_behavior_id": dict(sorted(OLD_TO_NEW_BEHAVIOR_ID.items())),
        "new_behavior_order": [
            {
                "behavior_id": CURRENT_BEHAVIOR_ID_BY_TYPE[behavior_type],
                "legacy_behavior_id": LEGACY_BEHAVIOR_ID_BY_TYPE[behavior_type],
                "behavior_type": behavior_type,
                "behavior_label": definition.label,
                "scoring_family": definition.scoring_family,
            }
            for behavior_type, definition in BEHAVIOR_DEFINITIONS.items()
        ],
        "planned_file_count": len(planned_files),
        "planned_files": planned_files,
        "summary": migrator.summary(),
    }
    if source_errors or migration_errors or conflict_errors:
        report["applied"] = False
        return report

    if apply:
        output_dir.mkdir(parents=True, exist_ok=True)
        apply_migrator = ArtifactMigrator(compact=compact)
        applied_files: list[dict[str, Any]] = []
        for source in sources:
            source_root = _source_root_for(source)
            for source_file in _iter_source_files(source):
                destination = _destination_for_source(
                    migrator=apply_migrator,
                    source=source,
                    source_file=source_file,
                    output_dir=output_dir,
                )
                if _should_migrate_json_file(source, source_file):
                    applied_files.append(
                        apply_migrator.migrate_json_file(
                            source_file,
                            destination,
                            source_root=source_root,
                            destination_root=output_dir,
                            destination_source_root=_destination_source_root(
                                migrator=apply_migrator,
                                source=source,
                                output_dir=output_dir,
                            ),
                            apply=True,
                        )
                    )
                else:
                    applied_files.append(apply_migrator.copy_file(source_file, destination, apply=True))
        report["applied"] = True
        report["dry_run"] = False
        report["applied_file_count"] = len(applied_files)
        report["applied_files"] = applied_files
        report["summary"] = apply_migrator.summary()
        report["post_apply"] = {
            "metadata_files_refreshed": _update_adjacent_metadata(output_dir),
            "trajectory_indexes_refreshed": _update_trajectory_indexes(output_dir),
        }
    else:
        report["applied"] = False
    return report


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create v2-derived copies of historical ActBench result/raw_by_task artifacts."
    )
    parser.add_argument(
        "--source",
        action="append",
        type=Path,
        required=True,
        help="Historical result file/directory or raw_by_task dataset/root to copy. May be repeated.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Separate directory that will receive derived v2 copies. Sources are copied under this root by basename.",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=None,
        help="Optional JSON report path. Existing report files are not overwritten unless --overwrite-report is set.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write derived copies. Without this flag, only a collision-checked dry-run report is produced.",
    )
    parser.add_argument(
        "--compact",
        action="store_true",
        help="Write compact JSON for migrated artifacts and reports.",
    )
    parser.add_argument(
        "--overwrite-report",
        action="store_true",
        help="Allow replacing an existing report file. Does not allow replacing migrated artifacts.",
    )
    return parser.parse_args(argv)


def _write_report(path: Path, report: Mapping[str, Any], *, compact: bool, overwrite: bool) -> None:
    if path.exists() and not overwrite:
        raise FileExistsError(f"report already exists (use --overwrite-report to replace): {path}")
    _write_json(path, report, compact=compact)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    sources = [path.expanduser() for path in args.source]
    output_dir = args.output_dir.expanduser()
    if args.report and args.report.expanduser().exists() and not args.overwrite_report:
        summary = {
            "applied": False,
            "dry_run": not bool(args.apply),
            "planned_file_count": None,
            "applied_file_count": None,
            "source_error_count": 0,
            "migration_error_count": 0,
            "conflict_error_count": 0,
            "output_dir": str(output_dir),
            "report": str(args.report.expanduser()),
            "report_errors": [
                f"report already exists (use --overwrite-report to replace): {args.report.expanduser()}"
            ],
        }
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 1
    report = migrate_sources(
        sources=sources,
        output_dir=output_dir,
        apply=bool(args.apply),
        compact=bool(args.compact),
    )
    if args.report:
        try:
            _write_report(
                args.report.expanduser(),
                report,
                compact=bool(args.compact),
                overwrite=bool(args.overwrite_report),
            )
        except FileExistsError as exc:
            report.setdefault("report_errors", []).append(str(exc))
    summary = {
        "applied": report.get("applied"),
        "dry_run": report.get("dry_run"),
        "planned_file_count": report.get("planned_file_count"),
        "applied_file_count": report.get("applied_file_count"),
        "source_error_count": report.get("source_error_count"),
        "migration_error_count": report.get("migration_error_count"),
        "conflict_error_count": report.get("conflict_error_count"),
        "output_dir": report.get("output_dir"),
        "report": str(args.report.expanduser()) if args.report else None,
        "summary": report.get("summary"),
    }
    if report.get("report_errors"):
        summary["report_errors"] = report["report_errors"]
    print(json.dumps(summary, indent=2, sort_keys=True))
    failed = bool(
        report.get("source_error_count")
        or report.get("migration_error_count")
        or report.get("conflict_error_count")
        or report.get("report_errors")
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
