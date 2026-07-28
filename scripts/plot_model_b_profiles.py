#!/usr/bin/env python3
"""Plot per-model B1-B15 inverted-AGS/UGS behavior profiles."""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from statistics import mean
from typing import Any, Iterable


B_CATEGORIES = [f"B{i}" for i in range(1, 16)]

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

MODEL_ORDER = [
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


@dataclass
class CellMetrics:
    ags_values: list[float] = field(default_factory=list)
    ags_passes: list[bool] = field(default_factory=list)
    ags_eval_errors: int = 0
    ugs_values: list[float] = field(default_factory=list)
    ugs_passes: list[bool] = field(default_factory=list)
    ugs_eval_errors: int = 0

    @property
    def ags_mean(self) -> float | None:
        return mean(self.ags_values) if self.ags_values else None

    @property
    def not_ags_mean(self) -> float | None:
        return 1.0 - self.ags_mean if self.ags_mean is not None else None

    @property
    def asr(self) -> float | None:
        return (
            mean(1.0 if passed else 0.0 for passed in self.ags_passes) if self.ags_passes else None
        )

    @property
    def ugs_mean(self) -> float | None:
        return mean(self.ugs_values) if self.ugs_values else None

    @property
    def tacc(self) -> float | None:
        return (
            mean(1.0 if passed else 0.0 for passed in self.ugs_passes) if self.ugs_passes else None
        )


@dataclass
class DatasetMetrics:
    dataset_id: str
    model_label: str
    cells: dict[str, CellMetrics] = field(
        default_factory=lambda: {category: CellMetrics() for category in B_CATEGORIES}
    )

    @property
    def overall_ags(self) -> float | None:
        values = [value for cell in self.cells.values() for value in cell.ags_values]
        return mean(values) if values else None

    @property
    def overall_not_ags(self) -> float | None:
        return 1.0 - self.overall_ags if self.overall_ags is not None else None

    @property
    def overall_ugs(self) -> float | None:
        values = [value for cell in self.cells.values() for value in cell.ugs_values]
        return mean(values) if values else None

    @property
    def overall_asr(self) -> float | None:
        values = [passed for cell in self.cells.values() for passed in cell.ags_passes]
        return mean(1.0 if passed else 0.0 for passed in values) if values else None

    @property
    def overall_tacc(self) -> float | None:
        values = [passed for cell in self.cells.values() for passed in cell.ugs_passes]
        return mean(1.0 if passed else 0.0 for passed in values) if values else None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate B1-B15 inverted-AGS/UGS bar-chart profiles per OpenClaw model."
    )
    parser.add_argument(
        "--ags-json",
        type=Path,
        required=True,
        help="Merged AGS JSON with a top-level results[] array.",
    )
    parser.add_argument(
        "--ugs-json",
        type=Path,
        required=True,
        help="Merged UGS JSON with a top-level results[] array.",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("results/figures/model_b_profiles"),
        help="Output directory for per-B TSV and profile figures.",
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
        "--include-non-openclaw",
        action="store_true",
        help="Include non-OpenClaw datasets instead of filtering to dataset IDs beginning with openclaw_.",
    )
    parser.add_argument(
        "--ugs-ymin",
        type=float,
        default=0.4,
        help="Retained for compatibility; current layouts use a shared full 0-1 score axis.",
    )
    parser.add_argument(
        "--dpi",
        type=int,
        default=300,
        help="Raster DPI for PNG outputs.",
    )
    return parser.parse_args()


