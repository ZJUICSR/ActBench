"""Generate the search and reflector ablation figures for the manuscript."""

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


plt.rcParams.update(
    {
        "font.family": "serif",
        "font.serif": ["DejaVu Serif"],
        "mathtext.fontset": "stix",
        "axes.labelsize": 8,
        "axes.titlesize": 8,
        "xtick.labelsize": 7,
        "ytick.labelsize": 7,
        "legend.fontsize": 7,
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
    }
)


def save_beam_rollback(figures: Path) -> None:
    beam = np.array([1, 2, 3, 4])
    rollback_off = np.array([66.0, 69.4, 69.4, 70.7])
    rollback_on = np.array([69.1, 71.6, 71.6, 72.2])
    gains = rollback_on - rollback_off

    fig, ax = plt.subplots(figsize=(3.45, 2.55))
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
        ax.text(x + 0.06, (lower + upper) / 2, f"+{gain:.1f}", fontsize=6, va="center")

    ax.set_xlabel("Beam width $B$")
    ax.set_ylabel("Search success (\%)")
    ax.set_xticks(beam)
    ax.set_xlim(0.75, 4.25)
    ax.set_ylim(64, 74)
    ax.set_yticks(np.arange(64, 75, 2))
    ax.grid(axis="y", color="#D9D9D9", linewidth=0.6)
    ax.set_axisbelow(True)
    ax.legend(loc="lower right", frameon=False, handlelength=2.2)
    fig.tight_layout(pad=0.35)
    fig.savefig(figures / "search_ablation_beam_rollback.pdf", bbox_inches="tight")
    plt.close(fig)


def save_reflector_round_budget(figures: Path) -> None:
    rounds = np.arange(7)
    search_success = np.array([54.0, 65.7, 69.4, 71.3, 71.9, 72.5, 72.8])
    recovered = np.array([0, 102, 139, 163, 175, 178, 179])

    fig, ax_left = plt.subplots(figsize=(3.45, 2.55))
    ax_right = ax_left.twinx()

    success_line = ax_left.plot(
        rounds,
        search_success,
        color="#0072B2",
        marker="o",
        linewidth=1.5,
        markersize=4,
        label="Search success",
    )
    recovery_line = ax_right.plot(
        rounds,
        recovered,
        color="#D55E00",
        marker="s",
        linewidth=1.5,
        markersize=3.8,
        label="Cumulative reflector recoveries",
    )

    ax_left.axvline(3, color="#666666", linestyle=":", linewidth=0.9)
    ax_left.annotate(
        "R=3: 163/179 recoveries",
        xy=(3, search_success[3]),
        xytext=(3.45, 66.2),
        fontsize=6.2,
        arrowprops={"arrowstyle": "->", "color": "#666666", "lw": 0.7},
    )

    ax_left.set_xlabel("Maximum repair round $R$")
    ax_left.set_ylabel("Search success (\%)", color="#0072B2")
    ax_right.set_ylabel("Reflector-recovered paths", color="#D55E00")
    ax_left.set_xticks(rounds)
    ax_left.set_xlim(-0.25, 6.25)
    ax_left.set_ylim(52, 75)
    ax_left.set_yticks([54, 60, 66, 72])
    ax_right.set_ylim(0, 190)
    ax_right.set_yticks([0, 50, 100, 150, 190])
    ax_left.grid(axis="y", color="#D9D9D9", linewidth=0.6)
    ax_left.set_axisbelow(True)

    lines = success_line + recovery_line
    labels = [line.get_label() for line in lines]
    ax_left.legend(
        lines,
        labels,
        loc="lower center",
        bbox_to_anchor=(0.5, 1.02),
        ncol=2,
        frameon=False,
        handlelength=2.2,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.90), pad=0.35)
    fig.savefig(figures / "reflector_round_budget.pdf", bbox_inches="tight")
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


if __name__ == "__main__":
    main()
