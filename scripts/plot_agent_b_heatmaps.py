#!/usr/bin/env python3
"""Plot Deepseek-v4-Pro agent-by-behavior-risk-category AGS/UGS heatmaps."""

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

DEEPSEEK_AGENT_DATASET_LABELS = {
    "openclaw_deepseek_v4_pro_trajectories_20260713_runs3": "OpenClaw",
    "openagent_deepseek_v4_pro_trajectories_20260717_runs3_merged": "OpenAgent",
    "claudecode_deepseek_deepseek_v4_pro_trajectories_20260720_runs2-3_parallel_fixedenv": "ClaudeCode",
    "hermes_deepseek_deepseek_v4_pro_trajectories_20260718_runs3_parallel": "Hermes",
    "opencode_deepseek_deepseek_v4_pro_trajectories_20260716_runs3_parallel": "OpenCode",
    "qwenpaw_deepseek_deepseek_v4_pro_trajectories_20260717_runs3_sequential": "QwenPaw",
}

BACKEND_LABELS = {
    "openclaw": "OpenClaw",
    "openagent": "OpenAgent",
    "claudecode": "ClaudeCode",
    "hermes": "Hermes",
    "opencode": "OpenCode",
    "qwenpaw": "QwenPaw",
}

AGENT_ORDER = ["OpenClaw", "OpenAgent", "ClaudeCode", "Hermes", "OpenCode", "QwenPaw"]
MODEL_LABEL = "Deepseek-v4-Pro"
TEXT_COLOR = "#333333"
MISSING_COLOR = "#F2F2F2"
GRID_COLOR = "#FFFFFF"
HEATMAP_COLOR_LIMITS = {
    "AGS": (0.0, 1.0),
    "UGS": (0.7, 1.0),
}


@dataclass
class CellMetrics:
    ags_values: list[float] = field(default_factory=list)
    ags_eval_errors: int = 0
    ugs_values: list[float] = field(default_factory=list)
    ugs_eval_errors: int = 0

    @property
    def ags_mean(self) -> float | None:
        return mean(self.ags_values) if self.ags_values else None

    @property
    def ugs_mean(self) -> float | None:
        return mean(self.ugs_values) if self.ugs_values else None


@dataclass
class AgentMetrics:
    dataset_id: str
    agent_label: str
    cells: dict[str, CellMetrics] = field(
        default_factory=lambda: {category: CellMetrics() for category in B_CATEGORIES}
    )

    @property
    def overall_ags(self) -> float | None:
        values = [value for cell in self.cells.values() for value in cell.ags_values]
        return mean(values) if values else None

    @property
    def overall_ugs(self) -> float | None:
        values = [value for cell in self.cells.values() for value in cell.ugs_values]
        return mean(values) if values else None


@dataclass(frozen=True)
class LayoutFigureOutputs:
    ags: dict[str, str]
    ugs: dict[str, str]
    combined: dict[str, str]


@dataclass(frozen=True)
class FigureOutputs:
    vertical_b_axis: LayoutFigureOutputs
    horizontal_b_axis: LayoutFigureOutputs


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate Deepseek-v4-Pro AGS/UGS heatmaps by agent backend and behavior risk category."
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
        default=Path("results/figures/agent_b_heatmaps"),
        help="Output directory for heatmap figures, TSV, and manifest.",
    )
    parser.add_argument(
        "--format",
        dest="formats",
        action="append",
        choices=("pdf", "png", "svg"),
        default=None,
        help="Figure format to write. May be repeated. Defaults to pdf and svg.",
    )
    parser.add_argument("--dpi", type=int, default=300, help="Raster DPI for PNG outputs.")
    parser.add_argument(
        "--skip-plots",
        action="store_true",
        help="Only write TSV/manifest outputs; do not import matplotlib or render figures.",
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


def finite_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


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


def is_deepseek_v4_pro_row(row: dict[str, Any]) -> bool:
    dataset = dataset_id(row)
    if dataset in DEEPSEEK_AGENT_DATASET_LABELS:
        return True
    values = [dataset, str(row.get("model") or ""), str(row.get("score_model_label") or "")]
    normalized = " ".join(values).lower().replace("_", "-")
    return "deepseek" in normalized and "v4-pro" in normalized


def most_common(values: list[str]) -> str | None:
    if not values:
        return None
    counts: dict[str, int] = defaultdict(int)
    for value in values:
        counts[value] += 1
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0][0]