def load_results(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    results = payload.get("results")
    if not isinstance(results, list):
        raise ValueError(f"{path} does not contain a top-level results[] list")
    return [row for row in results if isinstance(row, dict)]


def dataset_id(row: dict[str, Any]) -> str:
    value = row.get("score_dataset_id") or row.get("dataset_id") or row.get("dataset")
    return str(value) if value else "unknown_dataset"


def model_label_for_dataset(dataset: str, rows: Iterable[dict[str, Any]]) -> str:
    if dataset in OPENCLAW_DATASET_LABELS:
        return OPENCLAW_DATASET_LABELS[dataset]
    for row in rows:
        label = row.get("score_model_label") or row.get("model")
        if label:
            return str(label)
    return dataset


def b_category(row: dict[str, Any]) -> str | None:
    for key in ("suite", "b_category", "scoring_family"):
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
    return None


def finite_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def attack_pass(row: dict[str, Any], score: float) -> bool:
    for key in ("attack_pass", "pass"):
        value = row.get(key)
        if isinstance(value, bool):
            return value
    threshold = finite_float(row.get("attack_success_threshold"))
    if threshold is None:
        threshold = 0.8
    return score >= threshold


def utility_pass(row: dict[str, Any], score: float) -> bool:
    value = row.get("task_pass")
    if isinstance(value, bool):
        return value
    threshold = finite_float(row.get("utility_success_threshold"))
    if threshold is None:
        threshold = 0.8
    return score >= threshold


def selected_datasets(rows: Iterable[dict[str, Any]], include_non_openclaw: bool) -> set[str]:
    datasets = {dataset_id(row) for row in rows}
    if include_non_openclaw:
        return datasets
    return {dataset for dataset in datasets if dataset.startswith("openclaw_")}


def build_metrics(
    ags_rows: list[dict[str, Any]],
    ugs_rows: list[dict[str, Any]],
    include_non_openclaw: bool,
) -> dict[str, DatasetMetrics]:
    ags_datasets = selected_datasets(ags_rows, include_non_openclaw)
    ugs_datasets = selected_datasets(ugs_rows, include_non_openclaw)
    datasets = sorted(ags_datasets & ugs_datasets)
    rows_by_dataset: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in ags_rows + ugs_rows:
        rows_by_dataset[dataset_id(row)].append(row)

    metrics = {
        dataset: DatasetMetrics(dataset, model_label_for_dataset(dataset, rows_by_dataset[dataset]))
        for dataset in datasets
    }

    for row in ags_rows:
        dataset = dataset_id(row)
        if dataset not in metrics:
            continue
        category = b_category(row)
        if category not in metrics[dataset].cells:
            continue
        cell = metrics[dataset].cells[category]
        if row.get("evaluation_error"):
            cell.ags_eval_errors += 1
            continue
        score = finite_float(row.get("ags", row.get("score", row.get("attack_success"))))
        if score is None:
            cell.ags_eval_errors += 1
            continue
        cell.ags_values.append(score)
        cell.ags_passes.append(attack_pass(row, score))

    for row in ugs_rows:
        dataset = dataset_id(row)
        if dataset not in metrics:
            continue
        category = b_category(row)
        if category not in metrics[dataset].cells:
            continue
        cell = metrics[dataset].cells[category]
        if row.get("evaluation_error"):
            cell.ugs_eval_errors += 1
            continue
        score = finite_float(row.get("ugs"))
        if score is None:
            cell.ugs_eval_errors += 1
            continue
        cell.ugs_values.append(score)
        cell.ugs_passes.append(utility_pass(row, score))

    return metrics


def metric_sort_key(item: DatasetMetrics) -> tuple[int, str]:
    try:
        return (MODEL_ORDER.index(item.model_label), item.model_label)
    except ValueError:
        return (len(MODEL_ORDER), item.model_label)


def fmt(value: float | None, digits: int = 3) -> str:
    return "" if value is None else f"{value:.{digits}f}"


def write_tsv(metrics: list[DatasetMetrics], out_dir: Path) -> Path:
    out_path = out_dir / "per_b_metrics.tsv"
    with out_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "model",
                "dataset_id",
                "b_category",
                "ags_mean",
                "not_ags_mean",
                "asr",
                "ags_valid_runs",
                "ags_eval_errors",
                "ugs_mean",
                "tacc",
                "ugs_valid_rows",
                "ugs_eval_errors",
                "overall_ags",
                "overall_not_ags",
                "overall_asr",
                "overall_ugs",
                "overall_tacc",
            ],
            delimiter="\t",
        )
        writer.writeheader()
        for dataset_metrics in metrics:
            for category in B_CATEGORIES:
                cell = dataset_metrics.cells[category]
                writer.writerow(
                    {
                        "model": dataset_metrics.model_label,
                        "dataset_id": dataset_metrics.dataset_id,
                        "b_category": category,
                        "ags_mean": fmt(cell.ags_mean, 6),
                        "not_ags_mean": fmt(cell.not_ags_mean, 6),
                        "asr": fmt(cell.asr, 6),
                        "ags_valid_runs": len(cell.ags_values),
                        "ags_eval_errors": cell.ags_eval_errors,
                        "ugs_mean": fmt(cell.ugs_mean, 6),
                        "tacc": fmt(cell.tacc, 6),
                        "ugs_valid_rows": len(cell.ugs_values),
                        "ugs_eval_errors": cell.ugs_eval_errors,
                        "overall_ags": fmt(dataset_metrics.overall_ags, 6),
                        "overall_not_ags": fmt(dataset_metrics.overall_not_ags, 6),
                        "overall_asr": fmt(dataset_metrics.overall_asr, 6),
                        "overall_ugs": fmt(dataset_metrics.overall_ugs, 6),
                        "overall_tacc": fmt(dataset_metrics.overall_tacc, 6),
                    }
                )
    return out_path


