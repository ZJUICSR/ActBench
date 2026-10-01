"""Generate standalone and combined search ablation figures for the manuscript."""

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from plot_task_coverage import BAR_EDGE_COLOR, B_CLASS_COLOR


plt.rcParams.update(
    {
        "font.family": "serif",
        "font.serif": ["STIXGeneral"],
        "mathtext.fontset": "stix",
        "font.size": 8.5,
        "axes.labelsize": 8.5,
        "axes.titlesize": 9,
        "axes.linewidth": 0.8,
        "xtick.labelsize": 7.5,
        "ytick.labelsize": 7.5,
        "legend.fontsize": 7.5,
        "legend.frameon": True,
        "legend.facecolor": "white",
        "legend.edgecolor": "none",
        "legend.framealpha": 1.0,
        "legend.borderpad": 0.2,
        "legend.handlelength": 2.2,
        "lines.linewidth": 1.4,
        "lines.markersize": 4,
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
    }
)


def draw_beam_rollback(ax: plt.Axes) -> None:
    beam = np.array([1, 2, 3, 4])
    rollback_off = np.array([66.0, 69.4, 69.4, 70.7])
    rollback_on = np.array([69.1, 71.6, 71.6, 72.2])
    gains = rollback_on - rollback_off

    ax.plot(
        beam,
        rollback_off,
        color="#0072B2",
        linestyle="--",
        marker="o",
        linewidth=1.4,
        markersize=4,
        label="Rollback off",
    )
    ax.plot(
        beam,
        rollback_on,
        color="#D55E00",
        linestyle="-",
        marker="o",
        linewidth=1.4,
        markersize=4,
        label="Rollback on",
    )

    for x, lower, upper, gain in zip(beam, rollback_off, rollback_on, gains):
        ax.annotate(
            "",
            xy=(x, upper - 0.10),
            xytext=(x, lower + 0.10),
            arrowprops={"arrowstyle": "->", "color": "#555555", "lw": 0.8},
        )
        label_left = x == beam[-1]
        ax.text(
            x - 0.08 if label_left else x + 0.06,
            (lower + upper) / 2,
            f"+{gain:.1f}",
            fontsize=7.5,
            ha="right" if label_left else "left",
            va="center",
        )

    ax.set_xlabel("Beam width $B$")
    ax.set_ylabel("Search success (%)")
    ax.set_xticks(beam)
    ax.set_xlim(0.75, 4.25)
    ax.set_ylim(64, 74)
    ax.set_yticks(np.arange(64, 75, 2))
    ax.grid(axis="y", color="#D9D9D9", linewidth=0.6)
    ax.set_axisbelow(True)
    ax.legend(loc="lower right")


def save_beam_rollback(figures: Path) -> None:
    fig, ax = plt.subplots(figsize=(3.45, 2.55))
    draw_beam_rollback(ax)
    fig.tight_layout(pad=0.35)
    fig.savefig(figures / "search_ablation_beam_rollback.pdf", bbox_inches="tight")
    plt.close(fig)


def draw_self_evolving_budget(ax: plt.Axes) -> None:
    rounds = np.arange(7)
    search_success = np.array([54.0, 65.7, 69.4, 71.3, 71.9, 72.5, 72.8])

    bars = ax.bar(
        rounds,
        search_success,
        color=B_CLASS_COLOR,
        edgecolor=BAR_EDGE_COLOR,
        linewidth=0.4,
        width=0.68,
        alpha=0.86,
        zorder=3,
    )
    ax.plot(
        rounds,
        search_success,
        color=BAR_EDGE_COLOR,
        linestyle="--",
        linewidth=1.2,
        marker="o",
        markersize=3,
        zorder=4,
    )
    value_labels = ax.bar_label(
        bars,
        labels=[f"{value:.1f}" for value in search_success],
        padding=6,
        fontsize=7.5,
    )
    # Clear the steep first segment while keeping all values above the bars.
    value_labels[0].set_position((-4, 6))

    ax.set_xlabel("Evolving round")
    ax.set_ylabel("Search success (%)")
    ax.set_xticks(rounds)
    ax.set_xlim(-0.6, 6.6)
    ax.set_ylim(40, 80)
    ax.set_yticks(np.arange(40, 81, 10))
    ax.grid(axis="y", color="#D9D9D9", linewidth=0.6)
    ax.set_axisbelow(True)


def save_reflector_round_budget(figures: Path) -> None:
    fig, ax = plt.subplots(figsize=(3.45, 2.55))
    draw_self_evolving_budget(ax)
    fig.tight_layout(pad=0.35)
    fig.savefig(figures / "reflector_round_budget.pdf", bbox_inches="tight")
    plt.close(fig)


def save_combined_ablation(figures: Path) -> None:
    # Match the manuscript's 5.5-inch text width so labels retain their size.
    fig, axes = plt.subplots(1, 2, figsize=(5.5, 2.3))
    draw_beam_rollback(axes[0])
    draw_self_evolving_budget(axes[1])
    axes[0].set_title("(a) Beam width and rollback", loc="left", pad=7)
    axes[1].set_title("(b) Self-evolving rounds", loc="left", pad=7)
    fig.tight_layout(pad=0.35, w_pad=1.0)
    fig.savefig(figures / "search_ablation_combined.pdf", bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Directory in which to write the manuscript PDF figures.",
    )
    args = parser.parse_args()
    figures = args.output_dir.expanduser().resolve()
    figures.mkdir(parents=True, exist_ok=True)
    save_beam_rollback(figures)
    save_reflector_round_budget(figures)
    save_combined_ablation(figures)


if __name__ == "__main__":
    main()
