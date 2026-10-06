"""Build canonical public ActBench full release bundles from raw-by-task packs."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import tarfile
import time
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, Optional, Sequence

from lib_training_artifacts import safe_artifact_name

from benchmark.raw_by_task import (
    DEFAULT_RAW_BY_TASK_ROOT,
    RAW_ROLE_ATTACKED,
    RAW_ROLE_BENIGN,
    TASK_VERSION_MISMATCH_REASON,
    RawByTaskDataset,
    RawByTaskCollection,
    collect_raw_by_task_trajectories,
    resolve_raw_by_task_datasets,
)
from benchmark.release_redaction import (
    copy_redacted_file,
    copy_redacted_tree,
    raise_on_redaction_hits,
    redact_json,
    scan_release_tree,
    validate_redacted_checker_payload,
)
from benchmark.release_scores import (
    AttackScoreQuery,
    AttackUtilityScoreQuery,
    CleanScoreQuery,
    MissingReleaseScoreError,
    ReleaseScoreError,
    ScoreIndex,
    load_score_index,
    public_attack_score,
    public_utility_score as public_utility_score_payload,
    score_bool,
    sha256_file,
)
from benchmark.trajectories import SUPPORTED_TRAJECTORY_SCHEMA_VERSIONS

FULL_RELEASE_SCHEMA_VERSION = "actbench.release.full.v1"
FULL_COMBO_SCHEMA_VERSION = "actbench.release.full_combo.v1"
TASK_BUNDLE_SCHEMA_VERSION = "actbench.release.task_bundle.v1"
ATTACK_SCORES_SCHEMA_VERSION = "actbench.release.attack_scores.v1"
UTILITY_SCORES_SCHEMA_VERSION = "actbench.release.utility_scores.v1"
AGGREGATE_METRICS_SCHEMA_VERSION = "actbench.release.aggregate_metrics.v1"

_SUITE_ID_RE = re.compile(r"^B(\d+)$")
_TASK_ID_RE = re.compile(r"^task_B(\d+)_T(\d+)$")
_NATURAL_PART_RE = re.compile(r"(\d+)")


class ReleaseBundleError(ValueError):
    """Raised when a full public release bundle cannot be built."""


@dataclass(frozen=True)
class ReleaseBuildOptions:
    raw_by_task_root: Path | str = DEFAULT_RAW_BY_TASK_ROOT
    output_root: Path | str = Path("release/actbench-public")
    release_id: str = "actbench-public"
    datasets: Sequence[str] = field(default_factory=tuple)
    ags_score_paths: Sequence[Path | str] = field(default_factory=tuple)
    utility_score_paths: Sequence[Path | str] = field(default_factory=tuple)
    expected_task_count: Optional[int] = 300
    expected_attack_runs_per_task: int = 3
    require_scores: bool = True
    overwrite: bool = False
    redact: bool = True
    run_redaction_scan: bool = True
    archive: bool = False
    compression: str = "zstd"


@dataclass(frozen=True)
class ComboBuildResult:
    combo_id: str
    combo_root: Path
    manifest_path: Path
    task_count: int
    clean_count: int
    attack_count: int
    archive_path: Optional[Path] = None
    archive_size_bytes: Optional[int] = None
    archive_sha256: str = ""


@dataclass(frozen=True)
class ReleaseBuildResult:
    release_root: Path
    manifest_path: Path
    combos: tuple[ComboBuildResult, ...]


@dataclass(frozen=True)
class _RunBundleResult:
    manifest: dict[str, Any]
    public_score: Optional[dict[str, Any]]
    public_utility_score: Optional[dict[str, Any]] = None


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _natural_key(value: str) -> tuple[Any, ...]:
    parts: list[tuple[int, Any]] = []
    for part in _NATURAL_PART_RE.split(value):
        if part.isdigit():
            parts.append((0, int(part)))
        elif part:
            parts.append((1, part))
    return tuple(parts)


def _suite_sort_key(suite: str) -> tuple[Any, ...]:
    match = _SUITE_ID_RE.fullmatch(suite)
    if match:
        return (0, int(match.group(1)))
    return (1, *_natural_key(suite))


def _task_sort_key(task_id: str) -> tuple[Any, ...]:
    match = _TASK_ID_RE.fullmatch(task_id)
    if match:
        return (0, int(match.group(1)), int(match.group(2)))
    return (1, *_natural_key(task_id))


def _suite_task_sort_key(item: tuple[str, str]) -> tuple[Any, ...]:
    suite, task_id = item
    return (*_suite_sort_key(suite), *_task_sort_key(task_id))


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ReleaseBundleError(f"JSON payload must be an object: {path}")
    return payload


def _write_json(
    path: Path,
    payload: Any,
    *,
    redact: bool = False,
    validate_embedded_checker: bool = False,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if redact:
        redacted_payload = redact_json(payload)
        if validate_embedded_checker:
            errors = validate_redacted_checker_payload(payload, redacted_payload, label=str(path))
            if errors:
                raise ReleaseBundleError("; ".join(errors))
        payload = redacted_payload
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _write_jsonl(path: Path, rows: Sequence[dict[str, Any]], *, redact: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            payload = redact_json(row) if redact else row
            handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True))
            handle.write("\n")


def _explicit_backend_model(trajectory: dict[str, Any]) -> tuple[str, str]:
    backend = _as_dict(trajectory.get("backend"))
    execution = _as_dict(trajectory.get("execution"))
    scoring_inputs = _as_dict(trajectory.get("scoring_inputs"))
    return (
        str(backend.get("name") or execution.get("backend") or scoring_inputs.get("backend_name") or ""),
        str(backend.get("model") or execution.get("model") or scoring_inputs.get("target_model") or ""),
    )


def _valid_identity_part(value: str) -> bool:
    return bool(value) and value.lower() not in {"mixed", "unknown", "unknown_backend", "unknown_model"}


def _backend_identity_key(value: str) -> str:
    return str(value or "").strip().lower()


def _model_identity_key(value: str) -> str:
    text = str(value or "").strip()
    if "/" not in text:
        return text.casefold()
    provider, model = text.split("/", 1)
    return f"{provider.casefold()}/{model.casefold()}"


def _dataset_trajectory_paths(dataset: RawByTaskDataset) -> list[Path]:
    paths: list[Path] = []
    for pattern in ("B*/task_*/run_*/trajectory.json", "_baselines/B*/task_*/baseline/trajectory.json"):
        paths.extend(sorted(dataset.path.glob(pattern)))
    return paths


def _dataset_identity(dataset: RawByTaskDataset) -> tuple[str, str]:
    backend = dataset.backend
    model = dataset.target_model
    if backend.lower() == "mixed" or model.lower() == "mixed":
        raise ReleaseBundleError(f"raw_by_task dataset has mixed backend/model identity: {dataset.path}")
    for trajectory_path in _dataset_trajectory_paths(dataset):
        try:
            trajectory = _load_json(trajectory_path)
        except (OSError, json.JSONDecodeError, ReleaseBundleError):
            continue
        explicit_backend, explicit_model = _explicit_backend_model(trajectory)
        if backend and explicit_backend and _backend_identity_key(explicit_backend) != _backend_identity_key(backend):
            raise ReleaseBundleError(
                f"Trajectory backend {explicit_backend!r} does not match dataset backend {backend!r}: {trajectory_path}"
            )
        if model and explicit_model and _model_identity_key(explicit_model) != _model_identity_key(model):
            raise ReleaseBundleError(
                f"Trajectory model {explicit_model!r} does not match dataset model {model!r}: {trajectory_path}"
            )
        backend = backend or explicit_backend
        model = model or explicit_model
    if not _valid_identity_part(backend) or not _valid_identity_part(model):
        raise ReleaseBundleError(f"Cannot determine single backend/model identity for raw_by_task dataset: {dataset.path}")
    return backend, model


def _combo_id_for_identity(backend: str, model: str, dataset_name: str = "") -> str:
    backend_slug = safe_artifact_name(backend or "unknown_backend")
    model_slug = safe_artifact_name(model or dataset_name or "unknown_model")
    return f"{backend_slug}__{model_slug}"


def _combo_id(dataset: RawByTaskDataset) -> str:
    backend, model = _dataset_identity(dataset)
    return _combo_id_for_identity(backend, model, dataset.name)


def _safe_component(value: str, *, label: str) -> str:
    text = str(value or "")
    path = Path(text)
    if not text or text in {".", ".."} or path.is_absolute() or len(path.parts) != 1 or safe_artifact_name(text) != text:
        raise ReleaseBundleError(f"Unsafe {label} path component: {value!r}")
    return text


def _run_number_from_attack_path(path: Path) -> int:
    try:
        return int(path.parent.name.removeprefix("run_"))
    except ValueError as exc:
        raise ReleaseBundleError(f"Unexpected raw_by_task attack run path: {path}") from exc


def _suite_task_from_attack_path(path: Path) -> tuple[str, str]:
    try:
        return path.parent.parent.parent.name, path.parent.parent.name
    except IndexError as exc:
        raise ReleaseBundleError(f"Unexpected raw_by_task attack trajectory path: {path}") from exc


def _suite_task_from_clean_path(path: Path) -> tuple[str, str]:
    try:
        return path.parents[2].name, path.parents[1].name
    except IndexError as exc:
        raise ReleaseBundleError(f"Unexpected raw_by_task clean trajectory path: {path}") from exc


def _canonical_slot_id(trajectory: dict[str, Any]) -> str:
    canonical = _as_dict(trajectory.get("canonical"))
    artifacts = _as_dict(trajectory.get("artifacts"))
    return str(canonical.get("slot_id") or artifacts.get("canonical_slot_id") or "")


def _backend_model(dataset: RawByTaskDataset, trajectory: dict[str, Any]) -> tuple[str, str]:
    backend, model = _explicit_backend_model(trajectory)
    return backend or dataset.backend, model or dataset.target_model


def _trajectory_id(trajectory: dict[str, Any]) -> str:
    return str(trajectory.get("trajectory_id") or _as_dict(trajectory.get("run")).get("training_artifact_key") or "")


def _copy_json_payload(payload: dict[str, Any], destination: Path, *, redact: bool) -> None:
    if redact:
        redacted_payload = redact_json(payload)
        errors = validate_redacted_checker_payload(payload, redacted_payload, label=str(destination))
        if errors:
            raise ReleaseBundleError("; ".join(errors))
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(redacted_payload, indent=2, ensure_ascii=False), encoding="utf-8")
    else:
        _write_json(destination, payload)


def _copy_optional_file(source: Path, destination: Path, *, redact: bool, backend: str = "") -> Optional[str]:
    if source.is_symlink():
        copy_redacted_file(source, destination, backend=backend)
        return str(destination.name)
    if not source.is_file():
        return None
    if redact:
        copy_redacted_file(source, destination, backend=backend)
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    return str(destination.name)


def _copy_tree_no_redaction(source: Path, destination: Path, *, backend: str = "") -> None:
    if destination.exists():
        if destination.is_dir():
            shutil.rmtree(destination)
        else:
            destination.unlink()
    if source.is_symlink():
        copy_redacted_tree(source, destination, backend=backend)
        return
    destination.mkdir(parents=True, exist_ok=True)
    for item in sorted(source.rglob("*"), key=lambda path: path.parts):
        rel = item.relative_to(source)
        target = destination / rel
        if item.is_symlink():
            copy_redacted_file(item, target, backend=backend)
        elif item.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        elif item.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            if item.name.lower() == "history.db":
                copy_redacted_file(item, target, backend=backend)
            else:
                shutil.copy2(item, target)


def _copy_optional_tree(source: Path, destination: Path, *, redact: bool, backend: str = "") -> Optional[str]:
    if source.is_symlink():
        copy_redacted_tree(source, destination, backend=backend)
        return str(destination.name)
    if not source.is_dir():
        return None
    if redact:
        copy_redacted_tree(source, destination, backend=backend)
    else:
        _copy_tree_no_redaction(source, destination, backend=backend)
    return str(destination.name)


def _copy_common_sidecars(source_run_dir: Path, destination: Path, *, redact: bool, backend: str = "") -> dict[str, Any]:
    artifacts: dict[str, Any] = {}
    workspace_ref = _copy_optional_tree(
        source_run_dir / "workspace_after",
        destination / "workspace_after",
        redact=redact,
        backend=backend,
    )
    artifacts["workspace_after"] = workspace_ref

    api_refs: dict[str, str] = {}
    api_ref = _copy_optional_tree(source_run_dir / "api", destination / "api", redact=redact, backend=backend)
    if api_ref:
        if (destination / "api" / "audit.json").is_file():
            api_refs["audit"] = "api/audit.json"
        if (destination / "api" / "endpoints.json").is_file():
            api_refs["endpoints"] = "api/endpoints.json"
        if (destination / "api" / "fixture_overrides.json").is_file():
            api_refs["fixture_overrides"] = "api/fixture_overrides.json"
        if (destination / "api" / "fixtures").is_dir():
            api_refs["fixtures"] = "api/fixtures"
        if (destination / "api" / "logs").is_dir():
            api_refs["logs"] = "api/logs"
    artifacts["api"] = api_refs
    return artifacts


def _score_summary(score: Optional[dict[str, Any]], *, role: str) -> dict[str, Any]:
    if not score:
        return {"available": False}
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


def _copy_clean_run(
    *,
    dataset: RawByTaskDataset,
    score_index: ScoreIndex,
    trajectory_path: Path,
    destination: Path,
    suite: str,
    task_id: str,
    options: ReleaseBuildOptions,
) -> _RunBundleResult:
    trajectory = _load_json(trajectory_path)
    schema_version = trajectory.get("schema_version")
    if schema_version not in SUPPORTED_TRAJECTORY_SCHEMA_VERSIONS:
        raise ReleaseBundleError(f"Unsupported clean trajectory schema {schema_version!r}: {trajectory_path}")
    source_sha = sha256_file(trajectory_path)
    backend, model = _backend_model(dataset, trajectory)
    public_score: Optional[dict[str, Any]] = None
    if options.require_scores or score_index.utility_rows:
        try:
            row = score_index.find_clean(
                CleanScoreQuery(
                    backend=backend,
                    model=model,
                    suite=suite,
                    task_id=task_id,
                    trajectory_id=_trajectory_id(trajectory),
                    trajectory_path=trajectory_path,
                    trajectory_sha256=source_sha,
                )
            )
            public_score = public_utility_score_payload(row)
        except MissingReleaseScoreError:
            if options.require_scores:
                raise
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True, exist_ok=True)
    _copy_json_payload(trajectory, destination / "trajectory.json", redact=options.redact)
    _write_json(
        destination / "scoring_input.json",
        _as_dict(trajectory.get("scoring_inputs")),
        redact=options.redact,
        validate_embedded_checker=True,
    )
    _write_json(destination / "score.json", public_score or {"available": False}, redact=options.redact)
    artifacts = _copy_common_sidecars(trajectory_path.parent, destination, redact=options.redact, backend=backend)
    manifest = {
        "role": "clean",
        "trajectory": "trajectory.json",
        "trajectory_id": _trajectory_id(trajectory),
        "trajectory_sha256": sha256_file(destination / "trajectory.json"),
        "source_trajectory_sha256": source_sha,
        "score": "score.json",
        "score_summary": _score_summary(public_score, role="clean"),
        "artifacts": artifacts,
    }
    return _RunBundleResult(manifest=manifest, public_score=public_score)


def _copy_attack_run(
    *,
    dataset: RawByTaskDataset,
    score_index: ScoreIndex,
    trajectory_path: Path,
    destination: Path,
    suite: str,
    task_id: str,
    run_number: int,
    options: ReleaseBuildOptions,
) -> _RunBundleResult:
    trajectory = _load_json(trajectory_path)
    schema_version = trajectory.get("schema_version")
    if schema_version not in SUPPORTED_TRAJECTORY_SCHEMA_VERSIONS:
        raise ReleaseBundleError(f"Unsupported attack trajectory schema {schema_version!r}: {trajectory_path}")
    source_sha = sha256_file(trajectory_path)
    backend, model = _backend_model(dataset, trajectory)
    public_score: Optional[dict[str, Any]] = None
    public_utility_score: Optional[dict[str, Any]] = None
    if options.require_scores or score_index.attack_rows:
        try:
            row = score_index.find_attack(
                AttackScoreQuery(
                    backend=backend,
                    model=model,
                    suite=suite,
                    task_id=task_id,
                    run_number=run_number,
                    canonical_slot_id=_canonical_slot_id(trajectory),
                    trajectory_id=_trajectory_id(trajectory),
                    trajectory_path=trajectory_path,
                    trajectory_sha256=source_sha,
                )
            )
            public_score = public_attack_score(row)
        except MissingReleaseScoreError:
            if options.require_scores:
                raise
    if score_index.has_attack_utility_rows:
        try:
            utility_row = score_index.find_attack_utility(
                AttackUtilityScoreQuery(
                    backend=backend,
                    model=model,
                    suite=suite,
                    task_id=task_id,
                    run_number=run_number,
                    trajectory_id=_trajectory_id(trajectory),
                    trajectory_path=trajectory_path,
                    trajectory_sha256=source_sha,
                )
            )
            public_utility_score = public_utility_score_payload(utility_row)
        except MissingReleaseScoreError:
            if options.require_scores:
                raise
    if public_score is not None and public_utility_score is not None:
        public_score = {**public_score, "utility_attack": public_utility_score}
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True, exist_ok=True)
    _copy_json_payload(trajectory, destination / "trajectory.json", redact=options.redact)
    _write_json(
        destination / "scoring_input.json",
        _as_dict(trajectory.get("scoring_inputs")),
        redact=options.redact,
        validate_embedded_checker=True,
    )
    _write_json(destination / "score.json", public_score or {"available": False}, redact=options.redact)
    artifacts = _copy_common_sidecars(trajectory_path.parent, destination, redact=options.redact, backend=backend)
    manifest = {
        "role": "attack",
        "attack_slot": f"run_{run_number}",
        "run_number": run_number,
        "trajectory": "trajectory.json",
        "trajectory_id": _trajectory_id(trajectory),
        "trajectory_sha256": sha256_file(destination / "trajectory.json"),
        "source_trajectory_sha256": source_sha,
        "score": "score.json",
        "score_summary": _score_summary(public_score, role="attack"),
        "artifacts": artifacts,
    }
    return _RunBundleResult(
        manifest=manifest,
        public_score=public_score,
        public_utility_score=public_utility_score,
    )


def _aggregate_metrics(task_records: Sequence[dict[str, Any]]) -> dict[str, Any]:
    attack_rows: list[dict[str, Any]] = []
    clean_rows: list[dict[str, Any]] = []
    for task in task_records:
        clean_score = _as_dict(_as_dict(task.get("clean")).get("score_summary"))
        if clean_score.get("available"):
            clean_rows.append(clean_score)
        for attack in _as_list(task.get("attacks")):
            attack_score = _as_dict(_as_dict(attack).get("score_summary"))
            if attack_score.get("available"):
                attack_rows.append({**attack_score, "task_id": task.get("task_id"), "run_number": attack.get("run_number")})

    non_error_attacks = [row for row in attack_rows if not score_bool(row, "evaluation_error", default=False)]
    scored_attacks = [
        row for row in non_error_attacks if row.get("ags") is not None or row.get("attack_success") is not None
    ]
    ags_values = [
        float(row["ags"] if row.get("ags") is not None else row["attack_success"])
        for row in scored_attacks
    ]
    attack_success_values = [float(row["attack_success"]) for row in non_error_attacks if row.get("attack_success") is not None]
    # Legacy aliases are validated when they are present, but are never used
    # to derive the official ASR.  Current releases use the explicit binary
    # dual-evidence field only.
    for row in scored_attacks:
        for legacy_key in ("attack_pass", "pass", "is_success"):
            if legacy_key in row and row.get(legacy_key) is not None:
                score_bool(row, legacy_key)

    def _explicit_binary(row: dict[str, Any], key: str) -> Optional[float]:
        if key not in row or row.get(key) is None:
            return None
        value = row.get(key)
        if isinstance(value, bool):
            return 1.0 if value else 0.0
        if isinstance(value, (int, float)) and not isinstance(value, bool) and value in (0, 1):
            return float(value)
        raise ReleaseScoreError(f"{key} must be an explicit 0/1 value, got {value!r}")

    binary_rows: list[dict[str, Any]] = []
    for row in scored_attacks:
        binary = _explicit_binary(row, "attack_success_binary")
        if binary is not None and row.get("binary_evidence_status") != "unscorable":
            binary_rows.append({**row, "_binary": binary})
    binary_success_count = sum(1 for row in binary_rows if row["_binary"] == 1.0)
    binary_valid_count = len(binary_rows)
    asr_binary = binary_success_count / binary_valid_count if binary_valid_count else None
    valid_attack_count = len(scored_attacks)
    by_task: dict[str, list[dict[str, Any]]] = {}
    for row in binary_rows:
        by_task.setdefault(str(row.get("task_id")), []).append(row)
    pass_at: dict[str, Any] = {}
    for rows in by_task.values():
        rows.sort(key=lambda item: int(item.get("run_number") or 0))
    for k in (1, 2, 3):
        eligible = [rows for rows in by_task.values() if len(rows) >= k]
        passed = sum(1 for rows in eligible if any(row["_binary"] == 1.0 for row in rows[:k]))
        pass_at[f"k{k}"] = {
            "tasks": passed,
            "eligible_tasks": len(eligible),
            "rate": passed / len(eligible) if eligible else None,
        }

    valid_clean = [row for row in clean_rows if not score_bool(row, "evaluation_error", default=False) and row.get("ugs") is not None]
    ugs_values = [float(row["ugs"]) for row in valid_clean]
    for row in valid_clean:
        if "task_pass" in row and row.get("task_pass") is not None:
            score_bool(row, "task_pass")

    return {
        "schema_version": AGGREGATE_METRICS_SCHEMA_VERSION,
        "task_count": len(task_records),
        "clean_trajectory_count": len(clean_rows),
        "attack_trajectory_count": len(attack_rows),
        "attack": {
            "valid_scores": valid_attack_count,
            "evaluation_errors": len(attack_rows) - valid_attack_count,
            "mean_ags": sum(ags_values) / len(ags_values) if ags_values else None,
            "mean_attack_success": sum(attack_success_values) / len(attack_success_values) if attack_success_values else None,
            "attack_success_count": binary_success_count,
            "binary_success_count": binary_success_count,
            "binary_valid_scores": binary_valid_count,
            "asr_binary": asr_binary,
            "asr": asr_binary,
            "pass@k": pass_at,
            "pass@k1": pass_at["k1"]["rate"],
            "pass@k2": pass_at["k2"]["rate"],
            "pass@k3": pass_at["k3"]["rate"],
        },
        "utility": {
            "valid_scores": len(valid_clean),
            "evaluation_errors": len(clean_rows) - len(valid_clean),
            "mean_ugs": sum(ugs_values) / len(ugs_values) if ugs_values else 0.0,
        },
        "utility_attack": _aggregate_attack_utility(attack_rows),
    }


def _aggregate_attack_utility(attack_rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate UGS values attached to attacked attempts, if supplied."""

    rows: list[float] = []
    evaluation_errors = 0
    for row in attack_rows:
        if row.get("ugs_attack_evaluation_error"):
            evaluation_errors += 1
            continue
        value = row.get("ugs_attack")
        if value is None:
            continue
        try:
            rows.append(float(value))
        except (TypeError, ValueError):
            evaluation_errors += 1
    return {
        "valid_scores": len(rows),
        "evaluation_errors": evaluation_errors,
        "mean_ugs": sum(rows) / len(rows) if rows else None,
    }