def write_manifest(
    metrics: list[DatasetMetrics],
    out_dir: Path,
    ags_json: Path,
    ugs_json: Path,
    formats: list[str],
    ugs_ymin: float,
) -> Path:
    out_path = out_dir / "manifest.json"
    del ugs_ymin  # Kept for CLI compatibility; both current layouts share the full 0-1 score axis.
    payload = {
        "description": "Per-model B1-B15 inverted-AGS/UGS behavior-profile plots.",
        "ags_source": str(ags_json),
        "ugs_source": str(ugs_json),
        "b_categories": B_CATEGORIES,
        "formats": formats,
        "plotted_metrics": {
            "not_ags": "1 - AGS; plotted as ¬AGS so both bars are higher-is-better",
            "ugs": "UGS; plotted unchanged",
        },
        "layout_variants": {
            "vertical_b_axis": "B1-B15 on the y-axis, horizontal grouped bars",
            "horizontal_b_axis": "B1-B15 on the x-axis, taller landscape grouped bars with larger bold text",
        },
        "figure_dirs": {
            "vertical_b_axis": "vertical_b_axis",
            "horizontal_b_axis": "horizontal_b_axis",
        },
        "axis_limits": {"score": [0.0, 1.05]},
        "datasets": [
            {
                "model": item.model_label,
                "dataset_id": item.dataset_id,
                "overall_ags": item.overall_ags,
                "overall_not_ags": item.overall_not_ags,
                "overall_asr": item.overall_asr,
                "overall_ugs": item.overall_ugs,
                "overall_tacc": item.overall_tacc,
            }
            for item in metrics
        ],
    }
    with out_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    return out_path


def slugify(value: str) -> str:
    value = value.lower().replace("@", "_at_")
    value = re.sub(r"[^a-z0-9]+", "_", value)
    return value.strip("_")


def top_items(values: dict[str, float | None], reverse: bool) -> str:
    present = [(category, value) for category, value in values.items() if value is not None]
    if not present:
        return "n/a"
    present.sort(key=lambda item: item[1], reverse=reverse)
    return ", ".join(f"{category}={value:.2f}" for category, value in present[:3])


def require_matplotlib() -> Any:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.backends.backend_pdf import PdfPages
    except ImportError as exc:
        raise SystemExit(
            "matplotlib is required for plotting. Run with: "
            "uv run --with matplotlib python scripts/plot_model_b_profiles.py ..."
        ) from exc
    return plt, PdfPages


def configure_matplotlib(plt: Any) -> None:
    plt.rcParams.update(
        {
            "font.size": 8.5,
            "axes.labelsize": 8.5,
            "axes.titlesize": 9.0,
            "xtick.labelsize": 8.0,
            "ytick.labelsize": 8.0,
            "legend.fontsize": 7.5,
            "figure.titlesize": 11.0,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
            "svg.fonttype": "none",
        }
    )


def _profile_values(
    dataset_metrics: DatasetMetrics,
) -> tuple[dict[str, float | None], dict[str, float | None]]:
    not_ags_values = {
        category: dataset_metrics.cells[category].not_ags_mean for category in B_CATEGORIES
    }
    ugs_values = {category: dataset_metrics.cells[category].ugs_mean for category in B_CATEGORIES}
    return not_ags_values, ugs_values


def _profile_subtitle(dataset_metrics: DatasetMetrics) -> str:
    return f"Overall ¬AGS={fmt(dataset_metrics.overall_not_ags)} · Overall UGS={fmt(dataset_metrics.overall_ugs)}"


