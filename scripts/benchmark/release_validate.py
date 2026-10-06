"""Validators for ActBench public full and lightweight release artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import tarfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, Optional, Sequence
from urllib.parse import urlparse

from lib_safe_paths import ScenarioValidationError, safe_join, safe_relative_path
from lib_training_artifacts import safe_artifact_name

from benchmark.release_bundle import (
    FULL_COMBO_SCHEMA_VERSION,
    FULL_RELEASE_SCHEMA_VERSION,
    TASK_BUNDLE_SCHEMA_VERSION,
)
from benchmark.release_hf import HF_RELEASE_SCHEMA_VERSION
from benchmark.release_redaction import scan_release_tree, validate_checker_payload
from benchmark.release_scores import ReleaseScoreError, score_bool, sha256_file
from benchmark.trajectories import SUPPORTED_TRAJECTORY_SCHEMA_VERSIONS


@dataclass(frozen=True)
class ValidationIssue:
    path: str
    message: str


@dataclass
class ValidationResult:
    errors: list[ValidationIssue] = field(default_factory=list)
    warnings: list[ValidationIssue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def error(self, path: Path | str, message: str) -> None:
        self.errors.append(ValidationIssue(str(path), message))

    def warn(self, path: Path | str, message: str) -> None:
        self.warnings.append(ValidationIssue(str(path), message))

    def merge(self, other: "ValidationResult") -> None:
        self.errors.extend(other.errors)
        self.warnings.extend(other.warnings)

    def summary(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
            "errors": [issue.__dict__ for issue in self.errors],
            "warnings": [issue.__dict__ for issue in self.warnings],
        }


@dataclass(frozen=True)
class _FullComboRef:
    combo_id: str
    manifest_rel: str
    manifest_path: Path
    manifest: dict[str, Any]
    archive_rel: str
    archive_path: Optional[Path]
    archive_sha256: str
    archive_size_bytes: Optional[int]


class ReleaseValidationError(ValueError):
    """Raised by the validation CLI when a release is invalid."""


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _load_json(path: Path, result: ValidationResult) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except Exception as exc:
        result.error(path, f"Cannot read JSON: {exc}")
        return {}
    if not isinstance(payload, dict):
        result.error(path, "JSON root must be an object")
        return {}
    return payload


def _safe_relative_path(base: Path, value: str, result: ValidationResult, *, label: str, issue_path: Path) -> Optional[Path]:
    try:
        rel = safe_relative_path(value)
        current = base
        for part in rel.parts:
            current = current / part
            if current.is_symlink():
                raise ScenarioValidationError(f"path contains symbolic link component: {value}")
        return safe_join(base, value)
    except ScenarioValidationError as exc:
        result.error(issue_path, f"Unsafe {label} path: {value!r} ({exc})")
        return None


def _is_top_level_dir_path(path: Path, root: Path, dirname: str) -> bool:
    try:
        rel = path.relative_to(root)
    except ValueError:
        return False
    return bool(rel.parts) and rel.parts[0] == dirname


def _validate_no_symlinks(root: Path, result: ValidationResult) -> None:
    if root.is_symlink():
        result.error(root, "Release path must not be a symbolic link")
        return
    if not root.exists():
        return
    for path in sorted(root.rglob("*"), key=lambda item: item.parts):
        if path.is_symlink():
            result.error(path, "Release artifact must not be a symbolic link")


def _backend_identity_key(value: str) -> str:
    return str(value or "").strip().lower()


def _model_identity_key(value: str) -> str:
    text = str(value or "").strip()
    if "/" not in text:
        return text
    provider, model = text.split("/", 1)
    return f"{provider.lower()}/{model}"


def _safe_component(value: str, result: ValidationResult, *, label: str, issue_path: Path) -> Optional[str]:
    text = str(value or "")
    path = Path(text)
    if not text or text in {".", ".."} or path.is_absolute() or len(path.parts) != 1 or safe_artifact_name(text) != text:
        result.error(issue_path, f"Unsafe {label} path component: {value!r}")
        return None
    return text


def _int_metadata(value: Any, result: ValidationResult, *, path: Path, label: str) -> Optional[int]:
    if isinstance(value, bool) or value is None:
        result.error(path, f"{label} must be an integer")
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        result.error(path, f"{label} must be an integer: {value!r}")
        return None


def _json_equivalent(left: str, right: dict[str, Any], result: ValidationResult, path: Path, *, label: str) -> bool:
    try:
        parsed = json.loads(left)
    except json.JSONDecodeError as exc:
        result.error(path, f"Invalid {label} JSON: {exc}")
        return False
    if parsed != right:
        result.error(path, f"{label} does not match full release source")
        return False
    return True


def _read_jsonl(path: Path, result: ValidationResult) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError as exc:
                    result.error(path, f"Invalid JSONL line {line_number}: {exc}")
                    continue
                if not isinstance(payload, dict):
                    result.error(path, f"JSONL line {line_number} root must be object")
                    continue
                rows.append(payload)
    except Exception as exc:
        result.error(path, f"Cannot read JSONL: {exc}")
    return rows


def _validate_trajectory(path: Path, result: ValidationResult) -> Optional[dict[str, Any]]:
    if not path.is_file():
        result.error(path, "Missing trajectory file")
        return None
    payload = _load_json(path, result)
    schema = payload.get("schema_version")
    if schema not in SUPPORTED_TRAJECTORY_SCHEMA_VERSIONS:
        result.error(path, f"Unsupported trajectory schema {schema!r}")
    for issue in validate_checker_payload(payload, label=str(path)):
        result.error(path, issue)
    return payload


def _expected_score_summary(score: dict[str, Any], *, role: str) -> dict[str, Any]:
    if role == "attack":
        utility_attack = _as_dict(score.get("utility_attack"))
        return {
            "available": True,
            "scoring_semantics": score.get("scoring_semantics"),
            "ags": score.get("ags"),
            "attack_success": score.get("attack_success"),
            "attack_success_binary": score.get("attack_success_binary"),
            "python_attack_success_binary": score.get("python_attack_success_binary"),
            "llm_attack_success_binary": score.get("llm_attack_success_binary"),
            "binary_agreement": score.get("binary_agreement"),
            "binary_evidence_status": score.get("binary_evidence_status"),
            "ugs_attack": utility_attack.get("ugs"),
            "ugs_attack_python_utility": utility_attack.get("python_utility"),
            "ugs_attack_llm_utility": utility_attack.get("llm_utility"),
            "ugs_attack_evaluation_error": utility_attack.get("evaluation_error"),
            "evaluation_error": score_bool(score, "evaluation_error", default=False),
            "error_type": score.get("error_type", ""),
        }
    return {
        "available": True,
        "scoring_semantics": score.get("scoring_semantics"),
        "ugs": score.get("ugs"),
        "python_utility": score.get("python_utility"),
        "python_utility_raw": score.get("python_utility_raw"),
        "llm_utility": score.get("llm_utility"),
        "score_combination_policy": score.get("score_combination_policy"),
        "evaluation_error": score_bool(score, "evaluation_error", default=False),
        "error_type": score.get("error_type", ""),
    }


def _validate_explicit_binary(score: dict[str, Any], key: str) -> None:
    if key not in score or score.get(key) is None:
        return
    value = score.get(key)
    if isinstance(value, bool):
        return
    if isinstance(value, (int, float)) and not isinstance(value, bool) and value in (0, 1):
        return
    raise ReleaseScoreError(f"{key} must be an explicit 0/1 value, got {value!r}")


def _validate_score_payload(
    *,
    score_path: Path,
    run_record: dict[str, Any],
    role: str,
    require_scores: bool,
    result: ValidationResult,
) -> None:
    if not score_path.is_file():
        result.error(score_path, "Missing score sidecar")
        return
    score = _load_json(score_path, result)
    summary = _as_dict(run_record.get("score_summary"))
    if not score or score.get("available") is False:
        if require_scores:
            result.error(score_path, f"Missing required {role} score")
        return
    try:
        evaluation_error = score_bool(score, "evaluation_error", default=False)
        retired_fields = {
            "attack_success_threshold",
            "task_pass",
            "attack_pass",
            "pass",
            "is_success",
            "tacc",
        }
        present_retired = sorted(key for key in retired_fields if key in score and score.get(key) is not None)
        if present_retired:
            raise ReleaseScoreError(
                "Retired score fields are not allowed in a current release: "
                + ", ".join(present_retired)
            )
        if role == "attack":
            for key in (
                "attack_success_binary",
                "python_attack_success_binary",
                "llm_attack_success_binary",
            ):
                _validate_explicit_binary(score, key)
            for key in ("attack_pass", "pass", "is_success"):
                if key in score and score.get(key) is not None:
                    score_bool(score, key)
            utility_attack = _as_dict(score.get("utility_attack"))
            if utility_attack:
                nested_retired = sorted(
                    key for key in retired_fields if key in utility_attack and utility_attack.get(key) is not None
                )
                if nested_retired:
                    raise ReleaseScoreError(
                        "Retired attack utility fields are not allowed in a current release: "
                        + ", ".join(nested_retired)
                    )
                utility_error = score_bool(utility_attack, "evaluation_error", default=False)
                if not utility_error and utility_attack.get("ugs") is None:
                    raise ReleaseScoreError("Attack utility score is missing ugs")
    except ReleaseScoreError as exc:
        result.error(score_path, str(exc))
        return
    if role == "attack" and not evaluation_error and score.get("ags") is None and score.get("attack_success") is None:
        result.error(score_path, "Attack score is missing ags/attack_success")
    if role == "clean" and not evaluation_error and score.get("ugs") is None:
        result.error(score_path, "Clean score is missing ugs")
    expected_summary = _expected_score_summary(score, role=role)
    if summary.get("available") is False:
        result.error(score_path, f"score_summary says present {role} score is unavailable")
    elif summary and summary != expected_summary:
        result.error(score_path, "score.json does not match task-bundle score_summary")


def _trajectory_backend_model(payload: dict[str, Any]) -> tuple[str, str]:
    backend = _as_dict(payload.get("backend"))
    execution = _as_dict(payload.get("execution"))
    scoring_inputs = _as_dict(payload.get("scoring_inputs"))
    return (
        str(backend.get("name") or execution.get("backend") or scoring_inputs.get("backend_name") or ""),
        str(backend.get("model") or execution.get("model") or scoring_inputs.get("target_model") or ""),
    )


def _validate_run(
    *,
    run_dir: Path,
    run_record: dict[str, Any],
    role: str,
    require_scores: bool,
    result: ValidationResult,
    expected_backend: str = "",
    expected_model: str = "",
) -> None:
    trajectory_rel = str(run_record.get("trajectory") or "trajectory.json")
    trajectory = _safe_relative_path(run_dir, trajectory_rel, result, label="trajectory", issue_path=run_dir)
    if trajectory is None:
        return
    trajectory_payload = _validate_trajectory(trajectory, result)
    expected_trajectory_id = str(run_record.get("trajectory_id") or "")
    if trajectory_payload is not None and expected_trajectory_id:
        actual_trajectory_id = str(trajectory_payload.get("trajectory_id") or "")
        if actual_trajectory_id != expected_trajectory_id:
            result.error(
                trajectory,
                f"trajectory_id mismatch: manifest={expected_trajectory_id!r} payload={actual_trajectory_id!r}",
            )
    if trajectory_payload is not None:
        actual_backend, actual_model = _trajectory_backend_model(trajectory_payload)
        if expected_backend and actual_backend and _backend_identity_key(actual_backend) != _backend_identity_key(expected_backend):
            result.error(trajectory, f"backend mismatch: combo={expected_backend!r} trajectory={actual_backend!r}")
        if expected_model and actual_model and _model_identity_key(actual_model) != _model_identity_key(expected_model):
            result.error(trajectory, f"model mismatch: combo={expected_model!r} trajectory={actual_model!r}")
    expected_sha = str(run_record.get("trajectory_sha256") or "")
    if expected_sha and trajectory.is_file():
        actual_sha = sha256_file(trajectory)
        if actual_sha != expected_sha:
            result.error(trajectory, f"trajectory_sha256 mismatch: manifest={expected_sha} actual={actual_sha}")
    score_path = _safe_relative_path(
        run_dir,
        str(run_record.get("score") or "score.json"),
        result,
        label="score",
        issue_path=run_dir,
    )
    if score_path is not None:
        _validate_score_payload(
            score_path=score_path,
            run_record=run_record,
            role=role,
            require_scores=require_scores,
            result=result,
        )
    artifacts = _as_dict(run_record.get("artifacts"))
    workspace_ref = artifacts.get("workspace_after")
    if workspace_ref:
        workspace_path = _safe_relative_path(
            run_dir,
            str(workspace_ref),
            result,
            label="workspace_after",
            issue_path=run_dir,
        )
        if workspace_path is not None and not workspace_path.is_dir():
            result.error(workspace_path, "Referenced workspace_after directory is missing")
    api_refs = _as_dict(artifacts.get("api"))
    for key, rel in api_refs.items():
        if rel:
            api_path = _safe_relative_path(run_dir, str(rel), result, label="API artifact", issue_path=run_dir)
            if api_path is None:
                continue
            if key in {"fixtures", "logs"}:
                if not api_path.is_dir():
                    result.error(api_path, "Referenced API artifact directory is missing")
            elif not api_path.is_file():
                result.error(api_path, "Referenced API artifact is missing")


def _validate_checksums(combo_root: Path, manifest: dict[str, Any], result: ValidationResult) -> None:
    checksum_manifest = _as_dict(manifest.get("checksums"))
    files_rel = str(checksum_manifest.get("files") or "checksums/files.jsonl")
    sums_rel = str(checksum_manifest.get("sha256sums") or "checksums/sha256sums.txt")
    checksums = _safe_relative_path(
        combo_root,
        files_rel,
        result,
        label="checksum index",
        issue_path=combo_root / "manifest.json",
    )
    sums_path = _safe_relative_path(
        combo_root,
        sums_rel,
        result,
        label="sha256sums",
        issue_path=combo_root / "manifest.json",
    )
    if checksums is None or sums_path is None:
        return
    rows = _read_jsonl(checksums, result)
    seen: set[str] = set()
    for row in rows:
        rel = str(row.get("path") or "")
        if not rel:
            result.error(checksums, "Checksum row missing path")
            continue
        if rel in seen:
            result.error(checksums, f"Duplicate checksum path: {rel}")
            continue
        path = _safe_relative_path(combo_root, rel, result, label="checksum", issue_path=checksums)
        if path is None:
            continue
        seen.add(rel)
        if not path.is_file():
            result.error(path, "Checksum-listed file is missing")
            continue
        expected_size = row.get("size_bytes")
        if expected_size is not None:
            parsed_size = _int_metadata(expected_size, result, path=checksums, label="checksum size_bytes")
            if parsed_size is not None and path.stat().st_size != parsed_size:
                result.error(path, f"size mismatch: manifest={expected_size} actual={path.stat().st_size}")
        expected_sha = str(row.get("sha256") or "")
        actual_sha = sha256_file(path)
        if expected_sha != actual_sha:
            result.error(path, f"sha256 mismatch: manifest={expected_sha} actual={actual_sha}")
    expected_paths = {
        path.relative_to(combo_root).as_posix()
        for path in combo_root.rglob("*")
        if path.is_file()
        and not path.is_symlink()
        and not _is_top_level_dir_path(path, combo_root, "checksums")
        and not _is_top_level_dir_path(path, combo_root, "archives")
        and path != combo_root / "manifest.json"
    }
    missing = sorted(expected_paths - seen)
    for rel in missing[:20]:
        result.error(combo_root / rel, "File is missing from checksum index")
    if len(missing) > 20:
        result.error(checksums, f"{len(missing) - 20} additional files are missing from checksum index")
    declared_count = checksum_manifest.get("file_count")
    if declared_count != len(rows):
        result.error(checksums, f"checksum file_count mismatch: manifest={declared_count} actual={len(rows)}")
    expected_sums = "".join(f"{row.get('sha256', '')}  {row.get('path', '')}\n" for row in rows)
    try:
        actual_sums = sums_path.read_text(encoding="utf-8")
    except OSError as exc:
        result.error(sums_path, f"Cannot read sha256sums: {exc}")
    else:
        if actual_sums != expected_sums:
            result.error(sums_path, "sha256sums.txt does not match files.jsonl")


def validate_combo_release(
    combo_root: Path | str,
    *,
    expected_task_count: Optional[int] = 300,
    expected_attack_runs_per_task: int = 3,
    require_scores: bool = True,
    run_redaction_scan: bool = True,
) -> ValidationResult:
    combo_root = Path(combo_root).expanduser()
    result = ValidationResult()
    _validate_no_symlinks(combo_root, result)
    manifest = _load_json(combo_root / "manifest.json", result)
    if manifest.get("schema_version") != FULL_COMBO_SCHEMA_VERSION:
        result.error(combo_root / "manifest.json", f"Unsupported combo schema {manifest.get('schema_version')!r}")
    combo_id = _safe_component(str(manifest.get("combo_id") or combo_root.name), result, label="combo_id", issue_path=combo_root / "manifest.json")
    if combo_id and combo_id != combo_root.name:
        result.error(combo_root / "manifest.json", f"combo_id does not match directory name: {combo_id!r} != {combo_root.name!r}")
    task_bundles_path = _safe_relative_path(
        combo_root,
        str(manifest.get("task_bundles") or "task_bundles.jsonl"),
        result,
        label="task_bundles",
        issue_path=combo_root / "manifest.json",
    )
    task_records = _read_jsonl(task_bundles_path, result) if task_bundles_path is not None else []
    if expected_task_count is not None and len(task_records) != expected_task_count:
        result.error(task_bundles_path or combo_root, f"Expected {expected_task_count} tasks, found {len(task_records)}")
    clean_count = 0
    attack_count = 0
    seen_tasks: set[tuple[str, str]] = set()
    for task in task_records:
        if task.get("schema_version") != TASK_BUNDLE_SCHEMA_VERSION:
            result.error(task_bundles_path or combo_root, f"Task bundle has unsupported schema {task.get('schema_version')!r}")
        suite = _safe_component(str(task.get("suite") or ""), result, label="suite", issue_path=task_bundles_path or combo_root)
        task_id = _safe_component(str(task.get("task_id") or ""), result, label="task_id", issue_path=task_bundles_path or combo_root)
        if suite is None or task_id is None:
            continue
        if (suite, task_id) in seen_tasks:
            result.error(task_bundles_path or combo_root, f"Duplicate task bundle: {suite}/{task_id}")
        seen_tasks.add((suite, task_id))
        task_root = combo_root / "tasks" / suite / task_id
        task_manifest_path = task_root / "manifest.json"
        task_manifest = _load_json(task_manifest_path, result)
        if task_manifest and task_manifest != task:
            result.error(task_manifest_path, "Per-task manifest does not match task_bundles.jsonl")
        clean = _as_dict(task.get("clean"))
        if not clean:
            result.error(task_root, "Task is missing clean record")
        else:
            clean_count += 1
            _validate_run(
                run_dir=task_root / "clean",
                run_record=clean,
                role="clean",
                require_scores=require_scores,
                result=result,
                expected_backend=str(manifest.get("backend") or ""),
                expected_model=str(manifest.get("model") or ""),
            )
        attacks = [_as_dict(item) for item in _as_list(task.get("attacks"))]
        if len(attacks) != expected_attack_runs_per_task:
            result.error(task_root, f"Expected {expected_attack_runs_per_task} attacks, found {len(attacks)}")
        expected_runs = list(range(1, expected_attack_runs_per_task + 1))
        actual_runs: list[int] = []
        for attack in attacks:
            run_value = _int_metadata(attack.get("run_number"), result, path=task_root, label="attack run_number")
            if run_value is not None:
                actual_runs.append(run_value)
        if sorted(actual_runs) != expected_runs:
            result.error(task_root, f"Expected attack run numbers {expected_runs}, found {sorted(actual_runs)}")
        seen_slots: set[str] = set()
        for attack in attacks:
            attack_count += 1
            slot = _safe_component(
                str(attack.get("attack_slot") or f"run_{attack.get('run_number')}"),
                result,
                label="attack_slot",
                issue_path=task_bundles_path or task_root,
            )
            if slot is None:
                continue
            if slot in seen_slots:
                result.error(task_root, f"Duplicate attack slot: {slot}")
            seen_slots.add(slot)
            _validate_run(
                run_dir=task_root / "attacks" / slot,
                run_record=attack,
                role="attack",
                require_scores=require_scores,
                result=result,
                expected_backend=str(manifest.get("backend") or ""),
                expected_model=str(manifest.get("model") or ""),
            )
    if manifest.get("clean_trajectory_count") not in {None, clean_count}:
        result.error(combo_root / "manifest.json", f"clean_trajectory_count mismatch: {manifest.get('clean_trajectory_count')} != {clean_count}")
    if manifest.get("attack_trajectory_count") not in {None, attack_count}:
        result.error(combo_root / "manifest.json", f"attack_trajectory_count mismatch: {manifest.get('attack_trajectory_count')} != {attack_count}")
    _validate_checksums(combo_root, manifest, result)
    if run_redaction_scan:
        scan = scan_release_tree([combo_root], exclude_relative_parts=("archives",))
        for hit in scan.hits:
            result.error(hit.path, f"redaction scan hit: {hit.kind}#{hit.fingerprint} line={hit.line}")
        if scan.skipped_files:
            result.error(combo_root, f"redaction scan skipped {scan.skipped_files} file(s)")
    return result


def _sha256_stream(handle: Any) -> str:
    digest = hashlib.sha256()
    for chunk in iter(lambda: handle.read(1024 * 1024), b""):
        digest.update(chunk)
    return digest.hexdigest()


def _archive_expected_files(combo_root: Path) -> dict[str, tuple[int, str]]:
    expected: dict[str, tuple[int, str]] = {}
    for path in sorted(combo_root.rglob("*"), key=lambda item: item.parts):
        if not path.is_file() or path.is_symlink() or _is_top_level_dir_path(path, combo_root, "archives"):
            continue
        rel = path.relative_to(combo_root).as_posix()
        expected[rel] = (path.stat().st_size, sha256_file(path))
    return expected


def _open_archive_stream(archive_path: Path, result: ValidationResult) -> tuple[Any, Any]:
    if archive_path.name.endswith(".tar.gz"):
        return tarfile.open(archive_path, "r|gz"), None
    if archive_path.name.endswith(".tar.zst"):
        try:
            process = subprocess.Popen(["zstd", "-dc", str(archive_path)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except OSError as exc:
            result.error(archive_path, f"Cannot start zstd for archive validation: {exc}")
            return None, None
        if process.stdout is None:
            result.error(archive_path, "Cannot read zstd archive stream")
            process.kill()
            process.wait()
            return None, None
        try:
            return tarfile.open(fileobj=process.stdout, mode="r|"), process
        except tarfile.TarError as exc:
            result.error(archive_path, f"Cannot open zstd tar stream: {exc}")
            process.kill()
            process.wait()
            return None, None
    result.error(archive_path, f"Unsupported archive suffix: {archive_path.name}")
    return None, None


def _validate_archive_members(combo_root: Path, archive_path: Path, combo_id: str, result: ValidationResult) -> None:
    expected = _archive_expected_files(combo_root)
    seen: dict[str, tuple[int, str]] = {}
    seen_members: set[str] = set()
    archive, process = _open_archive_stream(archive_path, result)
    if archive is None:
        return
    try:
        with archive:
            for member in archive:
                name = str(member.name or "")
                if name in seen_members:
                    result.error(archive_path, f"Duplicate archive member: {name}")
                    continue
                seen_members.add(name)
                parts = PurePosixPath(name).parts
                if not parts or name.startswith("/") or any(part in {"", ".."} for part in parts):
                    result.error(archive_path, f"Unsafe archive member path: {name!r}")
                    continue
                if parts[0] != combo_id:
                    result.error(archive_path, f"Archive member outside combo root: {name!r}")
                    continue
                rel = "/".join(parts[1:])
                if member.uid != 0 or member.gid != 0 or member.uname or member.gname:
                    result.error(archive_path, f"Archive member ownership is not normalized: {name}")
                if not rel:
                    if not member.isdir():
                        result.error(archive_path, f"Combo root archive member is not a directory: {name}")
                    continue
                if rel == "archives" or rel.startswith("archives/"):
                    result.error(archive_path, f"Generated archives directory included in archive: {name}")
                    continue
                if member.isdir():
                    continue
                if not member.isfile():
                    result.error(archive_path, f"Unsupported archive member type: {name}")
                    continue
                extracted = archive.extractfile(member)
                if extracted is None:
                    result.error(archive_path, f"Cannot read archive member: {name}")
                    continue
                actual_sha = _sha256_stream(extracted)
                actual_size = int(member.size)
                seen[rel] = (actual_size, actual_sha)
                expected_item = expected.get(rel)
                if expected_item is None:
                    result.error(archive_path, f"Unexpected archive member: {name}")
                    continue
                expected_size, expected_sha = expected_item
                if actual_size != expected_size:
                    result.error(archive_path, f"Archive member size mismatch for {name}: expected={expected_size} actual={actual_size}")
                if actual_sha != expected_sha:
                    result.error(archive_path, f"Archive member sha256 mismatch for {name}: expected={expected_sha} actual={actual_sha}")
    except (tarfile.TarError, OSError, EOFError) as exc:
        result.error(archive_path, f"Cannot validate archive members: {exc}")
    finally:
        if process is not None:
            if process.stdout is not None:
                process.stdout.close()
            stderr = process.stderr.read() if process.stderr is not None else b""
            return_code = process.wait()
            if return_code != 0:
                message = stderr.decode("utf-8", errors="replace").strip()
                result.error(archive_path, f"zstd archive decompression failed: {message or return_code}")
    missing = sorted(set(expected) - set(seen))
    for rel in missing[:20]:
        result.error(archive_path, f"Missing archive member: {combo_id}/{rel}")
    if len(missing) > 20:
        result.error(archive_path, f"{len(missing) - 20} additional archive members are missing")


def _validate_archive(root: Path, combo: dict[str, Any], combo_id: str, result: ValidationResult) -> tuple[str, Optional[Path], str, Optional[int]]:
    archive_rel = str(combo.get("archive") or "")
    archive_size = combo.get("archive_size_bytes")
    archive_sha = str(combo.get("archive_sha256") or "")
    if not archive_rel:
        if archive_size is not None or archive_sha:
            result.error(root / "manifest.json", f"Archive metadata present without archive for combo {combo_id}")
        return "", None, "", None
    expected_prefix = f"combos/{combo_id}/archives/"
    archive_name = Path(archive_rel).name
    if not archive_rel.startswith(expected_prefix) or archive_name not in {f"{combo_id}.tar.gz", f"{combo_id}.tar.zst"}:
        result.error(root / "manifest.json", f"Unexpected archive path for combo {combo_id}: {archive_rel!r}")
    archive_path = _safe_relative_path(root, archive_rel, result, label="combo archive", issue_path=root / "manifest.json")
    if archive_path is None:
        return archive_rel, None, archive_sha, None
    if not archive_path.is_file():
        result.error(archive_path, "Declared combo archive is missing")
    parsed_size = _int_metadata(archive_size, result, path=root / "manifest.json", label="archive_size_bytes")
    if archive_path.is_file() and parsed_size is not None and archive_path.stat().st_size != parsed_size:
        result.error(archive_path, f"archive size mismatch: manifest={archive_size} actual={archive_path.stat().st_size}")
    if not archive_sha:
        result.error(root / "manifest.json", f"archive_sha256 is required for combo {combo_id}")
    elif archive_path.is_file():
        actual_sha = sha256_file(archive_path)
        if actual_sha != archive_sha:
            result.error(archive_path, f"archive sha256 mismatch: manifest={archive_sha} actual={actual_sha}")
    if archive_path.is_file():
        _validate_archive_members(root / "combos" / combo_id, archive_path, combo_id, result)
    return archive_rel, archive_path, archive_sha, parsed_size


def _full_combo_refs(root: Path, result: ValidationResult, *, selected: set[str] | None = None) -> dict[str, _FullComboRef]:
    manifest = _load_json(root / "manifest.json", result)
    if manifest.get("schema_version") != FULL_RELEASE_SCHEMA_VERSION:
        result.error(root / "manifest.json", f"Unsupported full release schema {manifest.get('schema_version')!r}")
    raw_combos = manifest.get("combos")
    if not isinstance(raw_combos, list) or not raw_combos:
        result.error(root / "manifest.json", "Full release manifest must contain a nonempty combos list")
        raw_combos = []
    if manifest.get("combo_count") != len(raw_combos):
        result.error(root / "manifest.json", f"combo_count mismatch: {manifest.get('combo_count')} != {len(raw_combos)}")
    refs: dict[str, _FullComboRef] = {}
    for item in raw_combos:
        combo = _as_dict(item)
        combo_id = _safe_component(str(combo.get("combo_id") or ""), result, label="combo_id", issue_path=root / "manifest.json")
        if combo_id is None:
            continue
        if combo_id in refs:
            result.error(root / "manifest.json", f"Duplicate combo_id: {combo_id}")
            continue
        manifest_rel = str(combo.get("manifest") or "")
        expected_manifest = f"combos/{combo_id}/manifest.json"
        if manifest_rel != expected_manifest:
            result.error(root / "manifest.json", f"Combo {combo_id} manifest path must be {expected_manifest!r}, got {manifest_rel!r}")
        manifest_path = _safe_relative_path(root, manifest_rel, result, label="combo manifest", issue_path=root / "manifest.json")
        if manifest_path is None:
            continue
        if selected is not None and combo_id not in selected:
            refs[combo_id] = _FullComboRef(
                combo_id=combo_id,
                manifest_rel=manifest_rel,
                manifest_path=manifest_path,
                manifest={},
                archive_rel=str(combo.get("archive") or ""),
                archive_path=None,
                archive_sha256=str(combo.get("archive_sha256") or ""),
                archive_size_bytes=combo.get("archive_size_bytes") if isinstance(combo.get("archive_size_bytes"), int) else None,
            )
            continue
        child = _load_json(manifest_path, result)
        child_combo_id = _safe_component(str(child.get("combo_id") or ""), result, label="combo manifest combo_id", issue_path=manifest_path)
        if child.get("schema_version") != FULL_COMBO_SCHEMA_VERSION:
            result.error(manifest_path, f"Unsupported combo schema {child.get('schema_version')!r}")
        if child_combo_id and child_combo_id != combo_id:
            result.error(manifest_path, f"combo_id mismatch: root={combo_id!r} child={child_combo_id!r}")
        for count_field in ("task_count", "clean_trajectory_count", "attack_trajectory_count"):
            if combo.get(count_field) != child.get(count_field):
                result.error(
                    root / "manifest.json",
                    f"Combo {combo_id} {count_field} mismatch: root={combo.get(count_field)} child={child.get(count_field)}",
                )
        archive_rel, archive_path, archive_sha, archive_size = _validate_archive(root, combo, combo_id, result)
        refs[combo_id] = _FullComboRef(
            combo_id=combo_id,
            manifest_rel=manifest_rel,
            manifest_path=manifest_path,
            manifest=child,
            archive_rel=archive_rel,
            archive_path=archive_path,
            archive_sha256=archive_sha,
            archive_size_bytes=archive_size,
        )
    return refs


def validate_full_release(
    root: Path | str,
    *,
    combos: Sequence[str] = (),
    expected_task_count: Optional[int] = 300,
    expected_attack_runs_per_task: int = 3,
    require_scores: bool = True,
    run_redaction_scan: bool = True,
) -> ValidationResult:
    root = Path(root).expanduser()
    result = ValidationResult()
    _validate_no_symlinks(root, result)
    selected: set[str] = set()
    for combo_id in combos:
        safe_id = _safe_component(str(combo_id), result, label="requested combo_id", issue_path=root / "manifest.json")
        if safe_id:
            selected.add(safe_id)
    refs = _full_combo_refs(root, result, selected=selected or None)
    combos_root = root / "combos"
    actual_combo_dirs = {path.name for path in combos_root.iterdir() if path.is_dir()} if combos_root.is_dir() else set()
    for combo_id in sorted(actual_combo_dirs - set(refs)):
        result.error(combos_root / combo_id, "Combo directory is not listed by the full release manifest")
    if root.is_dir():
        for path in root.iterdir():
            if path.name not in {"manifest.json", "combos"}:
                result.error(path, "Unexpected file or directory at full release root")
    for combo_id, ref in refs.items():
        if selected and combo_id not in selected:
            continue
        result.merge(
            validate_combo_release(
                ref.manifest_path.parent,
                expected_task_count=expected_task_count,
                expected_attack_runs_per_task=expected_attack_runs_per_task,
                require_scores=require_scores,
                run_redaction_scan=run_redaction_scan,
            )
        )
    if selected:
        missing = sorted(selected - set(refs))
        for combo_id in missing:
            result.error(root / "manifest.json", f"Requested combo not found: {combo_id}")
    if run_redaction_scan:
        root_scan = scan_release_tree([root / "manifest.json"])
        for hit in root_scan.hits:
            result.error(hit.path, f"redaction scan hit: {hit.kind}#{hit.fingerprint} line={hit.line}")
        if root_scan.skipped_files:
            result.error(root / "manifest.json", f"redaction scan skipped {root_scan.skipped_files} root manifest file(s)")
    return result


def _read_hf_rows(data_path: Path, result: ValidationResult) -> list[dict[str, Any]]:
    if data_path.suffix == ".jsonl":
        return _read_jsonl(data_path, result)
    if data_path.suffix == ".parquet":
        try:
            import pyarrow.parquet as pq  # type: ignore
        except Exception as exc:  # pragma: no cover - optional dependency
            result.error(data_path, f"Cannot validate parquet without pyarrow: {exc}")
            return []
        table = pq.read_table(data_path)
        return table.to_pylist()
    result.error(data_path, f"Unsupported HF data file suffix: {data_path.suffix}")
    return []


def _expected_hf_rows_by_path(
    *,
    full_release_root: Path,
    ref: _FullComboRef,
    result: ValidationResult,
) -> dict[str, dict[str, Any]]:
    combo_manifest = ref.manifest
    combo_root = ref.manifest_path.parent
    task_bundles_rel = str(combo_manifest.get("task_bundles") or "task_bundles.jsonl")
    task_bundles_path = _safe_relative_path(
        combo_root,
        task_bundles_rel,
        result,
        label="task_bundles",
        issue_path=ref.manifest_path,
    )
    if task_bundles_path is None:
        return {}
    expected: dict[str, dict[str, Any]] = {}
    for task in _read_jsonl(task_bundles_path, result):
        suite = _safe_component(str(task.get("suite") or ""), result, label="suite", issue_path=task_bundles_path)
        task_id = _safe_component(str(task.get("task_id") or ""), result, label="task_id", issue_path=task_bundles_path)
        if suite is None or task_id is None:
            continue
        run_items: list[tuple[str, dict[str, Any], str, str]] = [
            ("clean", _as_dict(task.get("clean")), f"tasks/{suite}/{task_id}/clean", "")
        ]
        for attack in _as_list(task.get("attacks")):
            attack_record = _as_dict(attack)
            slot = _safe_component(
                str(attack_record.get("attack_slot") or f"run_{attack_record.get('run_number')}"),
                result,
                label="attack_slot",
                issue_path=task_bundles_path,
            )
            if slot is None:
                continue
            run_items.append(("attack", attack_record, f"tasks/{suite}/{task_id}/attacks/{slot}", slot))
        for role, run_record, run_dir_rel, attack_slot in run_items:
            run_dir = _safe_relative_path(combo_root, run_dir_rel, result, label="run directory", issue_path=task_bundles_path)
            if run_dir is None:
                continue
            trajectory_rel = str(run_record.get("trajectory") or "trajectory.json")
            trajectory_path = _safe_relative_path(
                run_dir,
                trajectory_rel,
                result,
                label="trajectory",
                issue_path=task_bundles_path,
            )
            if trajectory_path is None:
                continue
            try:
                rel = trajectory_path.relative_to(full_release_root).as_posix()
                inner_rel = trajectory_path.relative_to(combo_root).as_posix()
            except ValueError:
                result.error(trajectory_path, "Expected HF source trajectory is outside full release root")
                continue
            expected[rel] = {
                "combo_id": ref.combo_id,
                "backend": str(combo_manifest.get("backend") or ""),
                "model": str(combo_manifest.get("model") or ""),
                "suite": suite,
                "task_id": task_id,
                "role": role,
                "run_number": run_record.get("run_number") if role == "attack" else None,
                "attack_slot": attack_slot,
                "trajectory_id": str(run_record.get("trajectory_id") or ""),
                "release_id": str(combo_manifest.get("release_id") or ""),
                "score_summary": _as_dict(run_record.get("score_summary")),
                "full_artifact_inner_path": f"{ref.combo_id}/{inner_rel}",
            }
    return expected


def _archive_uri_basename(uri: str) -> str:
    parsed = urlparse(uri)
    return Path(parsed.path).name if parsed.scheme or parsed.netloc else Path(uri).name


def validate_hf_dataset(
    *,
    full_release_root: Path | str,
    hf_root: Path | str,
    combos: Sequence[str] = (),
    expected_task_count: Optional[int] = 300,
    expected_attack_runs_per_task: int = 3,
    run_redaction_scan: bool = True,
) -> ValidationResult:
    full_release_root_raw = Path(full_release_root).expanduser()
    full_release_root = full_release_root_raw.resolve()
    hf_root = Path(hf_root).expanduser()
    result = ValidationResult()
    _validate_no_symlinks(full_release_root_raw, result)
    _validate_no_symlinks(hf_root, result)
    selected: set[str] = set()
    for combo_id in combos:
        safe_id = _safe_component(str(combo_id), result, label="requested combo_id", issue_path=hf_root / "manifest.json")
        if safe_id:
            selected.add(safe_id)
    full_refs = _full_combo_refs(full_release_root, result, selected=selected or None)
    manifest = _load_json(hf_root / "manifest.json", result)
    if manifest.get("schema_version") != HF_RELEASE_SCHEMA_VERSION:
        result.error(hf_root / "manifest.json", f"Unsupported HF schema {manifest.get('schema_version')!r}")
    if manifest.get("full_release_manifest") not in {None, "manifest.json"}:
        result.error(hf_root / "manifest.json", f"Unexpected full_release_manifest: {manifest.get('full_release_manifest')!r}")
    raw_combos = manifest.get("combos")
    if not isinstance(raw_combos, list):
        result.error(hf_root / "manifest.json", "HF manifest combos must be a list")
        raw_combos = []
    if manifest.get("combo_count") != len(raw_combos):
        result.error(hf_root / "manifest.json", f"HF combo_count mismatch: {manifest.get('combo_count')} != {len(raw_combos)}")
    seen: set[str] = set()
    actual_total_rows = 0
    declared_total_rows = 0
    read_all_rows = not selected
    selected_scan_roots = [
        hf_root / "manifest.json",
        hf_root / "metadata" / "combo_manifest.json",
        hf_root / "README.md",
    ]
    for item in raw_combos:
        combo = _as_dict(item)
        combo_id = _safe_component(str(combo.get("combo_id") or ""), result, label="HF combo_id", issue_path=hf_root / "manifest.json")
        if combo_id is None:
            continue
        if combo_id in seen:
            result.error(hf_root / "manifest.json", f"Duplicate HF combo_id: {combo_id}")
            continue
        seen.add(combo_id)
        row_count = _int_metadata(combo.get("row_count"), result, path=hf_root / "manifest.json", label="HF combo row_count")
        if row_count is not None:
            declared_total_rows += row_count
        ref = full_refs.get(combo_id)
        if ref is None:
            result.error(hf_root / "manifest.json", f"HF combo does not exist in full release: {combo_id}")
        source_manifest_rel = str(combo.get("source_full_manifest") or "")
        if ref is not None and source_manifest_rel != ref.manifest_rel:
            result.error(hf_root / "manifest.json", f"HF source_full_manifest mismatch for {combo_id}: {source_manifest_rel!r} != {ref.manifest_rel!r}")
        _safe_relative_path(full_release_root, source_manifest_rel, result, label="source full manifest", issue_path=hf_root / "manifest.json")
        if selected and combo_id not in selected:
            continue
        data_rel = str(combo.get("data") or "")
        data_path = _safe_relative_path(hf_root, data_rel, result, label="HF data", issue_path=hf_root / "manifest.json")
        if data_path is None:
            continue
        if selected:
            selected_scan_roots.append(data_path)
        expected_by_path = (
            _expected_hf_rows_by_path(
                full_release_root=full_release_root,
                ref=ref,
                result=result,
            )
            if ref is not None
            else {}
        )
        rows = _read_hf_rows(data_path, result)
        if read_all_rows:
            actual_total_rows += len(rows)
        if row_count is not None and row_count != len(rows):
            result.error(data_path, f"HF combo row_count mismatch: manifest={combo.get('row_count')} actual={len(rows)}")
        clean_count = sum(1 for row in rows if row.get("role") == "clean")
        attack_count = sum(1 for row in rows if row.get("role") == "attack")
        if expected_task_count is not None and clean_count != expected_task_count:
            result.error(data_path, f"Expected {expected_task_count} clean rows, found {clean_count}")
        expected_attacks = (expected_task_count * expected_attack_runs_per_task) if expected_task_count is not None else None
        if expected_attacks is not None and attack_count != expected_attacks:
            result.error(data_path, f"Expected {expected_attacks} attack rows, found {attack_count}")
        seen_paths: set[str] = set()
        combo_uri_values = {str(row.get("full_artifact_uri") or "") for row in rows}
        if len(combo_uri_values) > 1:
            result.error(data_path, "HF rows for one combo use multiple full_artifact_uri values")
        for row in rows:
            if row.get("schema_version") != HF_RELEASE_SCHEMA_VERSION:
                result.error(data_path, f"HF row has unsupported schema {row.get('schema_version')!r}")
            rel = str(row.get("full_bundle_relative_path") or "")
            full_path = _safe_relative_path(
                full_release_root,
                rel,
                result,
                label="full_bundle_relative_path",
                issue_path=data_path,
            )
            if full_path is None:
                continue
            if rel in seen_paths:
                result.error(data_path, f"Duplicate HF full_bundle_relative_path: {rel}")
            seen_paths.add(rel)
            expected = expected_by_path.get(rel)
            if expected is None:
                result.error(data_path, f"HF row does not match a task-bundle trajectory: {rel}")
            if not full_path.is_file():
                result.error(full_path, "HF row points to missing full trajectory")
                continue
            expected_sha = str(row.get("trajectory_sha256") or "")
            actual_sha = sha256_file(full_path)
            if expected_sha != actual_sha:
                result.error(full_path, f"HF trajectory hash mismatch: row={expected_sha} actual={actual_sha}")
            if "/workspace_after/" in rel or "/api/" in rel:
                result.error(data_path, f"HF row points to non-trajectory artifact: {rel}")
            full_trajectory = _load_json(full_path, result)
            _json_equivalent(str(row.get("trajectory_json") or ""), full_trajectory, result, data_path, label="trajectory_json")
            inner_path = str(row.get("full_artifact_inner_path") or "")
            try:
                safe_relative_path(inner_path)
            except ScenarioValidationError as exc:
                result.error(data_path, f"Unsafe full_artifact_inner_path: {inner_path!r} ({exc})")
            if expected is not None:
                for key in ("combo_id", "backend", "model", "suite", "task_id", "role", "attack_slot", "trajectory_id", "release_id"):
                    if str(row.get(key) or "") != str(expected.get(key) or ""):
                        result.error(data_path, f"HF row {key} mismatch for {rel}")
                if row.get("run_number") != expected.get("run_number"):
                    result.error(data_path, f"HF row run_number mismatch for {rel}")
                if inner_path != expected.get("full_artifact_inner_path"):
                    result.error(data_path, f"HF row full_artifact_inner_path mismatch for {rel}")
                _json_equivalent(
                    str(row.get("score_json") or ""),
                    _as_dict(expected.get("score_summary")),
                    result,
                    data_path,
                    label="score_json",
                )
            uri = str(row.get("full_artifact_uri") or "")
            if ref is not None and not ref.archive_rel and uri:
                result.error(data_path, f"HF row has full_artifact_uri but full combo has no archive: {rel}")
            if ref is not None and ref.archive_rel and uri:
                archive_name = Path(ref.archive_rel).name
                if _archive_uri_basename(uri) != archive_name:
                    result.error(data_path, f"HF row full_artifact_uri basename mismatch for {rel}")
        missing_rows = sorted(set(expected_by_path) - seen_paths)
        for rel in missing_rows[:20]:
            result.error(data_path, f"Missing HF row for full trajectory: {rel}")
        if len(missing_rows) > 20:
            result.error(data_path, f"{len(missing_rows) - 20} additional HF rows are missing")
    if selected:
        for combo_id in sorted(selected - seen):
            result.error(hf_root / "manifest.json", f"Requested HF combo not found: {combo_id}")
    if manifest.get("row_count") != declared_total_rows:
        result.error(hf_root / "manifest.json", f"HF declared row_count mismatch: manifest={manifest.get('row_count')} declared_sum={declared_total_rows}")
    if read_all_rows and manifest.get("row_count") != actual_total_rows:
        result.error(hf_root / "manifest.json", f"HF total row_count mismatch: manifest={manifest.get('row_count')} actual={actual_total_rows}")
    if run_redaction_scan:
        scan = scan_release_tree(selected_scan_roots if selected else [hf_root])
        for hit in scan.hits:
            result.error(hit.path, f"redaction scan hit: {hit.kind}#{hit.fingerprint} line={hit.line}")
        if scan.skipped_files:
            result.error(hf_root, f"redaction scan skipped {scan.skipped_files} file(s)")
    return result


def _parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate ActBench public release bundles")
    parser.add_argument("--full-release-root", required=True)
    parser.add_argument("--hf-root", default=None)
    parser.add_argument("--combo", action="append", default=[])
    parser.add_argument("--expected-task-count", type=int, default=300)
    parser.add_argument("--expected-attack-runs-per-task", type=int, default=3)
    parser.add_argument("--allow-missing-scores", action="store_true")
    parser.add_argument("--skip-redaction-scan", action="store_true")
    parser.add_argument("--json-output", default=None)
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _parse_args(argv)
    result = validate_full_release(
        args.full_release_root,
        combos=tuple(args.combo),
        expected_task_count=args.expected_task_count,
        expected_attack_runs_per_task=args.expected_attack_runs_per_task,
        require_scores=not args.allow_missing_scores,
        run_redaction_scan=not args.skip_redaction_scan,
    )
    if args.hf_root:
        result.merge(
            validate_hf_dataset(
                full_release_root=args.full_release_root,
                hf_root=args.hf_root,
                combos=tuple(args.combo),
                expected_task_count=args.expected_task_count,
                expected_attack_runs_per_task=args.expected_attack_runs_per_task,
                run_redaction_scan=not args.skip_redaction_scan,
            )
        )
    summary = result.summary()
    if args.json_output:
        Path(args.json_output).write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0 if result.ok else 1
