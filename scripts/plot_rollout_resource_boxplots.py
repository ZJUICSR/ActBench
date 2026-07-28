#!/usr/bin/env python3
"""Plot generation-time token and wall-clock resource boxplots for ActBench rollouts."""

from __future__ import annotations

import argparse
import csv
import io
import json
import math
import re
import tarfile
from dataclasses import dataclass, field
from pathlib import Path
from statistics import mean, median
from typing import Any


OPENCLAW_DATASET_LABELS = {
    "openclaw_openrouter_anthropic_claude_opus_4_8_trajectories_20260718_runs3_parallel": "Claude-Opus-4.8",
    "openclaw_openrouter_anthropic_claude_sonnet_4_6_trajectories_20260715_runs3_parallel": "Claude-Sonnet-4.6",
    "openclaw_zjuicsr_gpt-5.5_trajectories_20260715_runs3_parallel": "GPT-5.5",
    "openclaw_zjuicsr_gpt-5.4-mini_trajectories_20260714_runs3_parallel": "GPT-5.4-mini",
    "openclaw_taisure-glm-5-2_trajectories_20260714_runs3_parallel": "GLM-5.2",
    "openclaw_taisure_qwen3_7_max_trajectories_20260714_215927_runs3_parallel": "Qwen-3.7-max",
    "openclaw_taisure_qwen3_7_plus_trajectories_20260714_runs3_parallel": "Qwen-3.7-plus",
    "openclaw_tencent_tokenhub_hy3_trajectories_20260718_runs3_parallel_key2": "Hunyuan-3.0",
    "openclaw_taisure_kimi_k2_6_trajectories_20260715_runs3_parallel": "Kimi-k2.6",
    "openclaw_moonshot_kimi_k3_trajectories_20260726_runs3_parallel": "Kimi-K3",
    "openclaw_minimax_minimax-m3_trajectories_20260716_runs3_parallel": "MiniMax-M3",
    "openclaw_minimax_minimax_m2_7_trajectories_20260720_runs3_parallel": "MiniMax-M2.7",
    "openclaw_deepseek_v4_pro_trajectories_20260713_runs3": "Deepseek-v4-Pro",
    "openclaw_deepseek_v4_flash_trajectories_20260714_runs3_parallel": "Deepseek-v4-Flash",
}

OPENCLAW_MODEL_ORDER = [
    "Claude-Opus-4.8",
    "Claude-Sonnet-4.6",
    "GPT-5.5",
    "GPT-5.4-mini",
    "GLM-5.2",
    "Qwen-3.7-max",
    "Qwen-3.7-plus",
    "Hunyuan-3.0",
    "Kimi-k2.6",
    "Kimi-K3",
    "MiniMax-M3",
    "MiniMax-M2.7",
    "Deepseek-v4-Pro",
    "Deepseek-v4-Flash",
]

DEEPSEEK_V4_PRO_AGENT_DATASETS = {
    "openclaw_deepseek_v4_pro_trajectories_20260713_runs3": "OpenClaw",
    "openagent_deepseek_v4_pro_trajectories_20260717_runs3_merged": "OpenAgent",
    "claudecode_deepseek_deepseek_v4_pro_trajectories_20260720_runs2-3_parallel_fixedenv": "ClaudeCode",
    "hermes_deepseek_deepseek_v4_pro_trajectories_20260718_runs3_parallel": "Hermes",
    "opencode_deepseek_deepseek_v4_pro_trajectories_20260716_runs3_parallel": "OpenCode",
    "qwenpaw_deepseek_deepseek_v4_pro_trajectories_20260717_runs3_sequential": "QwenPaw",
}

DEEPSEEK_AGENT_ORDER = ["OpenClaw", "OpenAgent", "ClaudeCode", "Hermes", "OpenCode", "QwenPaw"]

DEFAULT_RAW_ROOTS = [
    Path("/home/lym/pack/raw_by_task"),
    Path(
        "/home/lym/remote_actbench_imports/taisure.ai/extracted/"
        "actbench_final_taxonomy_export_taisure.ai__20260724_024130/pack/raw_by_task"
    ),
]

DEFAULT_TAR_ARCHIVES = [
    Path(
        "/home/lym/remote_actbench_imports/DESKTOP-EM1S9GK/"
        "actbench_final_taxonomy_export_DESKTOP-EM1S9GK__20260723_114758.tar.gz"
    ),
]

RESOURCE_FIELDS = [
    "execution_time",
    "total_tokens",
    "raw_total_tokens",
    "input_tokens",
    "output_tokens",
    "cache_read_tokens",
    "cache_write_tokens",
    "cost_usd",
    "request_count",
]

PLOT_METRICS = ["total_tokens", "execution_time"]


@dataclass(frozen=True)
class MetricSpec:
    key: str
    title_name: str
    ylabel: str
    stem: str
    folder: str
    median_digits: int


METRIC_SPECS = {
    "total_tokens": MetricSpec(
        key="total_tokens",
        title_name="cache-inclusive total token count",
        ylabel="Total tokens (input + output + cache)",
        stem="total_tokens",
        folder="token",
        median_digits=0,
    ),
    "execution_time": MetricSpec(
        key="execution_time",
        title_name="execution time",
        ylabel="Execution time (s)",
        stem="execution_time",
        folder="time",
        median_digits=1,
    ),
}