def add_profile_top_legend(
    axis: Any,
    dataset_metrics: DatasetMetrics,
    not_ags_handle: Any,
    ugs_handle: Any,
    not_ags_overall_handle: Any | None,
    ugs_overall_handle: Any | None,
    *,
    bbox_y: float,
    fontsize: float,
) -> None:
    handles: list[Any] = []
    labels: list[str] = []
    if not_ags_overall_handle is not None and dataset_metrics.overall_not_ags is not None:
        handles.append(not_ags_overall_handle)
        labels.append(rf"Overall $\neg$AGS={dataset_metrics.overall_not_ags:.3f}")
    if ugs_overall_handle is not None and dataset_metrics.overall_ugs is not None:
        handles.append(ugs_overall_handle)
        labels.append(f"Overall UGS={dataset_metrics.overall_ugs:.3f}")
    handles.extend([not_ags_handle, ugs_handle])
    labels.extend(
        [
            r"$\neg\mathrm{AGS}_{\mathrm{mal}}\uparrow$",
            r"$\mathrm{UGS}_{\mathrm{ben}}\uparrow$",
        ]
    )
    legend = axis.legend(
        handles=handles,
        labels=labels,
        frameon=True,
        loc="upper center",
        bbox_to_anchor=(0.5, bbox_y),
        ncol=len(handles),
        prop={"size": fontsize, "weight": "bold"},
        handlelength=1.4,
        columnspacing=0.9,
        labelspacing=0.4,
        borderpad=0.45,
    )
    frame = legend.get_frame()
    frame.set_boxstyle("square,pad=0.35")
    frame.set_facecolor("white")
    frame.set_edgecolor("#333333")
    frame.set_linewidth(1.2)


def _save_profile_figure(
    fig: Any,
    out_dir: Path,
    stem: str,
    formats: list[str],
    dpi: int,
    pdf_pages: Any | None,
) -> dict[str, str]:
    outputs: dict[str, str] = {}
    for suffix in formats:
        path = out_dir / f"{stem}.{suffix}"
        fig.savefig(path, dpi=dpi if suffix == "png" else None, bbox_inches="tight")
        outputs[suffix] = str(path)
    if pdf_pages is not None:
        pdf_pages.savefig(fig, bbox_inches="tight")
    return outputs


def plot_vertical_profile(
    plt: Any,
    dataset_metrics: DatasetMetrics,
    out_dir: Path,
    formats: list[str],
    dpi: int,
    pdf_pages: Any | None = None,
) -> dict[str, str]:
    not_ags_values, ugs_values = _profile_values(dataset_metrics)

    fig, axis = plt.subplots(figsize=(4.6, 7.8), constrained_layout=False)
    fig.subplots_adjust(top=0.88, bottom=0.08, left=0.16, right=0.97)

    not_ags_color = "#0072B2"
    utility_color = "#009E73"
    grid_color = "#DDDDDD"
    separator_color = "#EEEEEE"

    group_y = [len(B_CATEGORIES) - index - 1 for index in range(len(B_CATEGORIES))]
    not_ags_y = [value + 0.17 for value in group_y]
    ugs_y = [value - 0.17 for value in group_y]
    not_ags_plot_values = [
        not_ags_values[category] if not_ags_values[category] is not None else 0.0
        for category in B_CATEGORIES
    ]
    ugs_plot_values = [
        ugs_values[category] if ugs_values[category] is not None else 0.0
        for category in B_CATEGORIES
    ]

    not_ags_bars = axis.barh(
        not_ags_y,
        not_ags_plot_values,
        height=0.26,
        color=not_ags_color,
        edgecolor="#004C78",
        linewidth=0.35,
        label=r"$\neg\mathrm{AGS}_{\mathrm{mal}}\uparrow$",
    )
    ugs_bars = axis.barh(
        ugs_y,
        ugs_plot_values,
        height=0.26,
        color=utility_color,
        edgecolor="#005A43",
        linewidth=0.35,
        label=r"$\mathrm{UGS}_{\mathrm{ben}}\uparrow$",
    )

    for y in [value - 0.5 for value in group_y[:-1]]:
        axis.axhline(y, color=separator_color, linewidth=0.6, zorder=0)
    not_ags_overall_line = None
    ugs_overall_line = None
    if dataset_metrics.overall_not_ags is not None:
        not_ags_overall_line = axis.axvline(
            dataset_metrics.overall_not_ags,
            color="#004C78",
            linestyle="--",
            linewidth=0.9,
            alpha=0.85,
            label=rf"overall $\neg$AGS {dataset_metrics.overall_not_ags:.3f}",
        )
    if dataset_metrics.overall_ugs is not None:
        ugs_overall_line = axis.axvline(
            dataset_metrics.overall_ugs,
            color="#005A43",
            linestyle="--",
            linewidth=0.9,
            alpha=0.85,
            label=f"overall UGS {dataset_metrics.overall_ugs:.3f}",
        )

    for y, value in zip(not_ags_y, not_ags_plot_values):
        axis.text(
            min(value + 0.018, 0.985),
            y,
            f"{value:.2f}",
            va="center",
            ha="left",
            fontsize=6.7,
            color="#333333",
        )
    for y, value in zip(ugs_y, ugs_plot_values):
        axis.text(
            min(value + 0.018, 0.985),
            y,
            f"{value:.2f}",
            va="center",
            ha="left",
            fontsize=6.7,
            color="#333333",
        )

    axis.set_yticks(group_y, B_CATEGORIES)
    axis.set_ylim(-0.75, len(B_CATEGORIES) - 0.25)
    axis.set_xlim(0.0, 1.05)
    axis.set_xlabel("Score (higher is better)")
    axis.set_ylabel("Behavior risk category")
    axis.grid(axis="x", color=grid_color, linewidth=0.6)
    axis.set_axisbelow(True)
    axis.spines["top"].set_visible(False)
    axis.spines["right"].set_visible(False)
    add_profile_top_legend(
        axis=axis,
        dataset_metrics=dataset_metrics,
        not_ags_handle=not_ags_bars,
        ugs_handle=ugs_bars,
        not_ags_overall_handle=not_ags_overall_line,
        ugs_overall_handle=ugs_overall_line,
        bbox_y=1.11,
        fontsize=7.4,
    )

    outputs = _save_profile_figure(
        fig=fig,
        out_dir=out_dir,
        stem=f"{slugify(dataset_metrics.model_label)}_b_profile_vertical",
        formats=formats,
        dpi=dpi,
        pdf_pages=pdf_pages,
    )
    plt.close(fig)
    return outputs


