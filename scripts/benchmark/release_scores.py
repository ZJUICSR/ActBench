"""Score-artifact indexing helpers for public ActBench releases."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Optional, Sequence

from benchmark.offline_scoring import COMBINED_AGS_SEMANTICS, OFFLINE_SCORE_SCHEMA_VERSION
from benchmark.utility_task_scoring import TASK_UTILITY_SCORE_SCHEMA_VERSION


class ReleaseScoreError(ValueError):
    """Raised when public release score artifacts cannot be joined safely."""


class MissingReleaseScoreError(ReleaseScoreError):
    """Raised when no score row matches a release trajectory."""


def _identity(value: Any) -> str:
    """Normalize backend/model labels for logical score joins.

    Raw exports have used harmless capitalization variants such as
    ``ZJUICSR`` and ``zjuicsr``.  The source spelling remains in payloads;
    only index and query keys use this case-insensitive form.
    """

    return str(value or "").strip().casefold()


# The current rescore jobs wrap official per-row artifacts in a combo-level
# envelope.  The envelope name is not itself a row schema; every row must
# still carry the official schema below.  Retired v1 utility artifacts are not
# accepted here.
_CURRENT_COMBO_WRAPPER_SCHEMAS = {
    OFFLINE_SCORE_SCHEMA_VERSION: {
        "actbench.unscored_release_combo_ags.v1",
        "actbench.three_combo_ags.v1",
        "actbench.kimi_gpt55_grok_ags.v1",
    },
    TASK_UTILITY_SCORE_SCHEMA_VERSION: {
        "actbench.unscored_release_combo_ugs.v1",
        "actbench.three_combo_ugs.v1",
        "actbench.kimi_gpt55_grok_ugs.v1",
    },
}


@dataclass(frozen=True)
class AttackScoreQuery:
    backend: str
    model: str
    suite: str
    task_id: str
    run_number: int
    canonical_slot_id: str = ""
    trajectory_id: str = ""
    trajectory_path: Optional[Path] = None
    trajectory_sha256: str = ""


@dataclass(frozen=True)
class CleanScoreQuery:
    backend: str
    model: str
    suite: str
    task_id: str
    trajectory_id: str = ""
    trajectory_path: Optional[Path] = None
    trajectory_sha256: str = ""


@dataclass(frozen=True)
class AttackUtilityScoreQuery:
    """Locate an attacked-attempt UGS row by the same run identity as AGS."""

    backend: str
    model: str
    suite: str
    task_id: str
    run_number: int
    trajectory_id: str = ""
    trajectory_path: Optional[Path] = None
    trajectory_sha256: str = ""


@dataclass
class ScoreIndex:
    """Indexed AGS and utility score rows."""

    attack_rows: list[dict[str, Any]] = field(default_factory=list)
    utility_rows: list[dict[str, Any]] = field(default_factory=list)
    _attack_index: dict[tuple[Any, ...], list[dict[str, Any]]] = field(default_factory=dict)
    _utility_index: dict[tuple[Any, ...], list[dict[str, Any]]] = field(default_factory=dict)

    @property
    def has_attack_utility_rows(self) -> bool:
        return any(
            str(row.get("role") or "") in {"attacked_attempt", "attack", "attacked"}
            for row in self.utility_rows
        )

    def find_attack(self, query: AttackScoreQuery) -> dict[str, Any]:
        keys: list[tuple[Any, ...]] = []
        backend = _identity(query.backend)
        model = _identity(query.model)
        # trajectory_id is the canonical logical identity.  Some historical
        # score envelopes carry a hash from an earlier metadata-only rewrite;
        # prefer the exact id before falling back to that advisory hash.
        if query.trajectory_id:
            keys.append(("trajectory_id_backend_model", backend, model, query.trajectory_id))
        if query.trajectory_sha256:
            keys.append(("trajectory_sha256_backend_model", backend, model, query.trajectory_sha256))
        if query.canonical_slot_id:
            keys.append(("canonical_slot_backend_model", backend, model, query.canonical_slot_id))
        keys.extend(
            [
                (
                    "attack_full",
                    backend,
                    model,
                    query.suite,
                    query.task_id,
                    query.run_number,
                ),
                ("attack_backend_model", backend, model, query.task_id, query.run_number),
            ]
        )
        keys.extend(_scoped_path_keys(backend, model, query.trajectory_path))
        return _lookup_unique(
            self._attack_index,
            keys,
            label="attack score",
            compatible=lambda row: _attack_row_conflicts(row, query),
        )

    def find_clean(self, query: CleanScoreQuery) -> dict[str, Any]:
        keys: list[tuple[Any, ...]] = []
        backend = _identity(query.backend)
        model = _identity(query.model)
        if query.trajectory_id:
            keys.append(("trajectory_id_backend_model", backend, model, query.trajectory_id))
        if query.trajectory_sha256:
            keys.append(("trajectory_sha256_backend_model", backend, model, query.trajectory_sha256))
        keys.extend(
            [
                ("clean_full", backend, model, query.suite, query.task_id),
                ("clean_backend_model", backend, model, query.task_id),
            ]
        )
        keys.extend(_scoped_path_keys(backend, model, query.trajectory_path))
        return _lookup_unique(
            self._utility_index,
            keys,
            label="utility score",
            compatible=lambda row: _clean_row_conflicts(row, query),
        )

    def find_attack_utility(self, query: AttackUtilityScoreQuery) -> dict[str, Any]:
        keys: list[tuple[Any, ...]] = []
        backend = _identity(query.backend)
        model = _identity(query.model)
        if query.trajectory_id:
            keys.append(("utility_attack_trajectory_id_backend_model", backend, model, query.trajectory_id))
        if query.trajectory_sha256:
            keys.append(
                (
                    "utility_attack_trajectory_sha256_backend_model",
                    backend,
                    model,
                    query.trajectory_sha256,
                )
            )
        keys.extend(
            [
                (
                    "utility_attack_full",
                    backend,
                    model,
                    query.suite,
                    query.task_id,
                    query.run_number,
                ),
                (
                    "utility_attack_backend_model",
                    backend,
                    model,
                    query.task_id,
                    query.run_number,
                ),
            ]
        )
        keys.extend(
            tuple(["utility_attack", *key])
            for key in _scoped_path_keys(backend, model, query.trajectory_path)
        )
        return _lookup_unique(
            self._utility_index,
            keys,
            label="attack utility score",
            compatible=lambda row: _attack_utility_row_conflicts(row, query),
        )


_PUBLIC_ATTACK_FIELDS = {
    "schema_version",
    "scoring_mode",
    "scoring_semantics",
    "judge_model",
    "judge_models",
    "llm_invoked",
    "score",
    "ags",
    "ags_gradient",
    "attack_success",
    "attack_success_binary",
    "python_attack_success_binary",
    "llm_attack_success_binary",
    "binary_agreement",
    "binary_evidence_status",
    "binary_policy",
    "threshold_role",
    "gradient_diagnostic_threshold",
    "attack_pass_condition",
    "stealth",
    "attack_success_threshold",
    "pass_threshold_ags_gte",
    "behavior_type",
    "behavior_id",
    "behavior_label",
    "scoring_family",
    "legacy_risk_type",
    "execution_status",
    "execution_exit_code",
    "execution_timed_out",
    "transcript_entry_count",
    "iteration_count",
    "message_count",
    "message_json_chars",
    "message_text_chars",
    "transcript_json_chars",
    "message_role_counts",
    "breakdown",
    "evaluation_error",
    "error_type",
    "notes",
    "usage",
}

_PUBLIC_UTILITY_FIELDS = {
    "schema_version",
    "scoring_semantics",
    "utility_contract_schema",
    "utility_contract_policy",
    "judge_model",
    "score_combination_policy",
    "score_weights",
    "role",
    "ugs",
    "python_utility",
    "python_utility_raw",
    "llm_utility",
    "criterion_count",
    "criterion_scores",
    "utility_checks",
    "python_rubric",
    "checker_name",
    "checker_version",
    "checker_status",
    "caps",
    "warnings",
    "llm_invoked",
    "evaluation_error",
    "error_type",
    "error_message",
    "notes",
    "usage",
    "execution_status",
    "execution_exit_code",
    "execution_timed_out",
    "transcript_entry_count",
    "iteration_count",
    "message_count",
    "message_json_chars",
    "message_text_chars",
    "transcript_json_chars",
    "message_role_counts",
}


def sha256_file(path: Path | str) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _string(value: Any) -> str:
    return str(value) if value is not None else ""


def _int(value: Any, default: int = 0) -> int:
    if isinstance(value, bool):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def score_bool(
    row: dict[str, Any],
    key: str,
    *,
    default: bool | None = None,
    source: str = "score row",
) -> bool:
    if key not in row or row.get(key) is None:
        if default is not None:
            return default
        raise ReleaseScoreError(f"{key} must be a JSON boolean in {source}")
    value = row.get(key)
    if not isinstance(value, bool):
        raise ReleaseScoreError(f"{key} must be a JSON boolean in {source}, got {value!r}")
    return value


def _normalize_bool_aliases(row: dict[str, Any], aliases: Sequence[str], *, canonical: str) -> None:
    values: dict[str, bool] = {}
    source = str(row.get("_score_file") or "score row")
    for key in aliases:
        if key in row and row.get(key) is not None:
            values[key] = score_bool(row, key, source=source)
    if not values:
        return
    canonical_value = next(iter(values.values()))
    conflicts = [f"{key}={value!r}" for key, value in values.items() if value != canonical_value]
    if conflicts:
        preview = ", ".join(f"{key}={value!r}" for key, value in values.items())
        raise ReleaseScoreError(f"Conflicting boolean score aliases in {source}: {preview}")
    row[canonical] = canonical_value


def _normalize_attack_row(row: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(row)
    source = str(normalized.get("_score_file") or "attack score row")
    if "evaluation_error" in normalized and normalized.get("evaluation_error") is not None:
        normalized["evaluation_error"] = score_bool(normalized, "evaluation_error", source=source)
    _normalize_bool_aliases(normalized, ("attack_pass", "pass", "is_success"), canonical="attack_pass")
    # Some current rescore envelopes were produced before the semantics label
    # was renamed.  Explicit dual-evidence fields are authoritative, so
    # normalize only that metadata in the in-memory/public projection without
    # rewriting the historical source artifact.
    if normalized.get("scoring_mode") == "combined_ags" and any(
        key in normalized
        for key in (
            "attack_success_binary",
            "python_attack_success_binary",
            "llm_attack_success_binary",
        )
    ):
        normalized["scoring_semantics"] = COMBINED_AGS_SEMANTICS
        normalized.setdefault("binary_policy", "python_and_llm_binary_required")
        normalized.setdefault("threshold_role", "gradient_diagnostic_only")
        normalized.setdefault(
            "attack_pass_condition",
            "attack_success_binary == 1 (python_attack_success_binary == 1 AND llm_attack_success_binary == 1)",
        )
    return normalized


def _normalize_utility_row(row: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(row)
    source = str(normalized.get("_score_file") or "utility score row")
    if "evaluation_error" in normalized and normalized.get("evaluation_error") is not None:
        normalized["evaluation_error"] = score_bool(normalized, "evaluation_error", source=source)
    # Keep validating a legacy alias when it is present so malformed historical
    # sidecars fail closed.  The current v3 utility schema has no task_pass
    # field and never uses it for UGS aggregation.
    if "task_pass" in normalized and normalized.get("task_pass") is not None:
        normalized["task_pass"] = score_bool(normalized, "task_pass", source=source)
    return normalized


def _load_json_object(path: Path | str) -> dict[str, Any]:
    with Path(path).expanduser().open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ReleaseScoreError(f"Score file must contain a JSON object: {path}")
    return payload


def _infer_suite(task_id: str, row: dict[str, Any]) -> str:
    # The task id is the canonical scope.  A few legacy utility envelopes
    # contain a malformed composite ``suite`` value (for example a comma
    # separated list of unrelated tasks); trusting it before task_id can make
    # an otherwise exact trajectory join look incompatible.
    parts = str(task_id).split("_")
    if len(parts) >= 2 and parts[0] == "task":
        return parts[1]
    for key in ("suite", "scoring_family", "behavior_id"):
        value = row.get(key)
        if value:
            return str(value)
    canonical = str(row.get("canonical_slot_id") or "")
    if "/" in canonical:
        return canonical.split("/", 1)[0]
    return "unknown_suite"


def _canonical_slot_id(row: dict[str, Any]) -> str:
    value = row.get("canonical_slot_id") or _as_dict(row.get("canonical")).get("slot_id")
    return _string(value)


def _path_suffixes(path: Path | str | None) -> list[str]:
    if path is None:
        return []
    raw = Path(path)
    parts = raw.parts
    suffixes: list[str] = []
    if raw.name == "trajectory.json":
        if len(parts) >= 4 and parts[-2].startswith("run_"):
            suffixes.append("/".join(parts[-4:]))
        if len(parts) >= 5 and parts[-2] == "baseline" and parts[-5] == "_baselines":
            suffixes.append("/".join(parts[-5:]))
        if len(parts) >= 3:
            suffixes.append("/".join(parts[-3:]))
    suffixes.append(str(raw))
    try:
        suffixes.append(str(raw.expanduser().resolve()))
    except OSError:
        suffixes.append(str(raw.expanduser()))
    seen: set[str] = set()
    unique: list[str] = []
    for suffix in suffixes:
        if suffix and suffix not in seen:
            seen.add(suffix)
            unique.append(suffix)
    return unique


def _scoped_path_keys(backend: str, model: str, path: Path | str | None) -> list[tuple[Any, ...]]:
    return [("path_backend_model", _identity(backend), _identity(model), suffix) for suffix in _path_suffixes(path)]


def _row_path_keys(row: dict[str, Any]) -> list[tuple[Any, ...]]:
    backend = _identity(row.get("backend"))
    model = _identity(row.get("model"))
    keys: list[tuple[Any, ...]] = []
    for raw_path in (row.get("trajectory_path"), row.get("canonical_trajectory_path")):
        for suffix in _path_suffixes(raw_path):
            keys.append(("path_backend_model", backend, model, suffix))
    return keys


def _add(index: dict[tuple[Any, ...], list[dict[str, Any]]], key: tuple[Any, ...], row: dict[str, Any]) -> None:
    if any(part in {None, ""} for part in key):
        return
    index.setdefault(key, []).append(row)


def _lookup_unique(
    index: dict[tuple[Any, ...], list[dict[str, Any]]],
    keys: Iterable[tuple[Any, ...]],
    *,
    label: str,
    compatible: Any,
) -> dict[str, Any]:
    tried = list(keys)
    for key in tried:
        rows = index.get(key)
        if not rows:
            continue
        unique_rows = {id(row): row for row in rows}
        compatible_rows: list[dict[str, Any]] = []
        conflicts: list[str] = []
        for row in unique_rows.values():
            conflict = compatible(row)
            if conflict:
                conflicts.append(conflict)
            else:
                compatible_rows.append(row)
        if len(compatible_rows) == 1:
            return compatible_rows[0]
        if len(compatible_rows) > 1:
            raise ReleaseScoreError(f"Ambiguous {label} join for key {key!r}: {len(compatible_rows)} rows")
        if conflicts:
            preview = "; ".join(conflicts[:3])
            raise ReleaseScoreError(f"Incompatible {label} join for key {key!r}: {preview}")
    raise MissingReleaseScoreError(f"Missing {label}; tried keys {tried!r}")


def _compare_field(conflicts: list[str], row: dict[str, Any], key: str, expected: Any, *, label: str | None = None) -> None:
    if expected in {None, ""}:
        return
    actual = row.get(key)
    if actual in {None, ""}:
        return
    if str(actual) != str(expected):
        conflicts.append(f"{label or key}={actual!r} != {expected!r}")


def _compare_identity_field(
    conflicts: list[str], row: dict[str, Any], key: str, expected: Any, *, label: str | None = None
) -> None:
    if expected in {None, ""}:
        return
    actual = row.get(key)
    if actual in {None, ""}:
        return
    if _identity(actual) != _identity(expected):
        conflicts.append(f"{label or key}={actual!r} != {expected!r}")


def _compare_trajectory_hash(
    conflicts: list[str], row: dict[str, Any], expected: str, *, trajectory_id: str = ""
) -> None:
    """Compare a hash only when no exact trajectory id already proves identity.

    Score jobs before the current raw export sometimes hashed a metadata-only
    rewrite.  If both sides carry the same trajectory_id, that is the stronger
    logical key and the hash difference is retained for preflight auditing,
    rather than turning a valid join into a false conflict.
    """

    actual = row.get("trajectory_sha256")
    if not expected or not actual:
        return
    row_id = _string(row.get("trajectory_id"))
    if trajectory_id and row_id and row_id == trajectory_id:
        return
    if str(actual) != str(expected):
        conflicts.append(f"trajectory_sha256={actual!r} != {expected!r}")


def _compare_int_field(conflicts: list[str], row: dict[str, Any], key: str, expected: int, *, label: str | None = None) -> None:
    actual = row.get(key)
    if actual in {None, ""}:
        return
    if _int(actual, default=-1) != expected:
        conflicts.append(f"{label or key}={actual!r} != {expected!r}")


def _attack_row_conflicts(row: dict[str, Any], query: AttackScoreQuery) -> str:
    conflicts: list[str] = []
    _compare_identity_field(conflicts, row, "backend", query.backend)
    _compare_identity_field(conflicts, row, "model", query.model)
    row_suite = _infer_suite(_string(row.get("task_id")), row)
    if row_suite != "unknown_suite" and query.suite and row_suite != query.suite:
        conflicts.append(f"suite={row_suite!r} != {query.suite!r}")
    _compare_field(conflicts, row, "task_id", query.task_id)
    _compare_int_field(conflicts, row, "run_number", query.run_number)
    _compare_int_field(conflicts, row, "run_index", query.run_number, label="run_number")
    if query.canonical_slot_id:
        row_canonical = _canonical_slot_id(row)
        if row_canonical and row_canonical != query.canonical_slot_id:
            conflicts.append(f"canonical_slot_id={row_canonical!r} != {query.canonical_slot_id!r}")
    _compare_field(conflicts, row, "trajectory_id", query.trajectory_id)
    _compare_trajectory_hash(conflicts, row, query.trajectory_sha256, trajectory_id=query.trajectory_id)
    return ", ".join(conflicts)


def _clean_row_conflicts(row: dict[str, Any], query: CleanScoreQuery) -> str:
    conflicts: list[str] = []
    _compare_identity_field(conflicts, row, "backend", query.backend)
    _compare_identity_field(conflicts, row, "model", query.model)
    row_task_id = _string(row.get("task_id") or row.get("source_task_id"))
    row_suite = _infer_suite(row_task_id, row)
    if row_suite != "unknown_suite" and query.suite and row_suite != query.suite:
        conflicts.append(f"suite={row_suite!r} != {query.suite!r}")
    if row_task_id and query.task_id and row_task_id != query.task_id:
        conflicts.append(f"task_id={row_task_id!r} != {query.task_id!r}")
    _compare_field(conflicts, row, "trajectory_id", query.trajectory_id)
    _compare_trajectory_hash(conflicts, row, query.trajectory_sha256, trajectory_id=query.trajectory_id)
    return ", ".join(conflicts)


def _attack_utility_row_conflicts(row: dict[str, Any], query: AttackUtilityScoreQuery) -> str:
    conflicts: list[str] = []
    _compare_identity_field(conflicts, row, "backend", query.backend)
    _compare_identity_field(conflicts, row, "model", query.model)
    row_task_id = _string(row.get("task_id") or row.get("source_task_id"))
    row_suite = _infer_suite(row_task_id, row)
    if row_suite != "unknown_suite" and query.suite and row_suite != query.suite:
        conflicts.append(f"suite={row_suite!r} != {query.suite!r}")
    if row_task_id and query.task_id and row_task_id != query.task_id:
        conflicts.append(f"task_id={row_task_id!r} != {query.task_id!r}")
    _compare_int_field(conflicts, row, "run_number", query.run_number)
    _compare_int_field(conflicts, row, "run_index", query.run_number, label="run_number")
    _compare_field(conflicts, row, "trajectory_id", query.trajectory_id)
    _compare_trajectory_hash(conflicts, row, query.trajectory_sha256, trajectory_id=query.trajectory_id)
    if str(row.get("role") or "") not in {"attacked_attempt", "attack", "attacked"}:
        conflicts.append(f"role={row.get('role')!r} is not an attacked attempt")
    return ", ".join(conflicts)


def _attack_keys_for_row(row: dict[str, Any]) -> list[tuple[Any, ...]]:
    task_id = _string(row.get("task_id"))
    suite = _infer_suite(task_id, row)
    run_number = _int(row.get("run_number") or row.get("run_index"), default=0)
    backend = _string(row.get("backend"))
    model = _string(row.get("model"))
    keys: list[tuple[Any, ...]] = []
    canonical = _canonical_slot_id(row)
    if row.get("trajectory_sha256"):
        keys.append(("trajectory_sha256_backend_model", _identity(backend), _identity(model), _string(row.get("trajectory_sha256"))))
    if canonical:
        keys.append(("canonical_slot_backend_model", _identity(backend), _identity(model), canonical))
    if row.get("trajectory_id"):
        keys.append(("trajectory_id_backend_model", _identity(backend), _identity(model), _string(row.get("trajectory_id"))))
    keys.extend(
        [
            ("attack_full", _identity(backend), _identity(model), suite, task_id, run_number),
            ("attack_backend_model", _identity(backend), _identity(model), task_id, run_number),
        ]
    )
    keys.extend(_row_path_keys(row))
    return keys


def _utility_keys_for_row(row: dict[str, Any]) -> list[tuple[Any, ...]]:
    task_id = _string(row.get("task_id") or row.get("source_task_id"))
    suite = _infer_suite(task_id, row)
    backend = _identity(row.get("backend"))
    model = _identity(row.get("model"))
    keys: list[tuple[Any, ...]] = []
    is_attack_utility = str(row.get("role") or "") in {"attacked_attempt", "attack", "attacked"}
    if row.get("trajectory_sha256"):
        keys.append(
            (
                "utility_attack_trajectory_sha256_backend_model" if is_attack_utility else "trajectory_sha256_backend_model",
                backend,
                model,
                _string(row.get("trajectory_sha256")),
            )
        )
    if row.get("trajectory_id"):
        keys.append(
            (
                "utility_attack_trajectory_id_backend_model" if is_attack_utility else "trajectory_id_backend_model",
                backend,
                model,
                _string(row.get("trajectory_id")),
            )
        )
    if is_attack_utility:
        run_number = _int(row.get("run_number") or row.get("run_index"), default=0)
        keys.extend(
            [
                ("utility_attack_full", backend, model, suite, task_id, run_number),
                ("utility_attack_backend_model", backend, model, task_id, run_number),
            ]
        )
        keys.extend(tuple(["utility_attack", *key]) for key in _row_path_keys(row))
    else:
        keys.extend(
            [
                ("clean_full", backend, model, suite, task_id),
                ("clean_backend_model", backend, model, task_id),
            ]
        )
        keys.extend(_row_path_keys(row))
    return keys


def _load_rows(paths: Sequence[Path | str], *, schema: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in paths:
        payload = _load_json_object(path)
        top_schema = payload.get("schema_version")
        wrapper_allowed = top_schema in _CURRENT_COMBO_WRAPPER_SCHEMAS.get(schema, set())
        if top_schema != schema and not wrapper_allowed:
            raise ReleaseScoreError(
                f"Unsupported score schema {top_schema!r} in {path}; expected {schema!r}"
            )
        raw_rows = _as_list(payload.get("results"))
        for row in raw_rows:
            if isinstance(row, dict):
                copied = dict(row)
                row_schema = copied.get("schema_version")
                if row_schema != schema:
                    raise ReleaseScoreError(
                        f"Unsupported row score schema {row_schema!r} in {path}; expected {schema!r}"
                    )
                copied["_score_file"] = str(Path(path).expanduser())
                rows.append(copied)
    return rows


def load_score_index(
    *,
    ags_score_paths: Sequence[Path | str] = (),
    utility_score_paths: Sequence[Path | str] = (),
) -> ScoreIndex:
    """Load and index official AGS and utility score artifacts."""

    index = ScoreIndex()
    index.attack_rows = [_normalize_attack_row(row) for row in _load_rows(ags_score_paths, schema=OFFLINE_SCORE_SCHEMA_VERSION)]
    index.utility_rows = [
        _normalize_utility_row(row)
        for row in _load_rows(utility_score_paths, schema=TASK_UTILITY_SCORE_SCHEMA_VERSION)
    ]
    for row in index.attack_rows:
        for key in _attack_keys_for_row(row):
            _add(index._attack_index, key, row)
    for row in index.utility_rows:
        for key in _utility_keys_for_row(row):
            _add(index._utility_index, key, row)
    return index


def public_attack_score(row: dict[str, Any]) -> dict[str, Any]:
    """Return a public-safe attack score sidecar payload."""

    payload = {key: row.get(key) for key in sorted(_PUBLIC_ATTACK_FIELDS) if key in row}
    # ``attack_success_threshold`` was part of the retired 0.8 projection.  A
    # current public score has an explicit dual-evidence binary and a separate
    # five-level AGS gradient, so the old threshold must not be re-published.
    payload.pop("attack_success_threshold", None)
    payload["source_schema_version"] = row.get("schema_version") or OFFLINE_SCORE_SCHEMA_VERSION
    return payload


def public_utility_score(row: dict[str, Any]) -> dict[str, Any]:
    """Return a public-safe clean utility score sidecar payload."""

    payload = {key: row.get(key) for key in sorted(_PUBLIC_UTILITY_FIELDS) if key in row}
    payload["source_schema_version"] = row.get("schema_version") or TASK_UTILITY_SCORE_SCHEMA_VERSION
    return payload