@dataclass
class ResourceRecord:
    kind: str
    row_index: int
    dataset_id: str
    score_row_index: str
    b_category: str
    task_id: str
    run_number: str
    trajectory_path: str
    resolved_key: str
    resolved_source: str
    source_kind: str
    evaluation_error: bool
    execution_status: str
    execution_timed_out: bool | None
    execution_exit_code: int | None
    metrics: dict[str, float | None]


@dataclass
class PendingRow:
    kind: str
    row_index: int
    row: dict[str, Any]
    dataset_id: str
    keys: list[str]


@dataclass
class Group:
    label: str
    dataset_id: str
    records: list[ResourceRecord] = field(default_factory=list)

    def values(self, metric: str) -> list[float]:
        return [value for record in self.records if (value := record.metrics.get(metric)) is not None]


@dataclass
class Coverage:
    rows_seen: dict[str, int] = field(default_factory=lambda: {"attack": 0, "clean": 0})
    rows_used: dict[str, int] = field(default_factory=lambda: {"attack": 0, "clean": 0})
    rows_missing: dict[str, int] = field(default_factory=lambda: {"attack": 0, "clean": 0})
    rows_without_resource: dict[str, int] = field(default_factory=lambda: {"attack": 0, "clean": 0})
    evaluation_error_rows: dict[str, int] = field(default_factory=lambda: {"attack": 0, "clean": 0})
    source_counts: dict[str, dict[str, int]] = field(
        default_factory=lambda: {"attack": {}, "clean": {}}
    )
    dataset_counts: dict[str, dict[str, dict[str, int]]] = field(
        default_factory=lambda: {"attack": {}, "clean": {}}
    )
    missing_examples: list[dict[str, str]] = field(default_factory=list)
    read_errors: list[str] = field(default_factory=list)

    def add_source(self, kind: str, source_kind: str) -> None:
        self.source_counts[kind][source_kind] = self.source_counts[kind].get(source_kind, 0) + 1

    def add_dataset_count(self, kind: str, dataset: str, key: str) -> None:
        dataset_bucket = self.dataset_counts[kind].setdefault(
            dataset,
            {"seen": 0, "used": 0, "missing": 0, "without_resource": 0},
        )
        dataset_bucket[key] += 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Plot rollout generation-time token/time boxplots from raw trajectory JSONs."
    )
    parser.add_argument(
        "--ags-json",
        type=Path,
        required=True,
        help="Merged AGS JSON with top-level results[] for attack trajectories.",
    )
    parser.add_argument(
        "--ugs-json",
        type=Path,
        required=True,
        help="Merged UGS JSON with top-level results[] for clean baseline trajectories.",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("results/figures/rollout_resources"),
        help="Output directory for figures and TSVs.",
    )
    parser.add_argument(
        "--raw-root",
        action="append",
        type=Path,
        default=None,
        help="Directory containing raw_by_task dataset folders. May be repeated.",
    )
    parser.add_argument(
        "--tar-archive",
        action="append",
        type=Path,
        default=None,
        help="Tar archive containing pack/raw_by_task entries. May be repeated.",
    )
    parser.add_argument(
        "--format",
        dest="formats",
        action="append",
        choices=("pdf", "png", "svg"),
        default=None,
        help="Figure format to write. May be repeated. Defaults to pdf and svg.",
    )
    parser.add_argument(
        "--show-fliers",
        action="store_true",
        help="Show outlier points. Default hides fliers so boxes remain readable.",
    )
    parser.add_argument(
        "--exclude-evaluation-errors",
        action="store_true",
        help="Exclude score rows marked evaluation_error before resolving rollout resources.",
    )
    parser.add_argument(
        "--skip-plots",
        action="store_true",
        help="Only write TSV/manifest outputs; do not import matplotlib or render figures.",
    )
    parser.add_argument("--dpi", type=int, default=300, help="Raster DPI for PNG outputs.")
    return parser.parse_args()