def plot_horizontal_profile(
    plt: Any,
    dataset_metrics: DatasetMetrics,
    out_dir: Path,
    formats: list[str],
    dpi: int,
    pdf_pages: Any | None = None,
) -> dict[str, str]:
    not_ags_values, ugs_values = _profile_values(dataset_metrics)

    fig, axis = plt.subplots(figsize=(7.4, 3.75), constrained_layout=False)
    fig.subplots_adjust(top=0.84, bottom=0.16, left=0.085, right=0.99)

    not_ags_color = "#0072B2"
    utility_color = "#009E73"
    grid_color = "#DDDDDD"
    separator_color = "#EEEEEE"

    positions = list(range(len(B_CATEGORIES)))
    bar_width = 0.34
    not_ags_plot_values = [
        not_ags_values[category] if not_ags_values[category] is not None else 0.0
        for category in B_CATEGORIES
    ]
    ugs_plot_values = [
        ugs_values[category] if ugs_values[category] is not None else 0.0
        for category in B_CATEGORIES
    ]

    not_ags_bars = axis.bar(
        [position - bar_width / 2 for position in positions],
        not_ags_plot_values,
        width=bar_width,
        color=not_ags_color,
        edgecolor="#004C78",
        linewidth=0.3,
        label=r"$\neg\mathrm{AGS}_{\mathrm{mal}}\uparrow$",
    )
    ugs_bars = axis.bar(
        [position + bar_width / 2 for position in positions],
        ugs_plot_values,
        width=bar_width,
        color=utility_color,
        edgecolor="#005A43",
        linewidth=0.3,
        label=r"$\mathrm{UGS}_{\mathrm{ben}}\uparrow$",
    )

    for x in [position + 0.5 for position in positions[:-1]]:
        axis.axvline(x, color=separator_color, linewidth=0.45, zorder=0)
    not_ags_overall_line = None
    ugs_overall_line = None
    if dataset_metrics.overall_not_ags is not None:
        not_ags_overall_line = axis.axhline(
            dataset_metrics.overall_not_ags,
            color="#004C78",
            linestyle="--",
            linewidth=0.8,
            alpha=0.85,
            label=rf"overall $\neg$AGS {dataset_metrics.overall_not_ags:.3f}",
        )
    if dataset_metrics.overall_ugs is not None:
        ugs_overall_line = axis.axhline(
            dataset_metrics.overall_ugs,
            color="#005A43",
            linestyle="--",
            linewidth=0.8,
            alpha=0.85,
            label=f"overall UGS {dataset_metrics.overall_ugs:.3f}",
        )

    axis.set_xticks(positions, B_CATEGORIES)
    axis.set_xlim(-0.65, len(B_CATEGORIES) - 0.35)
    axis.set_ylim(0.0, 1.05)
    axis.set_xlabel("Behavior risk category", fontsize=10.5, fontweight="bold")
    axis.set_ylabel("Score", fontsize=10.5, fontweight="bold")
    axis.tick_params(axis="both", labelsize=9.4)
    for tick_label in axis.get_xticklabels() + axis.get_yticklabels():
        tick_label.set_fontweight("bold")
    axis.grid(axis="y", color=grid_color, linewidth=0.55)
    axis.set_axisbelow(True)
    axis.spines["top"].set_visible(False)
    axis.spines["right"].set_visible(False)
    add_profile_top_legend(
        axis=axis,
        dataset_metrics=dataset_metrics,
        not_ags_handle=not_ags_bars,
        ugs_handle=ugs_bars,
        not_ags_overall_handle=not_ags_overall_line,
        ugs_overall_handle=ugs_overall_line,
        bbox_y=1.17,
        fontsize=8.6,
    )

    outputs = _save_profile_figure(
        fig=fig,
        out_dir=out_dir,
        stem=f"{slugify(dataset_metrics.model_label)}_b_profile_horizontal",
        formats=formats,
        dpi=dpi,
        pdf_pages=pdf_pages,
    )
    plt.close(fig)
    return outputs


