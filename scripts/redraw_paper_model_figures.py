#!/usr/bin/env python3
"""Refresh manuscript model figures from archived plot values, excluding incomplete batches.

The archived TSVs are read without rescoring rollouts. Retained distributions
and curve points are unchanged. Outputs are written to a separate directory;
the historical source archive is preserved.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import plot_iteration_boxplots as iterations
import plot_score_weight_sensitivity_combined as combined


ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "results/figures/threshold_0.9"
EXCLUDED = combined.EXCLUDED_MODELS


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream, delimiter="\t"))


def read_iterations(path: Path) -> dict[str, list[iterations.Group]]:
    groups: dict[str, dict[str, iterations.Group]] = {}
    for row in read_tsv(path):
        if row["label"] in EXCLUDED:
            continue
        scenario = groups.setdefault(row["scenario"], {})
        group = scenario.setdefault(
            row["label"], iterations.Group(row["label"], row["dataset_id"])
        )
        group.values.append(float(row["iteration_count"]))
    return {scenario: list(items.values()) for scenario, items in groups.items()}


def curve_groups(path: Path, value_key: str, metric: str | None = None):
    curves: dict[str, list[tuple[float, float]]] = {}
    for row in read_tsv(path):
        if metric is not None and row["metric"] != metric:
            continue
        label = row["agent_model"]
        if label.startswith("OpenClaw + "):
            curves.setdefault(label, []).append(
                (float(row["python_weight"]), float(row[value_key]))
            )
    for points in curves.values():
        points.sort()
    return curves


def plot_standalone(plt, curves, metric: str, output: Path) -> None:
    """Retain the archived standalone layout and each retained curve's color."""
    is_rate = metric == "ASR"
    is_pass = metric.startswith("pass@")
    fig, axis = plt.subplots(figsize=(7.0, 4.6))
    fig.subplots_adjust(
        left=0.11 if is_rate else 0.10,
        right=0.70,
        bottom=0.21 if is_rate or is_pass else 0.17,
        top=0.86,
    )
    colors = plt.get_cmap("tab20")
    for index, (label, points) in enumerate(curves.items()):
        if label.removeprefix("OpenClaw + ") in EXCLUDED:
            continue
        beta, values = zip(*points)
        axis.plot(
            beta, values, marker="o", markersize=2.5, linewidth=1.25,
            color=colors(index % 20), label=label.removeprefix("OpenClaw + "),
        )
    axis.axvline(0.4, color="#333333", linestyle="--", linewidth=1.0)
    axis.set_xlim(0, 1)
    axis.set_ylim(0, 1)
    axis.set_xlabel("Python component weight α")
    axis.set_ylabel("Attack success rate (scoreα ≥ 0.9)" if is_rate else metric)
    axis.set_title(
        "OpenClaw across models — " + ("attack success rate" if is_rate else metric),
        fontweight="bold",
    )
    axis.grid(color="#DDDDDD", linewidth=0.6)
    axis.set_axisbelow(True)
    axis.spines["top"].set_visible(False)
    axis.spines["right"].set_visible(False)
    if is_rate or is_pass:
        k = metric.removeprefix("pass@")
        note = (
            r"score$_\alpha$ = α · Python + (1 − α) · LLM; y-axis is the fraction of rows where score$_\alpha$ ≥ 0.9."
            if is_rate else
            rf"pass@{k}: fraction of tasks with any successful run among the first {k}; success means score$_\alpha$ ≥ 0.9."
        )
        axis.text(0, -0.27, note, transform=axis.transAxes, fontsize=7.2, color="#444444")
    axis.legend(loc="center left", bbox_to_anchor=(1.01, 0.5), frameon=False, ncol=1, fontsize=6.5)
    fig.savefig(output, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive-dir", type=Path, default=ARCHIVE)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    archive, output = args.archive_dir, args.out_dir
    output.mkdir(parents=True, exist_ok=True)
    weight_dir = output / "score_weight_sensitivity"
    weight_dir.mkdir(exist_ok=True)

    source_values = archive / "iteration_boxplots/iteration_boxplot_values.tsv"
    scenarios = read_iterations(source_values)
    attack, clean = scenarios["openclaw_models"], scenarios["clean_openclaw_models"]
    if len(attack) != 15 or [g.label for g in attack] != [g.label for g in clean]:
        raise ValueError("Expected 15 matching complete-core model groups after exclusions.")
    plt = iterations.require_matplotlib()
    iterations.configure_matplotlib(plt)
    iterations.plot_combined_boxplot(
        plt, attack, clean, "", "Model", "iteration_boxplot_combined_openclaw_models",
        output, ["pdf", "png", "svg"], False, 300,
    )
    iterations.write_summary_tsv(scenarios, output)
    iterations.write_values_tsv(scenarios, output)
    (output / "apdix_resource_iteration.pdf").write_bytes(
        (output / "iteration_boxplot_combined_openclaw_models.pdf").read_bytes()
    )

    resource_dir = archive / "rollout_resources"
    agent_time = resource_dir / "time/rollout_resource_execution_time_combined_deepseek_v4_pro_agents.png"
    model_tokens = resource_dir / "token/rollout_resource_total_tokens_combined_openclaw_models.png"
    subprocess.run(
        [sys.executable, str(ROOT / "scripts/compose_execution_cost_figure.py"),
         "--iteration", str(output / "iteration_boxplot_combined_openclaw_models.png"),
         "--agent-time", str(agent_time), "--model-tokens", str(model_tokens),
         "--out-pdf", str(output / "apdix_execution_cost.pdf"),
         "--out-png", str(output / "apdix_execution_cost.png")],
        check=True,
    )

    sensitivity = archive / "score_weight_sensitivity"
    score_curves = sensitivity / "score_curves/score_weight_sensitivity_curves.tsv"
    with plt.rc_context():
        combined.plot_combined(
            combined.read_curves(score_curves),
            weight_dir / "score_weight_sensitivity_combined_beta.pdf",
        )

    sources = [source_values, score_curves, agent_time, model_tokens]
    curves_to_plot = [
        (score_curves, "score", "AGS", "score_weight_sensitivity_openclaw_models_beta"),
        (score_curves, "score", "UGS", "score_weight_sensitivity_openclaw_models_ugs"),
        (sensitivity / "attack_success_rates/attack_success_rate_curves.tsv",
         "attack_success_rate", "ASR", "attack_success_rate_openclaw_models"),
    ]
    curves_to_plot += [
        (sensitivity / f"pass_at_{k}/pass_at_{k}_curves.tsv",
         "pass_at_k", f"pass@{k}", f"pass_at_{k}_openclaw_models")
        for k in (1, 2, 3)
    ]
    with plt.rc_context():
        plt.rcdefaults()
        plt.rcParams.update({
            "font.size": 8.2, "axes.labelsize": 8.5, "axes.titlesize": 9.0,
            "xtick.labelsize": 8.0, "ytick.labelsize": 8.0, "legend.fontsize": 6.6,
            "pdf.fonttype": 42, "ps.fonttype": 42,
        })
        for path, field, metric, stem in curves_to_plot:
            curves = curve_groups(path, field, metric if field == "score" else None)
            retained = [label for label in curves if label.removeprefix("OpenClaw + ") not in EXCLUDED]
            if len(retained) != 15 or any(len(curves[label]) != 21 for label in retained):
                raise ValueError(f"Expected 15 complete-core models and 21 beta points for {metric}.")
            plot_standalone(plt, curves, metric, weight_dir / f"{stem}.pdf")
            sources.append(path)

    manifest = {
        "excluded_models": sorted(EXCLUDED),
        "retained_models": [group.label for group in attack],
        "model_count": len(attack),
        "data_policy": "Existing archived plot values; no rescoring or imputation.",
        "source_sha256": {
            str(path): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in dict.fromkeys(sources)
        },
        "pdf_outputs": [str(path.relative_to(output)) for path in sorted(output.rglob("*.pdf"))],
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Refreshed {len(manifest['pdf_outputs'])} PDF assets for 15 complete-core models: {output}")


if __name__ == "__main__":
    main()