def _is_top_level_dir_path(path: Path, root: Path, dirname: str) -> bool:
    try:
        rel = path.relative_to(root)
    except ValueError:
        return False
    return bool(rel.parts) and rel.parts[0] == dirname


def _generate_checksums(combo_root: Path) -> dict[str, Any]:
    checksum_dir = combo_root / "checksums"
    checksum_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    for path in sorted(combo_root.rglob("*"), key=lambda item: item.parts):
        if (
            path.is_symlink()
            or not path.is_file()
            or _is_top_level_dir_path(path, combo_root, "checksums")
            or _is_top_level_dir_path(path, combo_root, "archives")
            or path == combo_root / "manifest.json"
        ):
            continue
        rel = path.relative_to(combo_root).as_posix()
        stat = path.stat()
        rows.append({"path": rel, "size_bytes": stat.st_size, "sha256": sha256_file(path)})
    _write_jsonl(checksum_dir / "files.jsonl", rows)
    with (checksum_dir / "sha256sums.txt").open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(f"{row['sha256']}  {row['path']}\n")
    return {"file_count": len(rows), "files": "checksums/files.jsonl", "sha256sums": "checksums/sha256sums.txt"}


def _archive_filter(info: tarfile.TarInfo) -> tarfile.TarInfo | None:
    parts = PurePosixPath(info.name).parts
    if len(parts) >= 2 and parts[1] == "archives":
        return None
    if info.issym() or info.islnk():
        raise ReleaseBundleError(f"Refusing to archive symlink member: {info.name}")
    info.uid = 0
    info.gid = 0
    info.uname = ""
    info.gname = ""
    return info


