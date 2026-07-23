#!/usr/bin/env python3
"""Plan or apply the ActBench B-class v1→v2 task-id migration.

The v2 taxonomy changes B-class numbering while keeping behavior slugs stable.
Dry-run mode emits a collision-checked report.  Apply mode performs the registry
migration with two-phase directory renames, rewrites task/clean-source metadata,
and updates in-repo task-id references outside historical result directories.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import yaml

SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = SCRIPTS_ROOT.parent
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from lib_taxonomy import (  # noqa: E402
    BEHAVIOR_DEFINITIONS,
    CURRENT_BEHAVIOR_ID_BY_TYPE,
    LEGACY_BEHAVIOR_ID_BY_TYPE,
    OLD_TO_NEW_BEHAVIOR_ID,
    TAXONOMY_VERSION_CURRENT,
    current_behavior_id_for_type,
    infer_behavior_from_metadata,
    legacy_behavior_id_for_type,
)

_TASK_ID_RE = re.compile(r"^task_(B(?:[1-9]|1[0-5]))_T(\d+)$")
_TEXT_SUFFIXES = {
    ".cfg",
    ".ini",
    ".json",
    ".md",
    ".py",
    ".rst",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}
_SKIP_DIR_NAMES = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    "__pycache__",
    "node_modules",
}


def _read_yaml(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"metadata must be a mapping: {path}")
    return payload


def _write_yaml(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(
        yaml.safe_dump(dict(payload), sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON metadata must be an object: {path}")
    return payload


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(json.dumps(dict(payload), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _task_number(task_id: str) -> str | None:
    match = _TASK_ID_RE.match(task_id)
    return match.group(2) if match else None


def _task_behavior_id(task_id: str) -> str | None:
    match = _TASK_ID_RE.match(task_id)
    return match.group(1) if match else None


def _task_display_id(task_id: str) -> str:
    return task_id.removeprefix("task_")


def _planned_task_id(old_task_id: str, new_behavior_id: str) -> str:
    task_number = _task_number(old_task_id)
    if task_number is None:
        return old_task_id
    return f"task_{new_behavior_id}_T{task_number}"


def _task_sort_key(task_id: str) -> tuple[int, int, str]:
    match = _TASK_ID_RE.match(task_id)
    if not match:
        return (999, 999, task_id)
    behavior_num = int(match.group(1)[1:])
    task_num = int(match.group(2))
    return (behavior_num, task_num, task_id)


def build_report(tasks_dir: Path) -> dict[str, Any]:
    task_files = sorted(tasks_dir.glob("task_B*_T*/task.yaml"))
    planned: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    new_ids: defaultdict[str, list[str]] = defaultdict(list)
    counts = Counter()

    for task_file in task_files:
        task_dir = task_file.parent
        try:
            metadata = _read_yaml(task_file)
            inference = infer_behavior_from_metadata(metadata, path=task_file)
        except Exception as exc:  # noqa: BLE001 - report all metadata issues in one dry-run.
            errors.append({"path": str(task_file), "error": str(exc)})
            continue

        current_task_id = str(metadata.get("id") or task_dir.name)
        legacy_behavior_task_id = str(metadata.get("legacy_behavior_task_id") or current_task_id)
        old_behavior_id = _task_behavior_id(legacy_behavior_task_id) or str(
            metadata.get("legacy_behavior_id") or metadata.get("behavior_id") or ""
        )
        legacy_behavior_id = legacy_behavior_id_for_type(inference.behavior_type)
        new_behavior_id = current_behavior_id_for_type(inference.behavior_type)
        new_task_id = _planned_task_id(current_task_id, new_behavior_id)
        new_ids[new_task_id].append(current_task_id)
        counts[new_behavior_id] += 1

        planned.append(
            {
                "old_task_id": legacy_behavior_task_id,
                "current_task_id": current_task_id,
                "current_task_dir": str(task_dir.relative_to(tasks_dir.parent)),
                "old_behavior_id_from_task_id": old_behavior_id,
                "legacy_behavior_id": legacy_behavior_id,
                "new_task_id": new_task_id,
                "new_task_dir": str((tasks_dir / new_task_id).relative_to(tasks_dir.parent)),
                "behavior_type": inference.behavior_type,
                "behavior_label": inference.behavior_label,
                "new_behavior_id": new_behavior_id,
                "scoring_family": inference.scoring_family,
                "legacy_risk_type": inference.legacy_risk_type,
                "rename_required": current_task_id != new_task_id or task_dir.name != new_task_id,
                "metadata_updates": {
                    "taxonomy_version": TAXONOMY_VERSION_CURRENT,
                    "id": new_task_id,
                    "behavior_id": new_behavior_id,
                    "behavior_label": inference.behavior_label,
                    "legacy_behavior_id": legacy_behavior_id,
                    "legacy_behavior_task_id": legacy_behavior_task_id,
                },
            }
        )

    conflicts = {
        new_task_id: old_task_ids
        for new_task_id, old_task_ids in sorted(new_ids.items())
        if len(old_task_ids) > 1
    }
    missing_expected_counts = [
        behavior_id
        for behavior_id in CURRENT_BEHAVIOR_ID_BY_TYPE.values()
        if behavior_id not in counts
    ]

    return {
        "schema_version": "actbench.behavior_taxonomy_migration_plan.v1",
        "taxonomy_version_from": "actbench.behavior_taxonomy.v1",
        "taxonomy_version_to": TAXONOMY_VERSION_CURRENT,
        "tasks_dir": str(tasks_dir),
        "dry_run": True,
        "task_count": len(planned),
        "error_count": len(errors),
        "rename_count": sum(1 for item in planned if item["rename_required"]),
        "unchanged_count": sum(1 for item in planned if not item["rename_required"]),
        "conflict_count": len(conflicts),
        "counts_by_new_behavior_id": dict(sorted(counts.items())),
        "missing_expected_behavior_ids": missing_expected_counts,
        "old_to_new_behavior_id": dict(sorted(OLD_TO_NEW_BEHAVIOR_ID.items())),
        "behavior_order_v2": [
            {
                "behavior_id": definition.id,
                "legacy_behavior_id": LEGACY_BEHAVIOR_ID_BY_TYPE[behavior_type],
                "behavior_type": behavior_type,
                "behavior_label": definition.label,
                "scoring_family": definition.scoring_family,
            }
            for behavior_type, definition in BEHAVIOR_DEFINITIONS.items()
        ],
        "baseline_semantic_remap": {
            "status": "deprecated",
            "note": "Historical raw baseline semantic remaps are intentionally not carried into the v2 taxonomy migration.",
        },
        "conflicts": conflicts,
        "errors": errors,
        "tasks": sorted(planned, key=lambda item: _task_sort_key(item["new_task_id"])),
    }


def _rename_dirs_two_phase(
    root: Path,
    pairs: Sequence[tuple[str, str]],
    *,
    temp_prefix: str,
) -> int:
    renames = [(old, new) for old, new in pairs if old != new]
    if not renames:
        return 0

    temp_pairs: list[tuple[Path, Path, Path]] = []
    for old_name, new_name in renames:
        old_path = root / old_name
        new_path = root / new_name
        temp_path = root / f"{temp_prefix}{old_name}"
        if not old_path.is_dir():
            raise FileNotFoundError(f"expected directory to migrate: {old_path}")
        if temp_path.exists():
            raise FileExistsError(f"temporary migration path already exists: {temp_path}")
        temp_pairs.append((old_path, temp_path, new_path))

    for old_path, temp_path, _new_path in temp_pairs:
        old_path.rename(temp_path)
    try:
        for _old_path, temp_path, new_path in temp_pairs:
            if new_path.exists():
                raise FileExistsError(f"migration target already exists after temp phase: {new_path}")
            temp_path.rename(new_path)
    except Exception:
        # Best-effort rollback for temp directories not yet moved.  Directories already
        # moved to final names are left in place so the failure remains inspectable.
        for old_path, temp_path, _new_path in temp_pairs:
            if temp_path.exists() and not old_path.exists():
                temp_path.rename(old_path)
        raise
    return len(renames)


def _rewrite_task_metadata(tasks_dir: Path, item: Mapping[str, Any]) -> None:
    task_id = str(item["new_task_id"])
    task_yaml = tasks_dir / task_id / "task.yaml"
    metadata = _read_yaml(task_yaml)
    metadata["id"] = task_id
    metadata["taxonomy_version"] = TAXONOMY_VERSION_CURRENT
    metadata["behavior_type"] = item["behavior_type"]
    metadata["behavior_id"] = item["new_behavior_id"]
    metadata["behavior_label"] = item["behavior_label"]
    metadata["scoring_family"] = item["scoring_family"]
    metadata["legacy_risk_type"] = item["legacy_risk_type"]
    metadata["legacy_behavior_id"] = item["legacy_behavior_id"]
    metadata["legacy_behavior_task_id"] = item["old_task_id"]
    clean_source = metadata.get("clean_source")
    if isinstance(clean_source, dict) and clean_source.get("bundle_path"):
        clean_source["bundle_path"] = f"clean_scenes/{task_id}"
    _write_yaml(task_yaml, metadata)

    manifest_path = tasks_dir / task_id / "manifest.json"
    if manifest_path.exists():
        manifest = _read_json(manifest_path)
        manifest["task_id"] = task_id
        manifest["taxonomy_version"] = TAXONOMY_VERSION_CURRENT
        manifest["behavior_type"] = item["behavior_type"]
        manifest["behavior_id"] = item["new_behavior_id"]
        manifest["behavior_label"] = item["behavior_label"]
        manifest["scoring_family"] = item["scoring_family"]
        manifest["legacy_risk_type"] = item["legacy_risk_type"]
        manifest["legacy_behavior_id"] = item["legacy_behavior_id"]
        manifest["legacy_behavior_task_id"] = item["old_task_id"]
        clean_manifest = manifest.get("clean_source")
        if isinstance(clean_manifest, dict) and clean_manifest.get("bundle_path"):
            clean_manifest["bundle_path"] = f"clean_scenes/{task_id}"
        _write_json(manifest_path, manifest)


def _rewrite_clean_scene_metadata(clean_root: Path, item: Mapping[str, Any]) -> None:
    task_id = str(item["new_task_id"])
    scene_yaml = clean_root / task_id / "scenario.yaml"
    if scene_yaml.exists():
        scene = _read_yaml(scene_yaml)
        scene["taxonomy_version"] = TAXONOMY_VERSION_CURRENT
        scene["behavior_type"] = item["behavior_type"]
        scene["behavior_id"] = item["new_behavior_id"]
        scene["behavior_label"] = item["behavior_label"]
        scene["scoring_family"] = item["scoring_family"]
        scene["legacy_risk_type"] = item["legacy_risk_type"]
        scene["legacy_behavior_id"] = item["legacy_behavior_id"]
        scene["legacy_behavior_task_id"] = item["old_task_id"]
        _write_yaml(scene_yaml, scene)


def _iter_text_files(roots: Iterable[Path]) -> Iterable[Path]:
    for root in roots:
        if root.is_file():
            if root.suffix in _TEXT_SUFFIXES:
                yield root
            continue
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if any(part in _SKIP_DIR_NAMES for part in path.parts):
                continue
            if path.is_file() and path.suffix in _TEXT_SUFFIXES:
                yield path


def _simultaneous_replace(text: str, mapping: Mapping[str, str]) -> str:
    if not mapping:
        return text
    pattern = re.compile("|".join(re.escape(key) for key in sorted(mapping, key=len, reverse=True)))
    return pattern.sub(lambda match: mapping[match.group(0)], text)


def _rewrite_reference_files(repo_root: Path, mapping: Mapping[str, str]) -> int:
    display_mapping = {
        _task_display_id(old): _task_display_id(new)
        for old, new in mapping.items()
        if old != new
    }
    replacement_mapping = {**display_mapping, **{old: new for old, new in mapping.items() if old != new}}
    roots = [
        repo_root / "README.md",
        repo_root / "docs",
        repo_root / "scripts",
        repo_root / "tests",
    ]
    changed = 0
    for path in _iter_text_files(roots):
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        new_text = _simultaneous_replace(text, replacement_mapping)
        if new_text != text:
            path.write_text(new_text, encoding="utf-8")
            changed += 1
    return changed


def apply_report(report: Mapping[str, Any], *, tasks_dir: Path, update_references: bool) -> dict[str, Any]:
    if report.get("conflict_count") or report.get("error_count"):
        raise ValueError("refusing to apply migration report with conflicts or metadata errors")
    tasks = list(report.get("tasks") or [])
    reference_mapping = {str(item["old_task_id"]): str(item["new_task_id"]) for item in tasks}
    task_pairs = [
        (str(item.get("current_task_id") or item["old_task_id"]), str(item["new_task_id"]))
        for item in tasks
        if item.get("rename_required")
    ]
    clean_root = tasks_dir / "clean_scenes"

    task_renames = _rename_dirs_two_phase(
        tasks_dir,
        task_pairs,
        temp_prefix=".taxonomy_v2_tmp__",
    )
    clean_pairs = [(old, new) for old, new in task_pairs if (clean_root / old).exists()]
    clean_renames = _rename_dirs_two_phase(
        clean_root,
        clean_pairs,
        temp_prefix=".taxonomy_v2_tmp__",
    )

    for item in tasks:
        _rewrite_task_metadata(tasks_dir, item)
        _rewrite_clean_scene_metadata(clean_root, item)

    reference_files_changed = (
        _rewrite_reference_files(REPO_ROOT, reference_mapping) if update_references else 0
    )
    return {
        "applied": True,
        "task_renames": task_renames,
        "clean_source_renames": clean_renames,
        "metadata_tasks_updated": len(tasks),
        "reference_files_changed": reference_files_changed,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Plan or apply the ActBench B-class v1→v2 task-id migration."
    )
    parser.add_argument(
        "--tasks-dir",
        type=Path,
        default=REPO_ROOT / "tasks",
        help="Task registry to scan. Defaults to repository tasks/.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional JSON report path. The report is also summarized on stdout.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply the migration after generating a clean report.",
    )
    parser.add_argument(
        "--no-reference-update",
        action="store_true",
        help="With --apply, skip rewriting task-id references in README/docs/scripts/tests.",
    )
    parser.add_argument(
        "--compact",
        action="store_true",
        help="Write compact JSON instead of pretty-printed JSON.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    tasks_dir = args.tasks_dir.expanduser()
    report = build_report(tasks_dir)
    apply_summary: dict[str, Any] | None = None
    if args.apply:
        apply_summary = apply_report(
            report,
            tasks_dir=tasks_dir,
            update_references=not args.no_reference_update,
        )
        post_report = build_report(tasks_dir)
        report["post_apply"] = {
            "task_count": post_report["task_count"],
            "rename_count": post_report["rename_count"],
            "unchanged_count": post_report["unchanged_count"],
            "conflict_count": post_report["conflict_count"],
            "error_count": post_report["error_count"],
            "counts_by_new_behavior_id": post_report["counts_by_new_behavior_id"],
        }
        report["apply_summary"] = apply_summary
        report["dry_run"] = False

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        indent = None if args.compact else 2
        args.output.write_text(
            json.dumps(report, indent=indent, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    summary = {
        "task_count": report["task_count"],
        "rename_count": report["rename_count"],
        "unchanged_count": report["unchanged_count"],
        "conflict_count": report["conflict_count"],
        "error_count": report["error_count"],
        "counts_by_new_behavior_id": report["counts_by_new_behavior_id"],
        "applied": bool(args.apply),
        "apply_summary": apply_summary,
        "post_apply": report.get("post_apply"),
        "output": str(args.output) if args.output else None,
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    failed = bool(report["conflict_count"] or report["error_count"])
    post = report.get("post_apply") or {}
    failed = failed or bool(post.get("conflict_count") or post.get("error_count"))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