def agent_label_for_dataset(dataset: str, rows: Iterable[dict[str, Any]]) -> str:
    if dataset in DEEPSEEK_AGENT_DATASET_LABELS:
        return DEEPSEEK_AGENT_DATASET_LABELS[dataset]
    backends = [str(row.get("backend")) for row in rows if row.get("backend")]
    backend = most_common(backends)
    if backend in BACKEND_LABELS:
        return BACKEND_LABELS[backend]
    if backend:
        return backend.replace("_", " ").title().replace(" ", "")
    return dataset


def selected_deepseek_datasets(rows: Iterable[dict[str, Any]]) -> set[str]:
    return {dataset_id(row) for row in rows if is_deepseek_v4_pro_row(row)}


def build_metrics(ags_rows: list[dict[str, Any]], ugs_rows: list[dict[str, Any]]) -> dict[str, AgentMetrics]:
    ags_datasets = selected_deepseek_datasets(ags_rows)
    ugs_datasets = selected_deepseek_datasets(ugs_rows)
    datasets = sorted(ags_datasets & ugs_datasets)

    rows_by_dataset: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in ags_rows + ugs_rows:
        rows_by_dataset[dataset_id(row)].append(row)

    metrics = {
        dataset: AgentMetrics(dataset, agent_label_for_dataset(dataset, rows_by_dataset[dataset]))
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

    return metrics


def agent_sort_key(item: AgentMetrics) -> tuple[int, str]:
    try:
        return (AGENT_ORDER.index(item.agent_label), item.agent_label)
    except ValueError:
        return (len(AGENT_ORDER), item.agent_label)


def fmt(value: float | None, digits: int = 3) -> str:
    return "" if value is None else f"{value:.{digits}f}"


def write_tsv(metrics: list[AgentMetrics], out_dir: Path) -> Path:
    path = out_dir / "deepseek_v4_pro_agent_b_metrics.tsv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "agent",
                "model",
                "dataset_id",
                "b_category",
                "ags_mean",
                "ags_valid_runs",
                "ags_eval_errors",
                "ugs_mean",
                "ugs_valid_rows",
                "ugs_eval_errors",
                "overall_ags",
                "overall_ugs",
            ],
            delimiter="\t",
        )
        writer.writeheader()
        for agent_metrics in metrics:
            for category in B_CATEGORIES:
                cell = agent_metrics.cells[category]
                writer.writerow(
                    {
                        "agent": agent_metrics.agent_label,
                        "model": MODEL_LABEL,
                        "dataset_id": agent_metrics.dataset_id,
                        "b_category": category,
                        "ags_mean": fmt(cell.ags_mean, 6),
                        "ags_valid_runs": len(cell.ags_values),
                        "ags_eval_errors": cell.ags_eval_errors,
                        "ugs_mean": fmt(cell.ugs_mean, 6),
                        "ugs_valid_rows": len(cell.ugs_values),
                        "ugs_eval_errors": cell.ugs_eval_errors,
                        "overall_ags": fmt(agent_metrics.overall_ags, 6),
                        "overall_ugs": fmt(agent_metrics.overall_ugs, 6),
                    }
                )
    return path