def _create_archive(combo_root: Path, *, compression: str) -> Path:
    archives_dir = combo_root / "archives"
    archives_dir.mkdir(parents=True, exist_ok=True)
    if compression == "gzip":
        archive_path = archives_dir / f"{combo_root.name}.tar.gz"
        try:
            with tarfile.open(archive_path, "w:gz") as archive:
                archive.add(combo_root, arcname=combo_root.name, filter=_archive_filter)
        except Exception:
            archive_path.unlink(missing_ok=True)
            raise
        return archive_path
    if compression == "zstd":
        archive_path = archives_dir / f"{combo_root.name}.tar.zst"
        try:
            process = subprocess.Popen(
                ["zstd", "-q", "-T0", "-f", "-o", str(archive_path), "-"],
                stdin=subprocess.PIPE,
            )
        except OSError as exc:
            raise ReleaseBundleError(f"Could not start zstd archive compression: {exc}") from exc
        try:
            if process.stdin is None:
                raise ReleaseBundleError("Could not open zstd stdin")
            with process.stdin:
                with tarfile.open(fileobj=process.stdin, mode="w|") as archive:
                    archive.add(combo_root, arcname=combo_root.name, filter=_archive_filter)
            return_code = process.wait()
            if return_code != 0:
                raise ReleaseBundleError(f"zstd archive compression failed with exit code {return_code}")
        except Exception:
            if process.poll() is None:
                process.kill()
            process.wait()
            archive_path.unlink(missing_ok=True)
            raise
        return archive_path
    raise ReleaseBundleError(f"Unsupported archive compression: {compression!r}")


