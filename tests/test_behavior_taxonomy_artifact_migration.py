from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from benchmark.migrate_behavior_taxonomy_artifacts import migrate_sources  # noqa: E402
from lib_taxonomy import TAXONOMY_VERSION_CURRENT  # noqa: E402


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def test_artifact_migration_writes_derived_copy_without_touching_source(tmp_path: Path) -> None:
    source = tmp_path / "legacy_results"
    output = tmp_path / "v2_results"
    summary_path = source / "actbench_summary_0001_model.json"
    trajectory_path = source / "raw_pack" / "B6" / "task_B6_T01" / "run_1" / "trajectory.json"
    manifest_path = source / "raw_pack" / "manifest.json"
    source_paths_path = trajectory_path.parent / "source_paths.json"
    api_audit_path = trajectory_path.parent / "api" / "audit.json"

    _write_json(
        summary_path,
        {
            "schema_version": "actbench.summary.fixture",
            "suite": "task_B7_T01",
            "by_behavior": {
                "B7_unauthorized_api_invocation": {
                    "behavior_id": "B7",
                    "behavior_type": "unauthorized_api_invocation",
                    "behavior_label": "Unauthorized API Invocation",
                    "tasks": 1,
                }
            },
            "tasks": [
                {
                    "task_id": "task_B7_T01",
                    "display": "B7_T01",
                    "behavior_id": "B7",
                    "behavior_type": "unauthorized_api_invocation",
                    "behavior_label": "Unauthorized API Invocation",
                    "behavior_key": "B7_unauthorized_api_invocation",
                    "scoring_family": "tool_abuse",
                    "legacy_risk_type": "tool_abuse",
                }
            ],
        },
    )
    _write_json(
        manifest_path,
        {
            "schema_version": "actbench.raw_by_task.v1",
            "name": "raw_pack",
            "backend": "test",
            "target_model": "test/model",
            "suite_counts": {"B6": 1},
            "task_count": 1,
        },
    )
    _write_json(
        trajectory_path,
        {
            "schema_version": "actbench.trajectory.v1",
            "trajectory_id": "task_B6_T01_attempt",
            "canonical": {
                "slot_id": "B6/task_B6_T01/run_1",
                "suite": "B6",
                "task_id": "task_B6_T01",
                "trajectory_path": "raw_pack/B6/task_B6_T01/run_1/trajectory.json",
            },
            "run": {
                "context_metadata": {
                    "suite": "B6",
                    "baseline_task_id": "task_B6_T01",
                },
                "training_artifact_key": "task_B6_T01_attempt",
            },
            "task": {
                "task_id": "task_B6_T01",
                "source_path": str(source / "raw_pack" / "B6" / "task_B6_T01" / "task.json"),
                "frontmatter": {
                    "id": "task_B6_T01",
                    "behavior_id": "B6",
                    "behavior_type": "unauthorized_command_execution",
                    "behavior_label": "Unauthorized Command Execution",
                    "scoring_family": "unauthorized_execution",
                    "legacy_risk_type": "unauthorized_execution",
                },
            },
            "scoring_inputs": {
                "behavior": {
                    "behavior_id": "B6",
                    "behavior_type": "unauthorized_command_execution",
                    "behavior_label": "Unauthorized Command Execution",
                    "scoring_family": "unauthorized_execution",
                },
                "risk_type": "unauthorized_execution",
            },
            "transcript": {
                "entries": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": [
                                {
                                    "type": "text",
                                    "text": "Evidence text mentions task_B6_T01 and must stay byte-for-byte meaningful.",
                                }
                            ],
                        }
                    }
                ]
            },
            "artifacts": {
                "canonical_slot_id": "B6/task_B6_T01/run_1",
                "canonical_trajectory": "raw_pack/B6/task_B6_T01/run_1/trajectory.json",
                "canonical_trajectory_absolute": str(trajectory_path),
            },
        },
    )
    _write_json(
        source_paths_path,
        {
            "role": "attacked",
            "suite": "B6",
            "task_id": "task_B6_T01",
            "legacy_trajectory": str(trajectory_path),
            "canonical_trajectory": "raw_pack/B6/task_B6_T01/run_1/trajectory.json",
        },
    )
    _write_json(api_audit_path, {"B6": "task_B6_T01", "evidence": True})
    original_summary = summary_path.read_text(encoding="utf-8")
    original_trajectory = trajectory_path.read_text(encoding="utf-8")

    dry_run = migrate_sources(sources=[source], output_dir=output, apply=False)

    assert dry_run["applied"] is False
    assert dry_run["planned_file_count"] == 5
    assert not output.exists()
    assert dry_run["baseline_semantic_remap"]["status"] == "deprecated_noop_not_applied"

    report = migrate_sources(sources=[source], output_dir=output, apply=True)

    assert report["applied"] is True
    assert summary_path.read_text(encoding="utf-8") == original_summary
    assert trajectory_path.read_text(encoding="utf-8") == original_trajectory

    migrated_summary = _read_json(output / "legacy_results" / "actbench_summary_0001_model.json")
    assert migrated_summary["suite"] == "task_B9_T01"
    assert list(migrated_summary["by_behavior"]) == ["B9_unauthorized_api_invocation"]
    assert migrated_summary["by_behavior"]["B9_unauthorized_api_invocation"]["taxonomy_version"] == TAXONOMY_VERSION_CURRENT
    row = migrated_summary["tasks"][0]
    assert row["task_id"] == "task_B9_T01"
    assert row["behavior_id"] == "B9"
    assert row["scoring_family"] == "B9"
    assert row["legacy_risk_type"] == "tool_abuse"
    assert row["legacy_behavior_id"] == "B7"
    assert migrated_summary["taxonomy_migration"]["policy"]["mode"] == "derived_copy"

    migrated_manifest = _read_json(output / "legacy_results" / "raw_pack" / "manifest.json")
    assert migrated_manifest["suite_counts"] == {"B8": 1}
    assert migrated_manifest["taxonomy_migration"]["source_relative_path"] == "raw_pack/manifest.json"

    migrated_trajectory_path = output / "legacy_results" / "raw_pack" / "B8" / "task_B8_T01" / "run_1" / "trajectory.json"
    migrated_trajectory = _read_json(migrated_trajectory_path)
    assert migrated_trajectory["trajectory_id"] == "task_B8_T01_attempt"
    assert migrated_trajectory["canonical"]["suite"] == "B8"
    assert migrated_trajectory["canonical"]["task_id"] == "task_B8_T01"
    assert migrated_trajectory["canonical"]["slot_id"] == "B8/task_B8_T01/run_1"
    assert migrated_trajectory["task"]["task_id"] == "task_B8_T01"
    assert migrated_trajectory["task"]["frontmatter"]["taxonomy_version"] == TAXONOMY_VERSION_CURRENT
    assert migrated_trajectory["task"]["frontmatter"]["behavior_id"] == "B8"
    assert migrated_trajectory["task"]["frontmatter"]["scoring_family"] == "B8"
    assert migrated_trajectory["task"]["frontmatter"]["legacy_risk_type"] == "unauthorized_execution"
    assert migrated_trajectory["task"]["frontmatter"]["legacy_behavior_id"] == "B6"
    assert migrated_trajectory["scoring_inputs"]["behavior"]["behavior_id"] == "B8"
    assert migrated_trajectory["scoring_inputs"]["behavior"]["scoring_family"] == "B8"
    assert migrated_trajectory["transcript"]["entries"][0]["message"]["content"][0]["text"] == "Evidence text mentions task_B6_T01 and must stay byte-for-byte meaningful."
    assert migrated_trajectory["artifacts"]["canonical_trajectory"] == "raw_pack/B8/task_B8_T01/run_1/trajectory.json"
    assert migrated_trajectory["artifacts"]["canonical_trajectory_absolute"] == str(migrated_trajectory_path)

    migrated_source_paths = _read_json(output / "legacy_results" / "raw_pack" / "B8" / "task_B8_T01" / "run_1" / "source_paths.json")
    assert migrated_source_paths["suite"] == "B8"
    assert migrated_source_paths["task_id"] == "task_B8_T01"
    assert migrated_source_paths["legacy_trajectory"] == str(migrated_trajectory_path)

    migrated_api_audit = _read_json(output / "legacy_results" / "raw_pack" / "B8" / "task_B8_T01" / "run_1" / "api" / "audit.json")
    assert migrated_api_audit == {"B6": "task_B6_T01", "evidence": True}


def test_artifact_migration_refuses_existing_destinations(tmp_path: Path) -> None:
    source = tmp_path / "legacy_results"
    output = tmp_path / "v2_results"
    _write_json(source / "result.json", {"tasks": [{"task_id": "task_B12_T01"}]})

    first = migrate_sources(sources=[source], output_dir=output, apply=True)
    second = migrate_sources(sources=[source], output_dir=output, apply=True)

    assert first["applied"] is True
    assert second["applied"] is False
    assert second["conflict_error_count"] == 1
    assert "destination already exists" in second["conflict_errors"][0]