def write_manifest(
    metrics: list[AgentMetrics],
    out_dir: Path,
    ags_json: Path,
    ugs_json: Path,
    formats: list[str],
    skip_plots: bool,
    figures: FigureOutputs | None,
) -> Path:
    path = out_dir / "manifest.json"
    payload = {
        "description": "Deepseek-v4-Pro agent-by-behavior-risk-category heatmaps for AGS and UGS.",
        "ags_source": str(ags_json),
        "ugs_source": str(ugs_json),
        "model": MODEL_LABEL,
        "b_categories": B_CATEGORIES,
        "agent_order": [item.agent_label for item in metrics],
        "horizontal_agent_codes": [
            {"code": f"A{index + 1}", "agent": item.agent_label, "dataset_id": item.dataset_id}
            for index, item in enumerate(metrics)
        ],
        "formats": formats,
        "plots_written": not skip_plots,
        "plotted_metrics": {
            "ags": "AGS plotted unchanged on a 0.0-1.0 color scale; higher means stronger attack success.",
            "ugs": "UGS values are unchanged, but the heatmap color scale starts at 0.7 to show high-utility differences more clearly; higher means stronger clean-task utility.",
        },
        "layout_variants": {
            "vertical_b_axis": {
                "x_axis": "agent backend",
                "y_axis": "B1-B15 behavior risk category",
                "panel_arrangement": "AGS and UGS side by side in the combined figure",
            },
            "horizontal_b_axis": {
                "x_axis": "B1-B15 behavior risk category",
                "y_axis": "agent backend",
                "panel_arrangement": "AGS above UGS in the combined figure",
            },
        },
        "figure_dirs": {
            "vertical_b_axis": "vertical_b_axis",
            "horizontal_b_axis": "horizontal_b_axis",
        },
        "cell_annotations": "mean score rounded to two decimals",
        "color_scale": {
            metric.lower(): [vmin, vmax]
            for metric, (vmin, vmax) in HEATMAP_COLOR_LIMITS.items()
        },
        "figures": None
        if figures is None
        else {
            "vertical_b_axis": {
                "ags": figures.vertical_b_axis.ags,
                "ugs": figures.vertical_b_axis.ugs,
                "combined": figures.vertical_b_axis.combined,
            },
            "horizontal_b_axis": {
                "ags": figures.horizontal_b_axis.ags,
                "ugs": figures.horizontal_b_axis.ugs,
                "combined": figures.horizontal_b_axis.combined,
            },
        },
        "datasets": [
            {
                "agent": item.agent_label,
                "dataset_id": item.dataset_id,
                "overall_ags": item.overall_ags,
                "overall_ugs": item.overall_ugs,
            }
            for item in metrics
        ],
    }
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    return path


def matrix_for_metric(metrics: list[AgentMetrics], metric: str) -> list[list[float]]:
    matrix: list[list[float]] = []
    for category in B_CATEGORIES:
        row_values: list[float] = []
        for agent_metrics in metrics:
            cell = agent_metrics.cells[category]
            value = cell.ags_mean if metric == "AGS" else cell.ugs_mean
            row_values.append(value if value is not None else math.nan)
        matrix.append(row_values)
    return matrix


def horizontal_matrix_for_metric(metrics: list[AgentMetrics], metric: str) -> list[list[float]]:
    matrix: list[list[float]] = []
    for agent_metrics in metrics:
        row_values: list[float] = []
        for category in B_CATEGORIES:
            cell = agent_metrics.cells[category]
            value = cell.ags_mean if metric == "AGS" else cell.ugs_mean
            row_values.append(value if value is not None else math.nan)
        matrix.append(row_values)
    return matrix


def require_matplotlib() -> tuple[Any, Any]:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.colors import LinearSegmentedColormap
    except ImportError as exc:
        raise SystemExit(
            "matplotlib is required for plotting. Run with: "
            "uv run --with matplotlib python scripts/plot_agent_b_heatmaps.py ..."
        ) from exc
    return plt, LinearSegmentedColormap


def configure_matplotlib(plt: Any) -> None:
    plt.rcParams.update(
        {
            "font.size": 11.8,
            "axes.labelsize": 13.2,
            "axes.titlesize": 15.0,
            "xtick.labelsize": 10.8,
            "ytick.labelsize": 11.0,
            "figure.titlesize": 15.0,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
            "svg.fonttype": "none",
        }
    )


def heatmap_cmap(LinearSegmentedColormap: Any, metric: str) -> Any:
    if metric == "AGS":
        colors = ["#FFF7EC", "#FDD49E", "#FC8D59", "#D7301F", "#7F0000"]
    else:
        colors = ["#F7FCF5", "#C7E9C0", "#74C476", "#238B45", "#00441B"]
    cmap = LinearSegmentedColormap.from_list(f"actbench_{metric.lower()}_heatmap", colors)
    cmap.set_bad(MISSING_COLOR)
    return cmap


def heatmap_color_limits(metric: str) -> tuple[float, float]:
    return HEATMAP_COLOR_LIMITS[metric]


def annotation_text_color(value: float, metric: str) -> str:
    vmin, vmax = heatmap_color_limits(metric)
    normalized = (value - vmin) / (vmax - vmin)
    return "white" if normalized >= 0.58 else TEXT_COLOR