def _expected_run_numbers(count: int) -> list[int]:
    return list(range(1, count + 1))


def _validate_expected_counts(
    *,
    options: ReleaseBuildOptions,
    task_records: Sequence[dict[str, Any]],
) -> None:
    if options.expected_task_count is not None and len(task_records) != options.expected_task_count:
        raise ReleaseBundleError(
            f"Expected {options.expected_task_count} task bundles, found {len(task_records)}"
        )
    for record in task_records:
        attacks = _as_list(record.get("attacks"))
        if len(attacks) != options.expected_attack_runs_per_task:
            raise ReleaseBundleError(
                f"Task {record.get('task_id')} expected {options.expected_attack_runs_per_task} attacks, found {len(attacks)}"
            )
        expected_runs = _expected_run_numbers(options.expected_attack_runs_per_task)
        actual_runs = sorted(int(_as_dict(attack).get("run_number") or 0) for attack in attacks)
        if actual_runs != expected_runs:
            raise ReleaseBundleError(
                f"Task {record.get('task_id')} expected attack run numbers {expected_runs}, found {actual_runs}"
            )
        if not _as_dict(record.get("clean")):
            raise ReleaseBundleError(f"Task {record.get('task_id')} is missing clean trajectory")


def _reinclude_score_aligned_clean_exclusions(
    *,
    dataset: RawByTaskDataset,
    collection: RawByTaskCollection,
    score_index: ScoreIndex,
) -> tuple[RawByTaskCollection, list[dict[str, Any]]]:
    """Reinclude version-mismatched clean runs only with an exact score join.

    A small set of B8/B13 baselines was rerun after the task registry changed.
    The raw pack therefore records ``task_version_mismatch`` even though the
    current Luna score artifact points to that exact replacement trajectory.
    Dropping those rows would silently turn a 300-task combo into 281 tasks;
    accepting every mismatch would be unsafe.  This gate admits only rows for
    which backend/model, suite/task, and trajectory_id resolve uniquely in the
    current score index, and records the decision in the combo manifest.
    """

    selected = list(collection.trajectory_paths)
    reincluded: list[dict[str, Any]] = []
    for excluded in collection.excluded:
        if str(excluded.get("reason") or "") != TASK_VERSION_MISMATCH_REASON:
            continue
        path = Path(str(excluded.get("path") or ""))
        if not path.is_file():
            continue
        try:
            suite, task_id = _suite_task_from_clean_path(path)
            trajectory = _load_json(path)
            source_sha = sha256_file(path)
            backend, model = _backend_model(dataset, trajectory)
            row = score_index.find_clean(
                CleanScoreQuery(
                    backend=backend,
                    model=model,
                    suite=suite,
                    task_id=task_id,
                    trajectory_id=_trajectory_id(trajectory),
                    trajectory_path=path,
                    trajectory_sha256=source_sha,
                )
            )
        except (OSError, json.JSONDecodeError, ReleaseScoreError):
            continue
        selected.append(path)
        reincluded.append(
            {
                "suite": suite,
                "task_id": task_id,
                "path": str(path),
                "trajectory_id": _trajectory_id(trajectory),
                "source_trajectory_sha256": source_sha,
                "score_file": str(row.get("_score_file") or ""),
                "score_trajectory_id": str(row.get("trajectory_id") or ""),
                "reason": TASK_VERSION_MISMATCH_REASON,
                "policy": "exact_score_aligned_reinclude",
            }
        )
    if not reincluded:
        return collection, reincluded
    return (
        RawByTaskCollection(
            trajectory_paths=selected,
            excluded=collection.excluded,
            source=collection.source,
            semantic_remaps=collection.semantic_remaps,
        ),
        reincluded,
    )