def load_rows(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    results = payload.get("results")
    if not isinstance(results, list):
        raise ValueError(f"{path} does not contain a top-level results[] list")
    return [row for row in results if isinstance(row, dict)]


def finite_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def dataset_id(row: dict[str, Any]) -> str:
    value = row.get("score_dataset_id") or row.get("dataset_id") or row.get("dataset")
    return str(value) if value else "unknown_dataset"


def b_category(row: dict[str, Any]) -> str:
    for key in ("suite", "b_category", "scoring_family", "behavior_id"):
        value = row.get(key)
        if isinstance(value, str) and re.fullmatch(r"B(?:[1-9]|1[0-5])", value):
            return value
    for key in (
        "task_id",
        "source_task_id",
        "clean_task_id",
        "trajectory_task_id",
        "behavior_id",
        "legacy_behavior_task_id",
        "legacy_behavior_id",
        "canonical_slot_id",
        "trajectory_path",
        "canonical_trajectory_path",
    ):
        value = row.get(key)
        if not isinstance(value, str):
            continue
        match = re.search(r"(?:^|[_/.-])B(1[0-5]|[1-9])(?:[_/.-]|$)", value)
        if match:
            return f"B{match.group(1)}"
    return "unknown"


def task_id(row: dict[str, Any]) -> str:
    for key in ("source_task_id", "task_id", "trajectory_task_id", "clean_task_id"):
        value = row.get(key)
        if isinstance(value, str) and value:
            return value.removesuffix("_baseline")
    return "unknown_task"


def run_number(row: dict[str, Any]) -> str:
    value = row.get("run_number")
    if value not in (None, ""):
        return str(value)
    value = row.get("run_index")
    if value not in (None, ""):
        return str(value)
    run_id = row.get("run_id")
    if isinstance(run_id, str):
        match = re.search(r"run[_-]?(\d+)", run_id)
        if match:
            return match.group(1)
    return ""


def clean_path_text(value: Any) -> str:
    return str(value).replace("\\", "/") if value is not None else ""


def append_unique(items: list[str], value: str) -> None:
    if value and value not in items:
        items.append(value)


def raw_by_task_key_from_path(path_text: str, dataset: str) -> str | None:
    if not path_text:
        return None
    text = clean_path_text(path_text)
    for marker in (f"/raw_by_task/{dataset}/", f"raw_by_task/{dataset}/"):
        if marker in text:
            return f"{dataset}/{text.split(marker, 1)[1]}"
    if text.startswith(f"{dataset}/"):
        return text
    marker = f"/{dataset}/"
    if marker in text and text.endswith("trajectory.json"):
        return f"{dataset}/{text.split(marker, 1)[1]}"
    return None


def raw_by_task_key_from_canonical(canonical: Any, dataset: str) -> str | None:
    if not isinstance(canonical, str) or not canonical:
        return None
    text = clean_path_text(canonical)
    if text.startswith("trajectories/"):
        rel = text.removeprefix("trajectories/").replace("/runs/", "/")
        return f"{dataset}/{rel}"
    return raw_by_task_key_from_path(text, dataset)


def fallback_raw_by_task_key(kind: str, row: dict[str, Any], dataset: str) -> str | None:
    category = b_category(row)
    task = task_id(row)
    if category == "unknown" or task == "unknown_task":
        return None
    if kind == "clean":
        return f"{dataset}/_baselines/{category}/{task}/baseline/trajectory.json"
    number = run_number(row)
    if not number:
        return None
    return f"{dataset}/{category}/{task}/run_{number}/trajectory.json"


def candidate_raw_by_task_keys(kind: str, row: dict[str, Any]) -> list[str]:
    dataset = dataset_id(row)
    keys: list[str] = []
    append_unique(keys, raw_by_task_key_from_path(clean_path_text(row.get("trajectory_path")), dataset) or "")
    append_unique(keys, raw_by_task_key_from_canonical(row.get("canonical_trajectory_path"), dataset) or "")
    append_unique(keys, fallback_raw_by_task_key(kind, row, dataset) or "")
    return keys


def tar_member_key(member_name: str) -> str | None:
    name = clean_path_text(member_name)
    marker = "/pack/raw_by_task/"
    if marker in name:
        return name.split(marker, 1)[1]
    marker = "pack/raw_by_task/"
    if marker in name:
        return name.split(marker, 1)[1]
    marker = "/raw_by_task/"
    if marker in name:
        return name.split(marker, 1)[1]
    if name.startswith("raw_by_task/"):
        return name.removeprefix("raw_by_task/")
    return None


def load_json_path(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"{path} is not a JSON object")
    return payload


def extract_resource(payload: dict[str, Any]) -> tuple[dict[str, float | None], str, bool | None, int | None]:
    execution = payload.get("execution") if isinstance(payload.get("execution"), dict) else {}
    usage = execution.get("usage") if isinstance(execution.get("usage"), dict) else {}
    if not usage and isinstance(payload.get("usage"), dict):
        usage = payload["usage"]

    raw_total_tokens = finite_float(usage.get("total_tokens"))
    input_tokens = finite_float(usage.get("input_tokens"))
    output_tokens = finite_float(usage.get("output_tokens"))
    cache_read_tokens = finite_float(usage.get("cache_read_tokens"))
    cache_write_tokens = finite_float(usage.get("cache_write_tokens"))
    token_components = [
        value
        for value in (input_tokens, output_tokens, cache_read_tokens, cache_write_tokens)
        if value is not None
    ]
    total_tokens = sum(token_components) if token_components else raw_total_tokens
    metrics = {
        "execution_time": finite_float(execution.get("execution_time", payload.get("execution_time"))),
        "total_tokens": total_tokens,
        "raw_total_tokens": raw_total_tokens,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cache_read_tokens": cache_read_tokens,
        "cache_write_tokens": cache_write_tokens,
        "cost_usd": finite_float(usage.get("cost_usd")),
        "request_count": finite_float(usage.get("request_count")),
    }
    status = str(execution.get("status", payload.get("execution_status", "")))
    timed_out_value = execution.get("timed_out", payload.get("execution_timed_out"))
    timed_out = timed_out_value if isinstance(timed_out_value, bool) else None
    exit_code = int_or_none(execution.get("exit_code", payload.get("execution_exit_code")))
    return metrics, status, timed_out, exit_code


def has_resource(metrics: dict[str, float | None]) -> bool:
    return any(metrics.get(field) is not None for field in ("execution_time", "total_tokens"))


def record_from_resource(
    kind: str,
    row_index: int,
    row: dict[str, Any],
    key: str,
    source: str,
    source_kind: str,
    payload: dict[str, Any],
) -> ResourceRecord | None:
    metrics, status, timed_out, exit_code = extract_resource(payload)
    if not has_resource(metrics):
        return None
    return ResourceRecord(
        kind=kind,
        row_index=row_index,
        dataset_id=dataset_id(row),
        score_row_index=str(row.get("score_row_index", row_index)),
        b_category=b_category(row),
        task_id=task_id(row),
        run_number=run_number(row),
        trajectory_path=clean_path_text(row.get("trajectory_path")),
        resolved_key=key,
        resolved_source=source,
        source_kind=source_kind,
        evaluation_error=bool(row.get("evaluation_error")),
        execution_status=status,
        execution_timed_out=timed_out,
        execution_exit_code=exit_code,
        metrics=metrics,
    )


def resolve_local_payload(
    row: dict[str, Any],
    keys: list[str],
    raw_roots: list[Path],
    coverage: Coverage,
) -> tuple[dict[str, Any], str, str, str] | None:
    path_text = clean_path_text(row.get("trajectory_path"))
    if path_text:
        path = Path(path_text)
        if path.is_file():
            try:
                return load_json_path(path), path_text, "absolute_path", keys[0] if keys else path.name
            except Exception as exc:  # noqa: BLE001 - keep plotting despite one bad raw file.
                coverage.read_errors.append(f"{path}: {exc}")

    for key in keys:
        for root in raw_roots:
            path = root / key
            if not path.is_file():
                continue
            try:
                return load_json_path(path), str(path), f"raw_root:{root}", key
            except Exception as exc:  # noqa: BLE001
                coverage.read_errors.append(f"{path}: {exc}")
    return None


def load_needed_tar_payloads(
    tar_archives: list[Path],
    needed_keys: set[str],
    coverage: Coverage,
) -> dict[str, tuple[dict[str, Any], str, str]]:
    found: dict[str, tuple[dict[str, Any], str, str]] = {}
    remaining = set(needed_keys)
    for tar_path in tar_archives:
        if not remaining:
            break
        if not tar_path.is_file():
            continue
        try:
            with tarfile.open(tar_path, "r:gz") as archive:
                for member in archive:
                    if not remaining:
                        break
                    if not member.isfile() or not member.name.endswith("trajectory.json"):
                        continue
                    key = tar_member_key(member.name)
                    if key not in remaining:
                        continue
                    handle = archive.extractfile(member)
                    if handle is None:
                        continue
                    try:
                        with io.TextIOWrapper(handle, encoding="utf-8") as text_handle:
                            payload = json.load(text_handle)
                        if isinstance(payload, dict):
                            source = f"{tar_path}:{member.name}"
                            found[key] = (payload, source, f"tar:{tar_path}")
                            remaining.remove(key)
                    except Exception as exc:  # noqa: BLE001
                        coverage.read_errors.append(f"{tar_path}:{member.name}: {exc}")
        except Exception as exc:  # noqa: BLE001
            coverage.read_errors.append(f"{tar_path}: {exc}")
    return found


def collect_resource_records(
    kind: str,
    rows: list[dict[str, Any]],
    raw_roots: list[Path],
    tar_archives: list[Path],
    exclude_evaluation_errors: bool,
    coverage: Coverage,
) -> list[ResourceRecord]:
    records: list[ResourceRecord] = []
    pending: list[PendingRow] = []

    for row_index, row in enumerate(rows):
        if exclude_evaluation_errors and row.get("evaluation_error"):
            continue
        dataset = dataset_id(row)
        coverage.rows_seen[kind] += 1
        coverage.add_dataset_count(kind, dataset, "seen")
        if row.get("evaluation_error"):
            coverage.evaluation_error_rows[kind] += 1

        keys = candidate_raw_by_task_keys(kind, row)
        local = resolve_local_payload(row, keys, raw_roots, coverage)
        if local is not None:
            payload, source, source_kind, key = local
            record = record_from_resource(kind, row_index, row, key, source, source_kind, payload)
            if record is not None:
                records.append(record)
                coverage.rows_used[kind] += 1
                coverage.add_source(kind, source_kind)
                coverage.add_dataset_count(kind, dataset, "used")
                continue
            coverage.rows_without_resource[kind] += 1
            coverage.add_dataset_count(kind, dataset, "without_resource")
        pending.append(PendingRow(kind=kind, row_index=row_index, row=row, dataset_id=dataset, keys=keys))

    needed_keys = {key for item in pending for key in item.keys}
    tar_payloads = load_needed_tar_payloads(tar_archives, needed_keys, coverage)

    for item in pending:
        record: ResourceRecord | None = None
        for key in item.keys:
            tar_payload = tar_payloads.get(key)
            if tar_payload is None:
                continue
            payload, source, source_kind = tar_payload
            record = record_from_resource(item.kind, item.row_index, item.row, key, source, source_kind, payload)
            if record is not None:
                break
            coverage.rows_without_resource[kind] += 1
            coverage.add_dataset_count(kind, item.dataset_id, "without_resource")
        if record is not None:
            records.append(record)
            coverage.rows_used[kind] += 1
            coverage.add_source(kind, record.source_kind)
            coverage.add_dataset_count(kind, item.dataset_id, "used")
            continue
        coverage.rows_missing[kind] += 1
        coverage.add_dataset_count(kind, item.dataset_id, "missing")
        if len(coverage.missing_examples) < 30:
            coverage.missing_examples.append(
                {
                    "kind": item.kind,
                    "dataset_id": item.dataset_id,
                    "score_row_index": str(item.row.get("score_row_index", item.row_index)),
                    "trajectory_path": clean_path_text(item.row.get("trajectory_path")),
                    "candidate_keys": ";".join(item.keys),
                }
            )
    return records


def collect_groups(records: list[ResourceRecord], scenario: str, metric: str) -> list[Group]:
    if scenario == "openclaw_models":
        groups = {
            dataset: Group(label=label, dataset_id=dataset)
            for dataset, label in OPENCLAW_DATASET_LABELS.items()
        }
        order = OPENCLAW_MODEL_ORDER
    elif scenario == "deepseek_v4_pro_agents":
        groups = {
            dataset: Group(label=label, dataset_id=dataset)
            for dataset, label in DEEPSEEK_V4_PRO_AGENT_DATASETS.items()
        }
        order = DEEPSEEK_AGENT_ORDER
    else:
        raise ValueError(f"unsupported scenario: {scenario}")

    for record in records:
        group = groups.get(record.dataset_id)
        if group is None or record.metrics.get(metric) is None:
            continue
        group.records.append(record)

    by_label = {group.label: group for group in groups.values() if group.records}
    return [by_label[label] for label in order if label in by_label]


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return float("nan")
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    pos = (len(ordered) - 1) * pct / 100.0
    lower = math.floor(pos)
    upper = math.ceil(pos)
    if lower == upper:
        return ordered[int(pos)]
    frac = pos - lower
    return ordered[lower] * (1.0 - frac) + ordered[upper] * frac


def fmt_float(value: float | None, digits: int = 6) -> str:
    return "" if value is None else f"{value:.{digits}f}"


def format_compact(value: float, digits: int = 1) -> str:
    abs_value = abs(value)
    if abs_value >= 1_000_000:
        return f"{value / 1_000_000:.{digits}f}M"
    if abs_value >= 1_000:
        return f"{value / 1_000:.{digits}f}k"
    if digits == 0:
        return f"{value:.0f}"
    return f"{value:.{digits}f}"


def format_median(value: float, spec: MetricSpec) -> str:
    if spec.key == "total_tokens":
        return format_compact(value, 0)
    return f"{value:.{spec.median_digits}f}"


def write_values_tsv(
    groups_by_key: dict[tuple[str, str, str], list[Group]],
    out_dir: Path,
) -> Path:
    path = out_dir / "rollout_resource_values.tsv"
    fieldnames = [
        "metric",
        "scenario",
        "kind",
        "label",
        "dataset_id",
        "score_row_index",
        "row_index",
        "b_category",
        "task_id",
        "run_number",
        "value",
        *RESOURCE_FIELDS,
        "evaluation_error",
        "execution_status",
        "execution_timed_out",
        "execution_exit_code",
        "source_kind",
        "resolved_key",
        "trajectory_path",
        "resolved_source",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter="\t")
        writer.writeheader()
        for (metric, scenario, kind), groups in groups_by_key.items():
            for group in groups:
                for record in group.records:
                    value = record.metrics.get(metric)
                    if value is None:
                        continue
                    row = {
                        "metric": metric,
                        "scenario": scenario,
                        "kind": kind,
                        "label": group.label,
                        "dataset_id": record.dataset_id,
                        "score_row_index": record.score_row_index,
                        "row_index": record.row_index,
                        "b_category": record.b_category,
                        "task_id": record.task_id,
                        "run_number": record.run_number,
                        "value": fmt_float(value),
                        "evaluation_error": record.evaluation_error,
                        "execution_status": record.execution_status,
                        "execution_timed_out": record.execution_timed_out,
                        "execution_exit_code": record.execution_exit_code,
                        "source_kind": record.source_kind,
                        "resolved_key": record.resolved_key,
                        "trajectory_path": record.trajectory_path,
                        "resolved_source": record.resolved_source,
                    }
                    for field_name in RESOURCE_FIELDS:
                        row[field_name] = fmt_float(record.metrics.get(field_name))
                    writer.writerow(row)
    return path


def write_summary_tsv(
    groups_by_key: dict[tuple[str, str, str], list[Group]],
    out_dir: Path,
) -> Path:
    path = out_dir / "rollout_resource_summary.tsv"
    fieldnames = [
        "metric",
        "scenario",
        "kind",
        "label",
        "dataset_id",
        "n",
        "mean",
        "median",
        "q1",
        "q3",
        "p5",
        "p95",
        "min",
        "max",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter="\t")
        writer.writeheader()
        for (metric, scenario, kind), groups in groups_by_key.items():
            for group in groups:
                values = group.values(metric)
                writer.writerow(
                    {
                        "metric": metric,
                        "scenario": scenario,
                        "kind": kind,
                        "label": group.label,
                        "dataset_id": group.dataset_id,
                        "n": len(values),
                        "mean": fmt_float(mean(values)),
                        "median": fmt_float(median(values)),
                        "q1": fmt_float(percentile(values, 25)),
                        "q3": fmt_float(percentile(values, 75)),
                        "p5": fmt_float(percentile(values, 5)),
                        "p95": fmt_float(percentile(values, 95)),
                        "min": fmt_float(min(values)),
                        "max": fmt_float(max(values)),
                    }
                )
    return path


def write_manifest(
    ags_json: Path,
    ugs_json: Path,
    raw_roots: list[Path],
    tar_archives: list[Path],
    groups_by_key: dict[tuple[str, str, str], list[Group]],
    coverage: Coverage,
    show_fliers: bool,
    exclude_evaluation_errors: bool,
    formats: list[str],
    skip_plots: bool,
    out_dir: Path,
) -> Path:
    path = out_dir / "manifest.json"
    payload = {
        "description": "Generation-time rollout resource boxplots from raw trajectory execution fields.",
        "sources": {"attack_ags_rows": str(ags_json), "clean_ugs_rows": str(ugs_json)},
        "raw_roots": [str(root) for root in raw_roots],
        "tar_archives": [str(tar_path) for tar_path in tar_archives],
        "resource_fields": {
            "execution_time": "execution.execution_time",
            "total_tokens": "derived: execution.usage.input_tokens + output_tokens + cache_read_tokens + cache_write_tokens when components are present; otherwise execution.usage.total_tokens",
            "raw_total_tokens": "execution.usage.total_tokens",
            "input_tokens": "execution.usage.input_tokens",
            "output_tokens": "execution.usage.output_tokens",
            "cache_read_tokens": "execution.usage.cache_read_tokens",
            "cache_write_tokens": "execution.usage.cache_write_tokens",
            "cost_usd": "execution.usage.cost_usd",
            "request_count": "execution.usage.request_count",
        },
        "score_row_usage_note": "Score-row usage/timing fields are judge/scoring resources and are not used here.",
        "token_accounting_note": "The token plot uses a cache-inclusive derived total because backend-provided execution.usage.total_tokens is not consistent about cache tokens across agents. The raw field is preserved as raw_total_tokens in rollout_resource_values.tsv.",
        "row_filtering": {
            "uses_final_score_rows_as_selection_list": True,
            "exclude_evaluation_errors": exclude_evaluation_errors,
        },
        "boxplot_whiskers": "matplotlib default 1.5 IQR",
        "show_fliers": show_fliers,
        "formats": formats,
        "plots_written": not skip_plots,
        "figure_dirs": {
            metric: str(out_dir / spec.folder) for metric, spec in METRIC_SPECS.items()
        },
        "coverage": {
            "rows_seen": coverage.rows_seen,
            "rows_used": coverage.rows_used,
            "rows_missing": coverage.rows_missing,
            "rows_without_resource": coverage.rows_without_resource,
            "evaluation_error_rows_included": coverage.evaluation_error_rows,
            "source_counts": coverage.source_counts,
            "dataset_counts": coverage.dataset_counts,
            "missing_examples": coverage.missing_examples,
            "read_errors": coverage.read_errors[:50],
            "read_error_count": len(coverage.read_errors),
        },
        "scenarios": {
            f"{metric}:{scenario}:{kind}": [
                {"label": group.label, "dataset_id": group.dataset_id, "n": len(group.values(metric))}
                for group in groups
            ]
            for (metric, scenario, kind), groups in groups_by_key.items()
        },
    }
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    return path


def require_matplotlib() -> Any:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.ticker import FuncFormatter
    except ImportError as exc:
        raise SystemExit("matplotlib is required for plotting.") from exc
    return plt, FuncFormatter


def configure_matplotlib(plt: Any) -> None:
    plt.rcParams.update(
        {
            "font.size": 10.0,
            "font.weight": "bold",
            "axes.labelsize": 11.2,
            "axes.labelweight": "bold",
            "axes.titlesize": 11.5,
            "axes.titleweight": "bold",
            "xtick.labelsize": 9.2,
            "ytick.labelsize": 10.0,
            "legend.fontsize": 10.0,
            "figure.titlesize": 12.0,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
            "svg.fonttype": "none",
        }
    )


def bold_axis_text(axis: Any) -> None:
    axis.xaxis.label.set_fontweight("bold")
    axis.yaxis.label.set_fontweight("bold")
    for tick_label in axis.get_xticklabels() + axis.get_yticklabels():
        tick_label.set_fontweight("bold")


def style_axis(axis: Any, labels_count: int, *, combined: bool = False) -> None:
    axis.grid(axis="y", color="#DDDDDD", linewidth=0.6)
    axis.set_axisbelow(True)
    axis.spines["top"].set_visible(False)
    axis.spines["right"].set_visible(False)
    if labels_count > 8:
        axis.tick_params(axis="x", rotation=38 if combined else 35, labelsize=8.2 if combined else 8.8)
    else:
        axis.tick_params(axis="x", rotation=18, labelsize=9.8 if combined else 9.4)
    for tick in axis.get_xticklabels():
        tick.set_ha("right")
    axis.tick_params(axis="y", labelsize=10.4 if combined else 10.0)
    bold_axis_text(axis)


def apply_metric_tick_formatter(axis: Any, metric: str, FuncFormatter: Any) -> None:
    if metric == "total_tokens":
        axis.yaxis.set_major_formatter(FuncFormatter(lambda value, _pos: format_compact(value, 0)))


def plot_boxplot(
    plt: Any,
    FuncFormatter: Any,
    metric: str,
    groups: list[Group],
    title: str,
    xlabel: str,
    stem: str,
    out_dir: Path,
    formats: list[str],
    show_fliers: bool,
    dpi: int,
    note_subject: str,
) -> None:
    spec = METRIC_SPECS[metric]
    labels = [group.label for group in groups]
    values = [group.values(metric) for group in groups]
    fig_width = 10.2 if len(groups) > 8 else 6.4
    fig, axis = plt.subplots(figsize=(fig_width, 4.8), constrained_layout=False)
    fig.subplots_adjust(left=0.08, right=0.985, bottom=0.32 if len(groups) > 8 else 0.21, top=0.96)

    box = axis.boxplot(
        values,
        tick_labels=labels,
        patch_artist=True,
        showfliers=show_fliers,
        widths=0.58,
        medianprops={"color": "#222222", "linewidth": 1.35},
        boxprops={"linewidth": 0.9, "color": "#555555"},
        whiskerprops={"linewidth": 0.85, "color": "#555555"},
        capprops={"linewidth": 0.85, "color": "#555555"},
        flierprops={
            "marker": "o",
            "markersize": 2.2,
            "markerfacecolor": "#999999",
            "markeredgecolor": "#999999",
            "alpha": 0.35,
        },
    )
    for patch in box["boxes"]:
        patch.set_facecolor("#56B4E9")
        patch.set_alpha(0.75)

    for index, group in enumerate(groups, start=1):
        med = median(group.values(metric))
        axis.text(
            index,
            med,
            format_median(med, spec),
            ha="center",
            va="bottom",
            fontsize=8.0,
            fontweight="bold",
            color="#222222",
        )

    del title, note_subject
    axis.set_ylabel(spec.ylabel, fontsize=11.2, fontweight="bold")
    axis.set_xlabel(xlabel, fontsize=11.2, fontweight="bold")
    apply_metric_tick_formatter(axis, metric, FuncFormatter)
    style_axis(axis, len(groups))

    for suffix in formats:
        path = out_dir / f"{stem}.{suffix}"
        fig.savefig(path, dpi=dpi if suffix == "png" else None, bbox_inches="tight")
    plt.close(fig)


def plot_combined_boxplot(
    plt: Any,
    FuncFormatter: Any,
    metric: str,
    attack_groups: list[Group],
    clean_groups: list[Group],
    title: str,
    xlabel: str,
    stem: str,
    out_dir: Path,
    formats: list[str],
    show_fliers: bool,
    dpi: int,
) -> None:
    spec = METRIC_SPECS[metric]
    attack_by_label = {group.label: group for group in attack_groups}
    clean_by_label = {group.label: group for group in clean_groups}
    labels = [group.label for group in attack_groups if group.label in clean_by_label]
    attack_values = [attack_by_label[label].values(metric) for label in labels]
    clean_values = [clean_by_label[label].values(metric) for label in labels]

    fig_width = 8.6 if len(labels) > 8 else 6.8
    fig, axis = plt.subplots(figsize=(fig_width, 4.9), constrained_layout=False)
    fig.subplots_adjust(left=0.095, right=0.985, bottom=0.33 if len(labels) > 8 else 0.21, top=0.86)

    centers = list(range(1, len(labels) + 1))
    offset = 0.18
    attack_positions = [center - offset for center in centers]
    clean_positions = [center + offset for center in centers]

    common_props = {
        "patch_artist": True,
        "showfliers": show_fliers,
        "widths": 0.30,
        "medianprops": {"color": "#222222", "linewidth": 1.25},
        "boxprops": {"linewidth": 0.85, "color": "#555555"},
        "whiskerprops": {"linewidth": 0.8, "color": "#555555"},
        "capprops": {"linewidth": 0.8, "color": "#555555"},
        "flierprops": {
            "marker": "o",
            "markersize": 2.0,
            "markerfacecolor": "#999999",
            "markeredgecolor": "#999999",
            "alpha": 0.30,
        },
    }
    attack_box = axis.boxplot(attack_values, positions=attack_positions, **common_props)
    clean_box = axis.boxplot(clean_values, positions=clean_positions, **common_props)

    attack_color = "#D55E00"
    attack_edge_color = "#8C2D04"
    clean_color = "#009E73"
    clean_edge_color = "#005A43"
    for patch in attack_box["boxes"]:
        patch.set_facecolor(attack_color)
        patch.set_edgecolor(attack_edge_color)
        patch.set_linewidth(0.95)
        patch.set_alpha(0.86)
    for patch in clean_box["boxes"]:
        patch.set_facecolor(clean_color)
        patch.set_edgecolor(clean_edge_color)
        patch.set_linewidth(0.95)
        patch.set_alpha(0.86)
    for artist in attack_box["whiskers"] + attack_box["caps"]:
        artist.set_color(attack_edge_color)
        artist.set_linewidth(0.85)
    for artist in clean_box["whiskers"] + clean_box["caps"]:
        artist.set_color(clean_edge_color)
        artist.set_linewidth(0.85)

    for position, values in zip(attack_positions, attack_values):
        med = median(values)
        axis.text(
            position,
            med,
            format_median(med, spec),
            ha="center",
            va="bottom",
            fontsize=8.0,
            fontweight="bold",
            color="#222222",
        )
    for position, values in zip(clean_positions, clean_values):
        med = median(values)
        axis.text(
            position,
            med,
            format_median(med, spec),
            ha="center",
            va="bottom",
            fontsize=8.0,
            fontweight="bold",
            color="#222222",
        )

    axis.set_xticks(centers, labels)
    axis.set_xlim(0.4, len(labels) + 0.6)
    del title
    axis.set_ylabel(spec.ylabel, fontsize=11.2, fontweight="bold")
    axis.set_xlabel(xlabel, fontsize=11.2, fontweight="bold")
    apply_metric_tick_formatter(axis, metric, FuncFormatter)
    style_axis(axis, len(labels), combined=True)

    legend_handles = [
        plt.Rectangle(
            (0, 0),
            1,
            1,
            facecolor=attack_color,
            alpha=0.86,
            edgecolor=attack_edge_color,
            label="Attack / AGS",
        ),
        plt.Rectangle(
            (0, 0),
            1,
            1,
            facecolor=clean_color,
            alpha=0.86,
            edgecolor=clean_edge_color,
            label="Clean / UGS",
        ),
    ]
    legend = axis.legend(
        handles=legend_handles,
        frameon=True,
        loc="upper center",
        bbox_to_anchor=(0.5, 1.18),
        ncol=2,
        prop={"size": 10.8, "weight": "bold"},
        handlelength=1.6,
        columnspacing=1.3,
        borderpad=0.5,
    )
    frame = legend.get_frame()
    frame.set_boxstyle("square,pad=0.35")
    frame.set_facecolor("white")
    frame.set_edgecolor("#333333")
    frame.set_linewidth(1.2)

    del show_fliers

    for suffix in formats:
        path = out_dir / f"{stem}.{suffix}"
        fig.savefig(path, dpi=dpi if suffix == "png" else None, bbox_inches="tight")
    plt.close(fig)


def build_groups_by_key(
    attack_records: list[ResourceRecord],
    clean_records: list[ResourceRecord],
) -> dict[tuple[str, str, str], list[Group]]:
    groups_by_key: dict[tuple[str, str, str], list[Group]] = {}
    for metric in PLOT_METRICS:
        for scenario in ("openclaw_models", "deepseek_v4_pro_agents"):
            groups_by_key[(metric, scenario, "attack")] = collect_groups(attack_records, scenario, metric)
            groups_by_key[(metric, scenario, "clean")] = collect_groups(clean_records, scenario, metric)
    return groups_by_key


def main() -> int:
    args = parse_args()
    formats = args.formats or ["pdf", "svg"]
    raw_roots = args.raw_root if args.raw_root is not None else DEFAULT_RAW_ROOTS
    tar_archives = args.tar_archive if args.tar_archive is not None else DEFAULT_TAR_ARCHIVES
    args.out_dir.mkdir(parents=True, exist_ok=True)
    for spec in METRIC_SPECS.values():
        (args.out_dir / spec.folder).mkdir(parents=True, exist_ok=True)

    coverage = Coverage()
    attack_rows = load_rows(args.ags_json)
    clean_rows = load_rows(args.ugs_json)
    attack_records = collect_resource_records(
        "attack",
        attack_rows,
        raw_roots,
        tar_archives,
        args.exclude_evaluation_errors,
        coverage,
    )
    clean_records = collect_resource_records(
        "clean",
        clean_rows,
        raw_roots,
        tar_archives,
        args.exclude_evaluation_errors,
        coverage,
    )
    groups_by_key = build_groups_by_key(attack_records, clean_records)

    for (metric, scenario, kind), groups in groups_by_key.items():
        if not groups:
            raise SystemExit(f"No groups found for {metric}/{scenario}/{kind}")

    summary_path = write_summary_tsv(groups_by_key, args.out_dir)
    values_path = write_values_tsv(groups_by_key, args.out_dir)
    manifest_path = write_manifest(
        args.ags_json,
        args.ugs_json,
        raw_roots,
        tar_archives,
        groups_by_key,
        coverage,
        args.show_fliers,
        args.exclude_evaluation_errors,
        formats,
        args.skip_plots,
        args.out_dir,
    )

    if not args.skip_plots:
        plt, FuncFormatter = require_matplotlib()
        configure_matplotlib(plt)
        for metric in PLOT_METRICS:
            spec = METRIC_SPECS[metric]
            metric_out_dir = args.out_dir / spec.folder
            for scenario, xlabel, scenario_title in (
                ("openclaw_models", "Model", "OpenClaw across models"),
                ("deepseek_v4_pro_agents", "Agent", "Deepseek-v4-Pro across agents"),
            ):
                attack_groups = groups_by_key[(metric, scenario, "attack")]
                clean_groups = groups_by_key[(metric, scenario, "clean")]
                plot_boxplot(
                    plt,
                    FuncFormatter,
                    metric,
                    attack_groups,
                    f"{scenario_title} — attack rollout {spec.title_name}",
                    xlabel,
                    f"rollout_resource_{spec.stem}_{scenario}_attack",
                    metric_out_dir,
                    formats,
                    args.show_fliers,
                    args.dpi,
                    "AGS/malicious rollout rows",
                )
                plot_boxplot(
                    plt,
                    FuncFormatter,
                    metric,
                    clean_groups,
                    f"{scenario_title} — clean rollout {spec.title_name}",
                    xlabel,
                    f"rollout_resource_{spec.stem}_{scenario}_clean",
                    metric_out_dir,
                    formats,
                    args.show_fliers,
                    args.dpi,
                    "UGS/clean baseline rows",
                )
                plot_combined_boxplot(
                    plt,
                    FuncFormatter,
                    metric,
                    attack_groups,
                    clean_groups,
                    f"{scenario_title} — attack vs. clean rollout {spec.title_name}",
                    xlabel,
                    f"rollout_resource_{spec.stem}_combined_{scenario}",
                    metric_out_dir,
                    formats,
                    args.show_fliers,
                    args.dpi,
                )

    output_label = "rollout resource TSVs" if args.skip_plots else "rollout resource boxplots"
    print(f"Wrote {output_label} to {args.out_dir}")
    print(f"Wrote summary TSV: {summary_path}")
    print(f"Wrote values TSV: {values_path}")
    print(f"Wrote manifest: {manifest_path}")
    print(f"Rows resolved: attack={coverage.rows_used['attack']}/{coverage.rows_seen['attack']}; clean={coverage.rows_used['clean']}/{coverage.rows_seen['clean']}")
    print(f"Rows missing: attack={coverage.rows_missing['attack']}; clean={coverage.rows_missing['clean']}")
    for kind in ("attack", "clean"):
        source_counts = ", ".join(
            f"{source}={count}" for source, count in sorted(coverage.source_counts[kind].items())
        )
        print(f"{kind} sources: {source_counts or 'none'}")
    for (metric, scenario, kind), groups in groups_by_key.items():
        print(
            f"{metric}/{scenario}/{kind}: {len(groups)} groups, "
            f"{sum(len(group.values(metric)) for group in groups)} rows"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