def annotate_heatmap(
    axis: Any,
    matrix: list[list[float]],
    metric: str,
    *,
    fontsize: float = 9.7,
) -> None:
    for y_index, row in enumerate(matrix):
        for x_index, value in enumerate(row):
            if not math.isfinite(value):
                label = "—"
                color = "#777777"
            else:
                label = f"{value:.2f}"
                color = annotation_text_color(value, metric)
            axis.text(
                x_index,
                y_index,
                label,
                ha="center",
                va="center",
                color=color,
                fontsize=fontsize,
                fontweight="bold",
            )


def style_heatmap_axis(
    axis: Any,
    metrics: list[AgentMetrics],
    *,
    show_y_label: bool,
    title: str,
) -> None:
    agent_labels = [item.agent_label for item in metrics]
    axis.set_xticks(range(len(agent_labels)), agent_labels)
    axis.set_yticks(range(len(B_CATEGORIES)), B_CATEGORIES)
    axis.xaxis.tick_top()
    axis.xaxis.set_label_position("top")
    axis.set_xlabel("")
    axis.set_ylabel("Behavior risk category" if show_y_label else "", fontweight="bold", fontsize=13.2)
    axis.set_title(title, pad=28, fontweight="bold", fontsize=17.0)
    axis.tick_params(axis="x", rotation=34, length=0, pad=3, labelsize=11.0)
    axis.tick_params(axis="y", length=0, labelsize=11.0)
    for tick_label in axis.get_xticklabels() + axis.get_yticklabels():
        tick_label.set_fontweight("bold")
    axis.set_xticks([index - 0.5 for index in range(len(agent_labels) + 1)], minor=True)
    axis.set_yticks([index - 0.5 for index in range(len(B_CATEGORIES) + 1)], minor=True)
    axis.grid(which="minor", color=GRID_COLOR, linewidth=1.1)
    axis.tick_params(which="minor", bottom=False, left=False, top=False)
    for spine in axis.spines.values():
        spine.set_visible(False)


def horizontal_agent_code_labels(metrics: list[AgentMetrics]) -> list[str]:
    return [f"A{index + 1}" for index, _item in enumerate(metrics)]


def horizontal_agent_code_legend(metrics: list[AgentMetrics]) -> str:
    entries = [f"A{index + 1}: {item.agent_label}" for index, item in enumerate(metrics)]
    return "  ·  ".join(entries[:3]) + "\n" + "  ·  ".join(entries[3:])


def add_horizontal_agent_code_legend(fig: Any, metrics: list[AgentMetrics]) -> None:
    fig.text(
        0.532,
        0.975,
        horizontal_agent_code_legend(metrics),
        ha="center",
        va="top",
        fontsize=16.2,
        fontweight="bold",
        color=TEXT_COLOR,
        linespacing=1.25,
        bbox={
            "boxstyle": "square,pad=0.36",
            "facecolor": "white",
            "edgecolor": TEXT_COLOR,
            "linewidth": 1.9,
        },
    )


def style_horizontal_heatmap_axis(
    axis: Any,
    metrics: list[AgentMetrics],
    *,
    title: str,
) -> None:
    agent_labels = horizontal_agent_code_labels(metrics)
    axis.set_xticks(range(len(B_CATEGORIES)), B_CATEGORIES)
    axis.set_yticks(range(len(agent_labels)), agent_labels)
    axis.set_xlabel("Behavior risk category", labelpad=6, fontweight="bold", fontsize=14.5)
    axis.set_ylabel("")
    axis.set_title(title, loc="left", pad=8, fontweight="bold", fontsize=18.0)
    axis.tick_params(axis="x", rotation=0, length=0, pad=4, labelsize=12.2, labelbottom=True)
    axis.tick_params(axis="y", length=0, labelsize=12.2)
    for tick_label in axis.get_xticklabels() + axis.get_yticklabels():
        tick_label.set_fontweight("bold")
    axis.set_xticks([index - 0.5 for index in range(len(B_CATEGORIES) + 1)], minor=True)
    axis.set_yticks([index - 0.5 for index in range(len(agent_labels) + 1)], minor=True)
    axis.grid(which="minor", color=GRID_COLOR, linewidth=1.1)
    axis.tick_params(which="minor", bottom=False, left=False)
    for spine in axis.spines.values():
        spine.set_visible(False)


def save_figure(fig: Any, out_dir: Path, stem: str, formats: list[str], dpi: int) -> dict[str, str]:
    outputs: dict[str, str] = {}
    for suffix in formats:
        path = out_dir / f"{stem}.{suffix}"
        fig.savefig(path, dpi=dpi if suffix == "png" else None, bbox_inches="tight")
        outputs[suffix] = str(path)
    return outputs


