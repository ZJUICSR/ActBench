#!/usr/bin/env python3
"""Plot attack and clean iteration-count boxplots for ActBench paper figures."""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
from pathlib import Path
from statistics import mean, median
from typing import Any


OPENCLAW_DATASET_LABELS = {
    "openclaw_openrouter_anthropic_claude_opus_4_8_trajectories_20260718_runs3_parallel": "Claude-Opus-4.8",
    "openclaw_openrouter_anthropic_claude_sonnet_4_6_trajectories_20260715_runs3_parallel": "Claude-Sonnet-4.6",
    "openclaw_private_gpt-5.5_trajectories_20260715_runs3_parallel": "GPT-5.5",
    "openclaw_private_gpt-5.4-mini_trajectories_20260714_runs3_parallel": "GPT-5.4-mini",
    "openclaw_private_grok-4.5_trajectories_20260727_runs3_parallel": "Grok-4.5",
    "openclaw_gateway-glm-5-2_trajectories_20260714_runs3_parallel": "GLM-5.2",
    "openclaw_gateway_qwen3_7_max_trajectories_20260714_215927_runs3_parallel": "Qwen-3.7-max",
    "openclaw_gateway_qwen3_7_plus_trajectories_20260714_runs3_parallel": "Qwen-3.7-plus",
    "openclaw_moonshot_kimi_k3_trajectories_20260726_runs3_parallel": "Kimi-K3",
    "openclaw_gateway_kimi_k2_6_trajectories_20260715_runs3_parallel": "Kimi-K2.6",
    "openclaw_minimax_minimax-m3_trajectories_20260716_runs3_parallel": "MiniMax-M3",
    "openclaw_minimax_minimax_m2_7_trajectories_20260720_runs3_parallel": "MiniMax-M2.7",
    "openclaw_deepseek_v4_pro_trajectories_20260713_runs3": "Deepseek-v4-Pro",
    "openclaw_deepseek_v4_flash_trajectories_20260714_runs3_parallel": "Deepseek-v4-Flash",
    "openclaw_tencent_tokenhub_hy3_trajectories_20260718_runs3_parallel_key2": "Hunyuan-3.0",
}

OPENCLAW_MODEL_ORDER = [
    "Claude-Opus-4.8",
    "Claude-Sonnet-4.6",
    "GPT-5.5",
    "GPT-5.4-mini",
    "Grok-4.5",
    "GLM-5.2",
    "Qwen-3.7-max",
    "Qwen-3.7-plus",
    "Kimi-K3",
    "Kimi-K2.6",
    "MiniMax-M3",
    "MiniMax-M2.7",
    "Deepseek-v4-Pro",
    "Deepseek-v4-Flash",
    "Hunyuan-3.0",
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


class Group:
    def __init__(self, label: str, dataset_id: str) -> None:
        self.label = label
        self.dataset_id = dataset_id
        self.values: list[float] = []


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Plot attack and clean rollout iteration-count boxplots."
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
        default=None,
        help="Optional merged UGS JSON with top-level results[] for clean trajectories.",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("results/figures/iteration_boxplots"),
        help="Output directory for figures and TSVs.",
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
    parser.add_argument("--dpi", type=int, default=300, help="Raster DPI for PNG outputs.")
    parser.add_argument(
        "--skip-plots",
        action="store_true",
        help="Only write TSV/manifest outputs; do not import matplotlib or render figures.",
    )
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


def dataset_id(row: dict[str, Any]) -> str:
    value = row.get("score_dataset_id") or row.get("dataset_id") or row.get("dataset")
    return str(value) if value else "unknown_dataset"


def collect_groups(rows: list[dict[str, Any]], scenario: str) -> list[Group]:
    if scenario == "openclaw_models":
        groups = {
            dataset: Group(label, dataset) for dataset, label in OPENCLAW_DATASET_LABELS.items()
        }
        order = OPENCLAW_MODEL_ORDER
    elif scenario == "deepseek_v4_pro_agents":
        groups = {
            dataset: Group(label, dataset)
            for dataset, label in DEEPSEEK_V4_PRO_AGENT_DATASETS.items()
        }
        order = DEEPSEEK_AGENT_ORDER
    else:
        raise ValueError(f"unsupported scenario: {scenario}")

    for row in rows:
        if row.get("evaluation_error"):
            continue
        dataset = dataset_id(row)
        if dataset not in groups:
            continue
        value = finite_float(row.get("iteration_count"))
        if value is None:
            continue
        groups[dataset].values.append(value)

    by_label = {group.label: group for group in groups.values() if group.values}
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


def write_summary_tsv(scenarios: dict[str, list[Group]], out_dir: Path) -> Path:
    path = out_dir / "iteration_boxplot_summary.tsv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "scenario",
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
            ],
            delimiter="\t",
        )
        writer.writeheader()
        for scenario, groups in scenarios.items():
            for group in groups:
                values = group.values
                writer.writerow(
                    {
                        "scenario": scenario,
                        "label": group.label,
                        "dataset_id": group.dataset_id,
                        "n": len(values),
                        "mean": f"{mean(values):.6f}",
                        "median": f"{median(values):.6f}",
                        "q1": f"{percentile(values, 25):.6f}",
                        "q3": f"{percentile(values, 75):.6f}",
                        "p5": f"{percentile(values, 5):.6f}",
                        "p95": f"{percentile(values, 95):.6f}",
                        "min": f"{min(values):.6f}",
                        "max": f"{max(values):.6f}",
                    }
                )
    return path