def build_combo_bundle(
    dataset: RawByTaskDataset,
    *,
    score_index: ScoreIndex,
    output_root: Path,
    options: ReleaseBuildOptions,
) -> ComboBuildResult:
    combo_id = _safe_component(_combo_id(dataset), label="combo_id")
    combo_backend, combo_model = _dataset_identity(dataset)
    combo_root = output_root / "combos" / combo_id
    if combo_root.exists():
        if not options.overwrite:
            raise ReleaseBundleError(f"Release combo already exists: {combo_root}")
        shutil.rmtree(combo_root)
    combo_root.mkdir(parents=True, exist_ok=True)

    attack_collection = collect_raw_by_task_trajectories([dataset], role=RAW_ROLE_ATTACKED)
    clean_collection = collect_raw_by_task_trajectories([dataset], role=RAW_ROLE_BENIGN)
    clean_collection, clean_reincluded = _reinclude_score_aligned_clean_exclusions(
        dataset=dataset,
        collection=clean_collection,
        score_index=score_index,
    )

    attacks_by_task: dict[tuple[str, str], dict[int, Path]] = {}
    for path in attack_collection.trajectory_paths:
        suite, task_id = _suite_task_from_attack_path(path)
        suite = _safe_component(suite, label="suite")
        task_id = _safe_component(task_id, label="task_id")
        run_number = _run_number_from_attack_path(path)
        attacks_by_task.setdefault((suite, task_id), {})[run_number] = path

    clean_by_task: dict[tuple[str, str], Path] = {}
    for path in clean_collection.trajectory_paths:
        suite, task_id = _suite_task_from_clean_path(path)
        suite = _safe_component(suite, label="suite")
        task_id = _safe_component(task_id, label="task_id")
        if (suite, task_id) in clean_by_task:
            raise ReleaseBundleError(f"Duplicate clean baseline for {suite}/{task_id}")
        clean_by_task[(suite, task_id)] = path

    task_keys = sorted(set(attacks_by_task) | set(clean_by_task), key=_suite_task_sort_key)
    task_records: list[dict[str, Any]] = []
    attack_score_rows: list[dict[str, Any]] = []
    utility_score_rows: list[dict[str, Any]] = []

    for suite, task_id in task_keys:
        if (suite, task_id) not in clean_by_task:
            raise ReleaseBundleError(f"Missing clean baseline for {suite}/{task_id}")
        run_map = attacks_by_task.get((suite, task_id), {})
        expected_runs = _expected_run_numbers(options.expected_attack_runs_per_task)
        actual_runs = sorted(run_map)
        if actual_runs != expected_runs:
            raise ReleaseBundleError(f"Task {task_id} expected attack run numbers {expected_runs}, found {actual_runs}")
        task_root = combo_root / "tasks" / suite / task_id
        clean_result = _copy_clean_run(
            dataset=dataset,
            score_index=score_index,
            trajectory_path=clean_by_task[(suite, task_id)],
            destination=task_root / "clean",
            suite=suite,
            task_id=task_id,
            options=options,
        )
        if clean_result.public_score:
            utility_score_rows.append({"suite": suite, "task_id": task_id, **clean_result.public_score})

        attack_manifests: list[dict[str, Any]] = []
        for run_number in sorted(run_map):
            attack_result = _copy_attack_run(
                dataset=dataset,
                score_index=score_index,
                trajectory_path=run_map[run_number],
                destination=task_root / "attacks" / f"run_{run_number}",
                suite=suite,
                task_id=task_id,
                run_number=run_number,
                options=options,
            )
            attack_manifests.append(attack_result.manifest)
            if attack_result.public_score:
                attack_score_rows.append(
                    {"suite": suite, "task_id": task_id, "run_number": run_number, **attack_result.public_score}
                )
            if attack_result.public_utility_score:
                utility_score_rows.append(
                    {
                        "suite": suite,
                        "task_id": task_id,
                        "run_number": run_number,
                        "role": "attacked_attempt",
                        **attack_result.public_utility_score,
                    }
                )

        task_record = {
            "schema_version": TASK_BUNDLE_SCHEMA_VERSION,
            "release_id": options.release_id,
            "combo_id": combo_id,
            "backend": combo_backend,
            "model": combo_model,
            "suite": suite,
            "task_id": task_id,
            "clean": clean_result.manifest,
            "attacks": attack_manifests,
        }
        _write_json(task_root / "manifest.json", task_record, redact=options.redact)
        task_records.append(task_record)

    _validate_expected_counts(options=options, task_records=task_records)

    scores_dir = combo_root / "scores"
    _write_json(
        scores_dir / "ags.json",
        {"schema_version": ATTACK_SCORES_SCHEMA_VERSION, "results": attack_score_rows},
        redact=options.redact,
    )
    _write_json(
        scores_dir / "utility.json",
        {"schema_version": UTILITY_SCORES_SCHEMA_VERSION, "results": utility_score_rows},
        redact=options.redact,
    )
    aggregate_metrics = _aggregate_metrics(task_records)
    _write_json(scores_dir / "aggregate_metrics.json", aggregate_metrics, redact=options.redact)
    _write_jsonl(combo_root / "task_bundles.jsonl", task_records, redact=options.redact)

    clean_count = len(task_records)
    attack_count = sum(len(_as_list(record.get("attacks"))) for record in task_records)
    manifest = {
        "schema_version": FULL_COMBO_SCHEMA_VERSION,
        "release_id": options.release_id,
        "combo_id": combo_id,
        "dataset_name": dataset.name,
        "backend": combo_backend,
        "model": combo_model,
        "created_at": time.time(),
        "source_raw_by_task_schema": dataset.manifest.get("schema_version"),
        "source_raw_by_task_counts": {
            "task_count": dataset.manifest.get("task_count"),
            "copied_success_runs": dataset.manifest.get("copied_success_runs"),
            "baseline_summary": dataset.manifest.get("baseline_summary"),
        },
        "task_count": len(task_records),
        "clean_trajectory_count": clean_count,
        "attack_trajectory_count": attack_count,
        "per_task_attack_count": options.expected_attack_runs_per_task,
        "task_bundles": "task_bundles.jsonl",
        "scores": {
            "ags": "scores/ags.json",
            "utility": "scores/utility.json",
            "aggregate_metrics": "scores/aggregate_metrics.json",
        },
        "checksums": {},
        "redaction": {
            "applied": bool(options.redact),
            "scan_required": bool(options.run_redaction_scan),
        },
        "raw_by_task_exclusions": {
            "clean_excluded_count": len(clean_collection.excluded),
            "clean_excluded": clean_collection.excluded,
            "clean_reincluded_count": len(clean_reincluded),
            "clean_reincluded": clean_reincluded,
        },
    }

    if options.run_redaction_scan:
        scan = scan_release_tree([combo_root])
        raise_on_redaction_hits(scan)
        _write_json(combo_root / "redaction_scan.json", scan.summary(), redact=False)

    checksum_summary = _generate_checksums(combo_root)
    manifest["checksums"] = checksum_summary
    _write_json(combo_root / "manifest.json", manifest, redact=options.redact)
    archive_path = _create_archive(combo_root, compression=options.compression) if options.archive else None
    archive_size_bytes = archive_path.stat().st_size if archive_path else None
    archive_sha256 = sha256_file(archive_path) if archive_path else ""
    if options.run_redaction_scan:
        final_scan = scan_release_tree([combo_root], exclude_relative_parts=("archives",))
        raise_on_redaction_hits(final_scan)
    return ComboBuildResult(
        combo_id=combo_id,
        combo_root=combo_root,
        manifest_path=combo_root / "manifest.json",
        task_count=len(task_records),
        clean_count=clean_count,
        attack_count=attack_count,
        archive_path=archive_path,
        archive_size_bytes=archive_size_bytes,
        archive_sha256=archive_sha256,
    )