def plot_single_heatmap(
    plt: Any,
    LinearSegmentedColormap: Any,
    metrics: list[AgentMetrics],
    metric: str,
    out_dir: Path,
    formats: list[str],
    dpi: int,
) -> dict[str, str]:
    matrix = matrix_for_metric(metrics, metric)
    fig, axis = plt.subplots(figsize=(5.9, 7.8), constrained_layout=False)
    fig.subplots_adjust(left=0.14, right=0.97, bottom=0.06, top=0.80)
    image = axis.imshow(
        matrix,
        aspect="auto",
        interpolation="nearest",
        cmap=heatmap_cmap(LinearSegmentedColormap, metric),
        vmin=heatmap_color_limits(metric)[0],
        vmax=heatmap_color_limits(metric)[1],
    )
    style_heatmap_axis(axis, metrics, show_y_label=True, title=metric)
    annotate_heatmap(axis, matrix, metric)
    outputs = save_figure(
        fig, out_dir, f"deepseek_v4_pro_agent_b_heatmap_{metric.lower()}", formats, dpi
    )
    plt.close(fig)
    return outputs


def plot_combined_heatmaps(
    plt: Any,
    LinearSegmentedColormap: Any,
    metrics: list[AgentMetrics],
    out_dir: Path,
    formats: list[str],
    dpi: int,
) -> dict[str, str]:
    fig, axes = plt.subplots(1, 2, figsize=(10.8, 7.8), constrained_layout=False, sharey=True)
    fig.subplots_adjust(left=0.075, right=0.985, bottom=0.06, top=0.80, wspace=0.18)

    for axis, metric, title in zip(axes, ("AGS", "UGS"), ("(a) AGS", "(b) UGS")):
        matrix = matrix_for_metric(metrics, metric)
        image = axis.imshow(
            matrix,
            aspect="auto",
            interpolation="nearest",
            cmap=heatmap_cmap(LinearSegmentedColormap, metric),
            vmin=heatmap_color_limits(metric)[0],
            vmax=heatmap_color_limits(metric)[1],
        )
        style_heatmap_axis(axis, metrics, show_y_label=axis is axes[0], title=title)
        annotate_heatmap(axis, matrix, metric)

    outputs = save_figure(fig, out_dir, "deepseek_v4_pro_agent_b_heatmaps", formats, dpi)
    plt.close(fig)
    return outputs


def plot_horizontal_single_heatmap(
    plt: Any,
    LinearSegmentedColormap: Any,
    metrics: list[AgentMetrics],
    metric: str,
    out_dir: Path,
    formats: list[str],
    dpi: int,
) -> dict[str, str]:
    matrix = horizontal_matrix_for_metric(metrics, metric)
    fig, axis = plt.subplots(figsize=(11.8, 5.5), constrained_layout=False)
    fig.subplots_adjust(left=0.08, right=0.985, bottom=0.12, top=0.80)
    add_horizontal_agent_code_legend(fig, metrics)
    image = axis.imshow(
        matrix,
        aspect="auto",
        interpolation="nearest",
        cmap=heatmap_cmap(LinearSegmentedColormap, metric),
        vmin=heatmap_color_limits(metric)[0],
        vmax=heatmap_color_limits(metric)[1],
    )
    style_horizontal_heatmap_axis(axis, metrics, title=metric)
    annotate_heatmap(axis, matrix, metric, fontsize=10.7)
    outputs = save_figure(
        fig, out_dir, f"deepseek_v4_pro_agent_b_heatmap_{metric.lower()}", formats, dpi
    )
    plt.close(fig)
    return outputs