def write_values_tsv(scenarios: dict[str, list[Group]], out_dir: Path) -> Path:
    path = out_dir / "iteration_boxplot_values.tsv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["scenario", "label", "dataset_id", "row_index", "iteration_count"],
            delimiter="\t",
        )
        writer.writeheader()
        for scenario, groups in scenarios.items():
            for group in groups:
                for index, value in enumerate(group.values):
                    writer.writerow(
                        {
                            "scenario": scenario,
                            "label": group.label,
                            "dataset_id": group.dataset_id,
                            "row_index": index,
                            "iteration_count": f"{value:.6f}",
                        }
                    )
    return path


def write_manifest(
    ags_json: Path,
    ugs_json: Path | None,
    scenarios: dict[str, list[Group]],
    show_fliers: bool,
    formats: list[str],
    skip_plots: bool,
    out_dir: Path,
) -> Path:
    path = out_dir / "manifest.json"
    payload = {
        "description": "Iteration-count boxplots for attack and optional clean rollouts.",
        "source": str(ags_json),
        "sources": {
            "attack": str(ags_json),
            "clean": str(ugs_json) if ugs_json is not None else None,
        },
        "iteration_field": "iteration_count",
        "score_rows": "AGS malicious rollout rows plus UGS clean baseline rows when --ugs-json is supplied",
        "boxplot_whiskers": "matplotlib default 1.5 IQR",
        "show_fliers": show_fliers,
        "formats": formats,
        "plots_written": not skip_plots,
        "scenarios": {
            name: [
                {"label": group.label, "dataset_id": group.dataset_id, "n": len(group.values)}
                for group in groups
            ]
            for name, groups in scenarios.items()
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
    except ImportError as exc:
        raise SystemExit("matplotlib is required for plotting.") from exc
    return plt


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


def slugify(value: str) -> str:
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    return value.strip("_")


def bold_axis_text(axis: Any) -> None:
    axis.xaxis.label.set_fontweight("bold")
    axis.yaxis.label.set_fontweight("bold")
    for tick_label in axis.get_xticklabels() + axis.get_yticklabels():
        tick_label.set_fontweight("bold")


def plot_boxplot(
    plt: Any,
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
    labels = [group.label for group in groups]
    values = [group.values for group in groups]
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

    medians = [median(group.values) for group in groups]
    for index, med in enumerate(medians, start=1):
        axis.text(
            index,
            med,
            f"{med:g}",
            ha="center",
            va="bottom",
            fontsize=8.0,
            fontweight="bold",
            color="#222222",
        )

    del title
    axis.set_ylabel("Iteration count", fontsize=11.2, fontweight="bold")
    axis.set_xlabel(xlabel, fontsize=11.2, fontweight="bold")
    axis.grid(axis="y", color="#DDDDDD", linewidth=0.6)
    axis.set_axisbelow(True)
    axis.spines["top"].set_visible(False)
    axis.spines["right"].set_visible(False)
    if len(groups) > 8:
        axis.tick_params(axis="x", rotation=35, labelsize=8.8)
        for tick in axis.get_xticklabels():
            tick.set_ha("right")
    else:
        axis.tick_params(axis="x", rotation=18, labelsize=9.4)
        for tick in axis.get_xticklabels():
            tick.set_ha("right")
    axis.tick_params(axis="y", labelsize=10.0)
    bold_axis_text(axis)

    for suffix in formats:
        path = out_dir / f"{stem}.{suffix}"
        fig.savefig(path, dpi=dpi if suffix == "png" else None, bbox_inches="tight")
    plt.close(fig)


def plot_combined_boxplot(
    plt: Any,
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
    attack_by_label = {group.label: group for group in attack_groups}
    clean_by_label = {group.label: group for group in clean_groups}
    labels = [group.label for group in attack_groups if group.label in clean_by_label]
    attack_values = [attack_by_label[label].values for label in labels]
    clean_values = [clean_by_label[label].values for label in labels]

    fig_width = 8.6 if len(labels) > 8 else 6.8
    fig_height = 4.9 if len(labels) > 8 else 4.2
    fig, axis = plt.subplots(figsize=(fig_width, fig_height), constrained_layout=False)
    fig.subplots_adjust(left=0.095, right=0.985, bottom=0.33 if len(labels) > 8 else 0.23, top=0.86)

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
            f"{med:g}",
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
            f"{med:g}",
            ha="center",
            va="bottom",
            fontsize=8.0,
            fontweight="bold",
            color="#222222",
        )

    axis.set_xticks(centers, labels)
    axis.set_xlim(0.4, len(labels) + 0.6)
    del title
    axis.set_ylabel("Iteration count", fontsize=11.2, fontweight="bold")
    axis.set_xlabel(xlabel, fontsize=11.2, fontweight="bold")
    axis.grid(axis="y", color="#DDDDDD", linewidth=0.6)
    axis.set_axisbelow(True)
    axis.spines["top"].set_visible(False)
    axis.spines["right"].set_visible(False)
    if len(labels) > 8:
        axis.tick_params(axis="x", rotation=38, labelsize=8.2)
        for tick in axis.get_xticklabels():
            tick.set_ha("right")
    else:
        axis.tick_params(axis="x", rotation=18, labelsize=9.8)
        for tick in axis.get_xticklabels():
            tick.set_ha("right")
    axis.tick_params(axis="y", labelsize=10.4)
    bold_axis_text(axis)

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

    for suffix in formats:
        path = out_dir / f"{stem}.{suffix}"
        fig.savefig(path, dpi=dpi if suffix == "png" else None, bbox_inches="tight")
    plt.close(fig)


def main() -> int:
    args = parse_args()
    formats = args.formats or ["pdf", "svg"]
    args.out_dir.mkdir(parents=True, exist_ok=True)

    attack_rows = load_rows(args.ags_json)
    scenarios = {
        "openclaw_models": collect_groups(attack_rows, "openclaw_models"),
        "deepseek_v4_pro_agents": collect_groups(attack_rows, "deepseek_v4_pro_agents"),
    }
    if args.ugs_json is not None:
        clean_rows = load_rows(args.ugs_json)
        scenarios.update(
            {
                "clean_openclaw_models": collect_groups(clean_rows, "openclaw_models"),
                "clean_deepseek_v4_pro_agents": collect_groups(
                    clean_rows, "deepseek_v4_pro_agents"
                ),
            }
        )
    for name, groups in scenarios.items():
        if not groups:
            raise SystemExit(f"No groups found for scenario: {name}")

    summary_path = write_summary_tsv(scenarios, args.out_dir)
    values_path = write_values_tsv(scenarios, args.out_dir)
    manifest_path = write_manifest(
        args.ags_json,
        args.ugs_json,
        scenarios,
        args.show_fliers,
        formats,
        args.skip_plots,
        args.out_dir,
    )

    if not args.skip_plots:
        plt = require_matplotlib()
        configure_matplotlib(plt)
        plot_boxplot(
            plt,
            scenarios["openclaw_models"],
            "OpenClaw across models — attack iteration count",
            "Model",
            "iteration_boxplot_openclaw_models",
            args.out_dir,
            formats,
            args.show_fliers,
            args.dpi,
            "AGS/malicious rollout rows",
        )
        plot_boxplot(
            plt,
            scenarios["deepseek_v4_pro_agents"],
            "Deepseek-v4-Pro across agents — attack iteration count",
            "Agent",
            "iteration_boxplot_deepseek_v4_pro_agents",
            args.out_dir,
            formats,
            args.show_fliers,
            args.dpi,
            "AGS/malicious rollout rows",
        )
        if args.ugs_json is not None:
            plot_boxplot(
                plt,
                scenarios["clean_openclaw_models"],
                "OpenClaw across models — clean iteration count",
                "Model",
                "iteration_boxplot_clean_openclaw_models",
                args.out_dir,
                formats,
                args.show_fliers,
                args.dpi,
                "UGS/clean baseline rows",
            )
            plot_boxplot(
                plt,
                scenarios["clean_deepseek_v4_pro_agents"],
                "Deepseek-v4-Pro across agents — clean iteration count",
                "Agent",
                "iteration_boxplot_clean_deepseek_v4_pro_agents",
                args.out_dir,
                formats,
                args.show_fliers,
                args.dpi,
                "UGS/clean baseline rows",
            )
            plot_combined_boxplot(
                plt,
                scenarios["openclaw_models"],
                scenarios["clean_openclaw_models"],
                "OpenClaw across models — attack vs. clean iteration count",
                "Model",
                "iteration_boxplot_combined_openclaw_models",
                args.out_dir,
                formats,
                args.show_fliers,
                args.dpi,
            )
            plot_combined_boxplot(
                plt,
                scenarios["deepseek_v4_pro_agents"],
                scenarios["clean_deepseek_v4_pro_agents"],
                "Deepseek-v4-Pro across agents — attack vs. clean iteration count",
                "Agent",
                "iteration_boxplot_combined_deepseek_v4_pro_agents",
                args.out_dir,
                formats,
                args.show_fliers,
                args.dpi,
            )

    output_label = "iteration TSVs" if args.skip_plots else "iteration boxplots"
    print(f"Wrote {output_label} to {args.out_dir}")
    print(f"Wrote summary TSV: {summary_path}")
    print(f"Wrote values TSV: {values_path}")
    print(f"Wrote manifest: {manifest_path}")
    for name, groups in scenarios.items():
        print(f"{name}: {len(groups)} groups, {sum(len(group.values) for group in groups)} rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