def main() -> int:
    args = parse_args()
    formats = args.formats or ["pdf", "svg"]
    args.out_dir.mkdir(parents=True, exist_ok=True)

    ags_rows = load_results(args.ags_json)
    ugs_rows = load_results(args.ugs_json)
    metrics_by_dataset = build_metrics(
        ags_rows=ags_rows,
        ugs_rows=ugs_rows,
        include_non_openclaw=args.include_non_openclaw,
    )
    metrics = sorted(metrics_by_dataset.values(), key=metric_sort_key)
    if not metrics:
        raise SystemExit("No matching datasets found in the AGS/UGS inputs.")

    tsv_path = write_tsv(metrics, args.out_dir)
    manifest_path = write_manifest(
        metrics, args.out_dir, args.ags_json, args.ugs_json, formats, args.ugs_ymin
    )

    plt, PdfPages = require_matplotlib()
    configure_matplotlib(plt)
    vertical_dir = args.out_dir / "vertical_b_axis"
    horizontal_dir = args.out_dir / "horizontal_b_axis"
    vertical_dir.mkdir(parents=True, exist_ok=True)
    horizontal_dir.mkdir(parents=True, exist_ok=True)

    vertical_multi_pdf_path = vertical_dir / "all_model_b_profiles_vertical.pdf"
    horizontal_multi_pdf_path = horizontal_dir / "all_model_b_profiles_horizontal.pdf"
    figure_count = 0
    with (
        PdfPages(vertical_multi_pdf_path) as vertical_pdf_pages,
        PdfPages(horizontal_multi_pdf_path) as horizontal_pdf_pages,
    ):
        for dataset_metrics in metrics:
            plot_vertical_profile(
                plt=plt,
                dataset_metrics=dataset_metrics,
                out_dir=vertical_dir,
                formats=formats,
                dpi=args.dpi,
                pdf_pages=vertical_pdf_pages,
            )
            plot_horizontal_profile(
                plt=plt,
                dataset_metrics=dataset_metrics,
                out_dir=horizontal_dir,
                formats=formats,
                dpi=args.dpi,
                pdf_pages=horizontal_pdf_pages,
            )
            figure_count += 1

    print(f"Wrote {figure_count} vertical model profiles to {vertical_dir}")
    print(f"Wrote {figure_count} horizontal model profiles to {horizontal_dir}")
    print(f"Wrote TSV: {tsv_path}")
    print(f"Wrote manifest: {manifest_path}")
    print(f"Wrote vertical multi-page PDF: {vertical_multi_pdf_path}")
    print(f"Wrote horizontal multi-page PDF: {horizontal_multi_pdf_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