def plot_horizontal_combined_heatmaps(
    plt: Any,
    LinearSegmentedColormap: Any,
    metrics: list[AgentMetrics],
    out_dir: Path,
    formats: list[str],
    dpi: int,
) -> dict[str, str]:
    fig, axes = plt.subplots(2, 1, figsize=(11.8, 9.8), constrained_layout=False, sharex=True)
    fig.subplots_adjust(left=0.08, right=0.985, bottom=0.06, top=0.865, hspace=0.38)
    add_horizontal_agent_code_legend(fig, metrics)

    for axis, metric, title in zip(axes, ("AGS", "UGS"), ("(a) AGS", "(b) UGS")):
        matrix = horizontal_matrix_for_metric(metrics, metric)
        image = axis.imshow(
            matrix,
            aspect="auto",
            interpolation="nearest",
            cmap=heatmap_cmap(LinearSegmentedColormap, metric),
            vmin=heatmap_color_limits(metric)[0],
            vmax=heatmap_color_limits(metric)[1],
        )
        style_horizontal_heatmap_axis(axis, metrics, title=title)
        annotate_heatmap(axis, matrix, metric, fontsize=10.7)

    outputs = save_figure(fig, out_dir, "deepseek_v4_pro_agent_b_heatmaps", formats, dpi)
    plt.close(fig)
    return outputs


def remove_stale_root_figures(out_dir: Path) -> None:
    generated_stems = {
        "deepseek_v4_pro_agent_b_heatmap_ags",
        "deepseek_v4_pro_agent_b_heatmap_ugs",
        "deepseek_v4_pro_agent_b_heatmaps",
    }
    generated_suffixes = {".pdf", ".png", ".svg"}
    for path in out_dir.iterdir():
        if path.is_file() and path.stem in generated_stems and path.suffix in generated_suffixes:
            path.unlink()


def main() -> int:
    args = parse_args()
    formats = args.formats or ["pdf", "svg"]
    args.out_dir.mkdir(parents=True, exist_ok=True)
    vertical_dir = args.out_dir / "vertical_b_axis"
    horizontal_dir = args.out_dir / "horizontal_b_axis"
    if not args.skip_plots:
        vertical_dir.mkdir(parents=True, exist_ok=True)
        horizontal_dir.mkdir(parents=True, exist_ok=True)
        remove_stale_root_figures(args.out_dir)

    ags_rows = load_results(args.ags_json)
    ugs_rows = load_results(args.ugs_json)
    metrics = sorted(build_metrics(ags_rows, ugs_rows).values(), key=agent_sort_key)
    if not metrics:
        raise SystemExit("No paired Deepseek-v4-Pro AGS/UGS datasets found.")

    tsv_path = write_tsv(metrics, args.out_dir)
    figures = None
    if not args.skip_plots:
        plt, LinearSegmentedColormap = require_matplotlib()
        configure_matplotlib(plt)
        ags_outputs = plot_single_heatmap(
            plt, LinearSegmentedColormap, metrics, "AGS", vertical_dir, formats, args.dpi
        )
        ugs_outputs = plot_single_heatmap(
            plt, LinearSegmentedColormap, metrics, "UGS", vertical_dir, formats, args.dpi
        )
        vertical_combined_outputs = plot_combined_heatmaps(
            plt, LinearSegmentedColormap, metrics, vertical_dir, formats, args.dpi
        )
        horizontal_ags_outputs = plot_horizontal_single_heatmap(
            plt, LinearSegmentedColormap, metrics, "AGS", horizontal_dir, formats, args.dpi
        )
        horizontal_ugs_outputs = plot_horizontal_single_heatmap(
            plt, LinearSegmentedColormap, metrics, "UGS", horizontal_dir, formats, args.dpi
        )
        horizontal_combined_outputs = plot_horizontal_combined_heatmaps(
            plt, LinearSegmentedColormap, metrics, horizontal_dir, formats, args.dpi
        )
        figures = FigureOutputs(
            vertical_b_axis=LayoutFigureOutputs(
                ags=ags_outputs,
                ugs=ugs_outputs,
                combined=vertical_combined_outputs,
            ),
            horizontal_b_axis=LayoutFigureOutputs(
                ags=horizontal_ags_outputs,
                ugs=horizontal_ugs_outputs,
                combined=horizontal_combined_outputs,
            ),
        )
    manifest_path = write_manifest(
        metrics, args.out_dir, args.ags_json, args.ugs_json, formats, args.skip_plots, figures
    )

    print(f"Wrote Deepseek-v4-Pro agent/B heatmap outputs to {args.out_dir}")
    print(f"Wrote metrics TSV: {tsv_path}")
    print(f"Wrote manifest: {manifest_path}")
    print("Agents: " + ", ".join(item.agent_label for item in metrics))
    print(
        "Overall AGS/UGS: "
        + "; ".join(
            f"{item.agent_label}={fmt(item.overall_ags)}/{fmt(item.overall_ugs)}"
            for item in metrics
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