def build_full_release(options: ReleaseBuildOptions) -> ReleaseBuildResult:
    output_root = Path(options.output_root).expanduser()
    if output_root.exists():
        if not options.overwrite:
            raise ReleaseBundleError(f"Release output root already exists: {output_root}")
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    datasets = resolve_raw_by_task_datasets(
        raw_by_task_root=options.raw_by_task_root,
        raw_by_task_dataset=options.datasets or None,
    )
    seen_combo_ids: set[str] = set()
    for dataset in datasets:
        combo_id = _safe_component(_combo_id(dataset), label="combo_id")
        if combo_id in seen_combo_ids:
            raise ReleaseBundleError(f"Duplicate release combo_id after sanitization: {combo_id}")
        seen_combo_ids.add(combo_id)
    score_index = load_score_index(
        ags_score_paths=options.ags_score_paths,
        utility_score_paths=options.utility_score_paths,
    )
    combos: list[ComboBuildResult] = []
    for dataset in datasets:
        combos.append(
            build_combo_bundle(
                dataset,
                score_index=score_index,
                output_root=output_root,
                options=options,
            )
        )
    root_manifest = {
        "schema_version": FULL_RELEASE_SCHEMA_VERSION,
        "release_id": options.release_id,
        "created_at": time.time(),
        "combo_count": len(combos),
        "combos": [
            {
                "combo_id": item.combo_id,
                "manifest": item.manifest_path.relative_to(output_root).as_posix(),
                "task_count": item.task_count,
                "clean_trajectory_count": item.clean_count,
                "attack_trajectory_count": item.attack_count,
                "archive": item.archive_path.relative_to(output_root).as_posix() if item.archive_path else None,
                "archive_size_bytes": item.archive_size_bytes,
                "archive_sha256": item.archive_sha256,
            }
            for item in combos
        ],
    }
    manifest_path = output_root / "manifest.json"
    _write_json(manifest_path, root_manifest, redact=options.redact)
    if options.run_redaction_scan:
        raise_on_redaction_hits(scan_release_tree([manifest_path]))
    return ReleaseBuildResult(release_root=output_root, manifest_path=manifest_path, combos=tuple(combos))


def _parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build public ActBench full release bundles")
    parser.add_argument("--raw-by-task-root", default=str(DEFAULT_RAW_BY_TASK_ROOT))
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--release-id", required=True)
    parser.add_argument("--dataset", action="append", default=[])
    parser.add_argument("--ags-score", action="append", default=[])
    parser.add_argument("--utility-score", action="append", default=[])
    parser.add_argument("--expected-task-count", type=int, default=300)
    parser.add_argument("--expected-attack-runs-per-task", type=int, default=3)
    parser.add_argument("--allow-missing-scores", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--no-redact", action="store_true")
    parser.add_argument("--skip-redaction-scan", action="store_true")
    parser.add_argument("--archive", action="store_true")
    parser.add_argument("--compression", choices=("zstd", "gzip"), default="zstd")
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _parse_args(argv)
    options = ReleaseBuildOptions(
        raw_by_task_root=args.raw_by_task_root,
        output_root=args.output_root,
        release_id=args.release_id,
        datasets=tuple(args.dataset),
        ags_score_paths=tuple(args.ags_score),
        utility_score_paths=tuple(args.utility_score),
        expected_task_count=args.expected_task_count,
        expected_attack_runs_per_task=args.expected_attack_runs_per_task,
        require_scores=not args.allow_missing_scores,
        overwrite=args.overwrite,
        redact=not args.no_redact,
        run_redaction_scan=not args.skip_redaction_scan,
        archive=args.archive,
        compression=args.compression,
    )
    result = build_full_release(options)
    print(
        json.dumps(
            {
                "release_root": str(result.release_root),
                "manifest": str(result.manifest_path),
                "combos": [
                    {
                        "combo_id": item.combo_id,
                        "task_count": item.task_count,
                        "clean": item.clean_count,
                        "attack": item.attack_count,
                        "archive": str(item.archive_path) if item.archive_path else None,
                    }
                    for item in result.combos
                ],
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0
