#!/usr/bin/env python3
"""Plot ActBench task coverage and behavior risk category task inventory figures."""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any


B_CLASS_ORDER = [f"B{i}" for i in range(1, 16)]

B_CLASS_LABELS = {
    "B1": "Instruction injection",
    "B2": "Goal hijacking",
    "B3": "Data exfiltration",
    "B4": "Credential exposure",
    "B5": "Memory poisoning",
    "B6": "State tampering",
    "B7": "Deceptive tool invocation",
    "B8": "Unauthorized CMD execution",
    "B9": "Unauthorized API invocation",
    "B10": "Tool scope escalation",
    "B11": "Resource exhaustion",
    "B12": "Obfuscated execution",
    "B13": "False reporting",
    "B14": "Context flooding",
    "B15": "Permission chaining",
}

DOMAIN_LABELS = {
    "business_operations": "Business Operations",
    "software_engineering": "Software Engineering",
    "infrastructure_operations": "Software Engineering",
    "knowledge_work": "Document Operations",
    "financial_operations": "Financial Operations",
    "security_compliance": "Security Operations",
    "missing": "Identity Operations",
}

DOMAIN_ORDER = [
    "Business Operations",
    "Software Engineering",
    "Document Operations",
    "Financial Operations",
    "Security Operations",
    "Identity Operations",
]

SERVICE_LABELS = {
    "automation": "Automation",
    "customer_records": "Customer records",
    "directory": "Directory / identity",
    "integrations": "Integrations",
    "knowledge_base": "Knowledge base",
    "ledger": "Ledger / finance",
    "mailbox": "Mailbox",
    "notebook": "Notebook / meetings",
    "scheduling": "Scheduling",
    "taskboard": "Task Tracker",
    "ticketing": "Ticketing",
    "web_content": "Web content",
}

PROFILE_GREEN = "#009E73"
PROFILE_GREEN_EDGE = "#005A43"
BAR_COLOR = PROFILE_GREEN
SERVICE_COLOR = PROFILE_GREEN
B_CLASS_COLOR = PROFILE_GREEN
BAR_EDGE_COLOR = PROFILE_GREEN_EDGE
GRID_COLOR = "#DDDDDD"
TEXT_COLOR = "#333333"


@dataclass(frozen=True)
class TaskMetadata:
    task_id: str
    path: str
    b_class: str
    b_label: str
    raw_scene_category: str
    domain_label: str
    scenario: str
    mock_services: tuple[str, ...]
    attack_method: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate ActBench scenario-coverage and behavior risk category task-count figures."
    )
    parser.add_argument(
        "--tasks-dir",
        type=Path,
        default=Path("tasks"),
        help="Directory containing task_B*_T*/task.yaml task definitions.",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("results/figures/task_coverage"),
        help="Output directory for figures, TSVs, and manifest.",
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


def load_yaml(path: Path) -> dict[str, Any]:
    try:
        import yaml
    except ImportError as exc:
        raise SystemExit("PyYAML is required to read task.yaml files.") from exc
    with path.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"{path} did not parse to a YAML mapping")
    return payload


def b_class_from_task(data: dict[str, Any], path: Path) -> str:
    for key in ("scoring_family", "behavior_id"):
        value = data.get(key)
        if isinstance(value, str) and re.fullmatch(r"B(?:[1-9]|1[0-5])", value):
            return value
    task_id = str(data.get("id") or path.parent.name)
    match = re.search(r"(?:^|_)B(1[0-5]|[1-9])(?:_|$)", task_id)
    if match:
        return f"B{match.group(1)}"
    return "unknown"


def normalized_domain(raw_scene_category: Any) -> tuple[str, str]:
    raw = str(raw_scene_category).strip() if raw_scene_category else "missing"
    return raw, DOMAIN_LABELS.get(raw, raw.replace("_", " ").title())


def load_tasks(tasks_dir: Path) -> list[TaskMetadata]:
    task_files = sorted(tasks_dir.glob("task_B*_T*/task.yaml"))
    if not task_files:
        raise SystemExit(f"No task YAML files found under {tasks_dir}")

    tasks: list[TaskMetadata] = []
    for path in task_files:
        data = load_yaml(path)
        b_class = b_class_from_task(data, path)
        raw_domain, domain_label = normalized_domain(data.get("scene_category"))
        services = tuple(str(service) for service in data.get("mock_services", []) if service)
        task_id = str(data.get("id") or path.parent.name)
        tasks.append(
            TaskMetadata(
                task_id=task_id,
                path=str(path),
                b_class=b_class,
                b_label=str(data.get("behavior_label") or B_CLASS_LABELS.get(b_class, b_class)),
                raw_scene_category=raw_domain,
                domain_label=domain_label,
                scenario=str(data.get("scenario") or "missing"),
                mock_services=services,
                attack_method=str(data.get("attack_method") or "missing"),
            )
        )
    return tasks


def ordered_domain_counts(tasks: list[TaskMetadata]) -> list[tuple[str, int]]:
    counts = Counter(task.domain_label for task in tasks)
    ordered = [(label, counts[label]) for label in DOMAIN_ORDER if label in counts]
    ordered.extend(
        sorted((label, count) for label, count in counts.items() if label not in DOMAIN_ORDER)
    )
    return ordered


def ordered_service_counts(tasks: list[TaskMetadata]) -> list[tuple[str, str, int]]:
    counts = Counter(service for task in tasks for service in task.mock_services)
    rows = [
        (service, SERVICE_LABELS.get(service, service.replace("_", " ").title()), count)
        for service, count in counts.items()
    ]
    return sorted(rows, key=lambda item: (-item[2], item[1]))


def ordered_b_counts(tasks: list[TaskMetadata]) -> list[tuple[str, str, int]]:
    counts = Counter(task.b_class for task in tasks)
    labels_by_class: dict[str, str] = {}
    for task in tasks:
        labels_by_class.setdefault(task.b_class, task.b_label)
    rows = []
    for b_class in B_CLASS_ORDER:
        rows.append(
            (
                b_class,
                B_CLASS_LABELS.get(b_class, labels_by_class.get(b_class, b_class)),
                counts[b_class],
            )
        )
    return rows


def write_task_values(tasks: list[TaskMetadata], out_dir: Path) -> Path:
    path = out_dir / "task_coverage_values.tsv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "task_id",
                "b_class",
                "b_label",
                "raw_scene_category",
                "domain_label",
                "scenario",
                "web_service_apis",
                "attack_method",
                "path",
            ],
            delimiter="\t",
        )
        writer.writeheader()
        for task in tasks:
            writer.writerow(
                {
                    "task_id": task.task_id,
                    "b_class": task.b_class,
                    "b_label": task.b_label,
                    "raw_scene_category": task.raw_scene_category,
                    "domain_label": task.domain_label,
                    "scenario": task.scenario,
                    "web_service_apis": ",".join(task.mock_services),
                    "attack_method": task.attack_method,
                    "path": task.path,
                }
            )
    return path


def write_domain_counts_tsv(tasks: list[TaskMetadata], out_dir: Path) -> Path:
    path = out_dir / "task_coverage_domain_counts.tsv"
    raw_counts = Counter(task.raw_scene_category for task in tasks)
    raw_by_label: dict[str, list[str]] = defaultdict(list)
    for raw, label in DOMAIN_LABELS.items():
        if raw in raw_counts:
            raw_by_label[label].append(raw)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["domain_label", "task_count", "raw_scene_categories"],
            delimiter="\t",
        )
        writer.writeheader()
        for label, count in ordered_domain_counts(tasks):
            writer.writerow(
                {
                    "domain_label": label,
                    "task_count": count,
                    "raw_scene_categories": ",".join(sorted(raw_by_label.get(label, []))),
                }
            )
    return path


def write_service_counts_tsv(tasks: list[TaskMetadata], out_dir: Path) -> Path:
    path = out_dir / "task_coverage_web_service_api_counts.tsv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["web_service_api", "api_label", "task_references"],
            delimiter="\t",
        )
        writer.writeheader()
        for service, label, count in ordered_service_counts(tasks):
            writer.writerow(
                {"web_service_api": service, "api_label": label, "task_references": count}
            )
    return path


def write_b_counts_tsv(tasks: list[TaskMetadata], out_dir: Path) -> Path:
    path = out_dir / "task_coverage_b_class_counts.tsv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["b_class", "b_label", "task_count"],
            delimiter="\t",
        )
        writer.writeheader()
        for b_class, label, count in ordered_b_counts(tasks):
            writer.writerow({"b_class": b_class, "b_label": label, "task_count": count})
    return path


def scenario_distribution(tasks: list[TaskMetadata]) -> dict[str, int]:
    counts = Counter(task.scenario for task in tasks)
    distribution = Counter(counts.values())
    return {str(task_count): distribution[task_count] for task_count in sorted(distribution)}


def write_manifest(
    tasks: list[TaskMetadata],
    tasks_dir: Path,
    out_dir: Path,
    formats: list[str],
    skip_plots: bool,
) -> Path:
    path = out_dir / "manifest.json"
    raw_scene_counts = Counter(task.raw_scene_category for task in tasks)
    domain_counts = ordered_domain_counts(tasks)
    service_counts = ordered_service_counts(tasks)
    b_counts = ordered_b_counts(tasks)
    payload = {
        "description": "ActBench task coverage figures from canonical task.yaml metadata.",
        "tasks_dir": str(tasks_dir),
        "task_count": len(tasks),
        "formats": formats,
        "plots_written": not skip_plots,
        "figures": {
            "task_scenario_coverage_overview": "two-panel Task domains + Web service APIs figure",
            "task_b_class_counts": "B1-B15 on x-axis with task counts on y-axis",
            "task_coverage_three_panel": "three-panel Task domains, Web service APIs, and behavior risk category counts figure",
        },
        "source_fields": {
            "b_class": "task.yaml scoring_family / behavior_id",
            "scenario": "task.yaml scenario",
            "scene_category": "task.yaml scene_category",
            "web_service_apis": "task.yaml mock_services",
        },
        "domain_normalization": {
            "infrastructure_operations": "merged into Software Engineering",
            "missing_scene_category": "displayed as Identity Operations; the affected tasks are credential-exposure workflows",
        },
        "scenario_ids": {
            "unique_count": len({task.scenario for task in tasks}),
            "task_count_distribution": scenario_distribution(tasks),
        },
        "raw_scene_category_counts": dict(sorted(raw_scene_counts.items())),
        "domain_counts": [{"domain": label, "tasks": count} for label, count in domain_counts],
        "web_service_api_counts": [
            {"web_service_api": service, "label": label, "task_references": count}
            for service, label, count in service_counts
        ],
        "b_class_counts": [
            {"b_class": b_class, "label": label, "tasks": count}
            for b_class, label, count in b_counts
        ],
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
            "font.size": 8.5,
            "axes.labelsize": 9.0,
            "axes.titlesize": 10.0,
            "xtick.labelsize": 8.0,
            "ytick.labelsize": 8.0,
            "legend.fontsize": 7.5,
            "figure.titlesize": 11.0,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
            "svg.fonttype": "none",
        }
    )


def add_bar_labels(
    axis: Any,
    values: list[int],
    *,
    x_pad: float = 1.0,
    fontsize: float = 7.5,
    fontweight: str = "bold",
) -> None:
    for patch, value in zip(axis.patches, values):
        axis.text(
            patch.get_width() + x_pad,
            patch.get_y() + patch.get_height() / 2.0,
            f"{value}",
            va="center",
            ha="left",
            fontsize=fontsize,
            fontweight=fontweight,
            color=TEXT_COLOR,
        )


def style_horizontal_bar_axis(axis: Any) -> None:
    axis.grid(axis="x", color=GRID_COLOR, linewidth=0.6)
    axis.set_axisbelow(True)
    axis.spines["top"].set_visible(False)
    axis.spines["right"].set_visible(False)


def add_vertical_bar_labels(
    axis: Any,
    values: list[int],
    *,
    y_pad: float = 0.7,
    fontsize: float = 7.5,
    fontweight: str = "bold",
) -> None:
    for patch, value in zip(axis.patches, values):
        axis.text(
            patch.get_x() + patch.get_width() / 2.0,
            patch.get_height() + y_pad,
            f"{value}",
            va="bottom",
            ha="center",
            fontsize=fontsize,
            fontweight=fontweight,
            color=TEXT_COLOR,
        )


def style_vertical_bar_axis(axis: Any) -> None:
    axis.grid(axis="y", color=GRID_COLOR, linewidth=0.6)
    axis.set_axisbelow(True)
    axis.spines["top"].set_visible(False)
    axis.spines["right"].set_visible(False)


def emphasize_axis_text(
    axis: Any,
    *,
    title_size: float,
    label_size: float,
    tick_size: float,
) -> None:
    axis.title.set_fontsize(title_size)
    axis.title.set_fontweight("bold")
    axis.xaxis.label.set_fontsize(label_size)
    axis.xaxis.label.set_fontweight("bold")
    axis.yaxis.label.set_fontsize(label_size)
    axis.yaxis.label.set_fontweight("bold")
    axis.tick_params(axis="both", labelsize=tick_size)
    for tick_label in axis.get_xticklabels() + axis.get_yticklabels():
        tick_label.set_fontweight("bold")


def plot_scenario_coverage(
    plt: Any,
    tasks: list[TaskMetadata],
    out_dir: Path,
    formats: list[str],
    dpi: int,
) -> None:
    domain_counts = ordered_domain_counts(tasks)
    service_counts = ordered_service_counts(tasks)

    fig, axes = plt.subplots(1, 2, figsize=(10.8, 5.0), constrained_layout=False)
    fig.subplots_adjust(left=0.26, right=0.985, bottom=0.13, top=0.84, wspace=0.48)
    fig.suptitle("ActBench workplace scenario coverage", fontweight="bold")

    domain_labels = [label for label, _count in domain_counts]
    domain_values = [count for _label, count in domain_counts]
    y_positions = list(range(len(domain_labels)))
    axes[0].barh(
        y_positions,
        domain_values,
        color=BAR_COLOR,
        edgecolor=BAR_EDGE_COLOR,
        linewidth=0.65,
        alpha=0.86,
        height=0.62,
    )
    axes[0].set_yticks(y_positions, domain_labels)
    axes[0].invert_yaxis()
    axes[0].set_xlabel("Tasks")
    axes[0].set_title("Task domains", fontweight="bold")
    axes[0].set_xlim(0, max(domain_values) + 12)
    add_bar_labels(axes[0], domain_values, x_pad=1.0)
    style_horizontal_bar_axis(axes[0])
    emphasize_axis_text(axes[0], title_size=10.5, label_size=9.4, tick_size=8.4)

    service_labels = [label for _service, label, _count in service_counts]
    service_values = [count for _service, _label, count in service_counts]
    service_y = list(range(len(service_labels)))
    axes[1].barh(
        service_y,
        service_values,
        color=SERVICE_COLOR,
        edgecolor=BAR_EDGE_COLOR,
        linewidth=0.65,
        alpha=0.86,
        height=0.62,
    )
    axes[1].set_yticks(service_y, service_labels)
    axes[1].invert_yaxis()
    axes[1].set_xlabel("Task-API references")
    axes[1].set_title("Web service APIs", fontweight="bold")
    axes[1].set_xlim(0, max(service_values) + 24)
    add_bar_labels(axes[1], service_values, x_pad=2.0, fontsize=7.3)
    style_horizontal_bar_axis(axes[1])
    emphasize_axis_text(axes[1], title_size=10.5, label_size=9.4, tick_size=8.4)

    for suffix in formats:
        path = out_dir / f"task_scenario_coverage_overview.{suffix}"
        fig.savefig(path, dpi=dpi if suffix == "png" else None, bbox_inches="tight")
    plt.close(fig)


def plot_b_class_counts(
    plt: Any,
    tasks: list[TaskMetadata],
    out_dir: Path,
    formats: list[str],
    dpi: int,
) -> None:
    b_counts = ordered_b_counts(tasks)
    labels = [b_class for b_class, _label, _count in b_counts]
    values = [count for _b_class, _label, count in b_counts]
    x_positions = list(range(len(labels)))

    fig, axis = plt.subplots(figsize=(8.2, 3.8), constrained_layout=False)
    fig.subplots_adjust(left=0.08, right=0.985, bottom=0.16, top=0.86)
    axis.bar(
        x_positions,
        values,
        color=B_CLASS_COLOR,
        edgecolor=BAR_EDGE_COLOR,
        linewidth=0.65,
        alpha=0.88,
        width=0.72,
    )
    axis.set_xticks(x_positions, labels)
    axis.set_xlabel("Behavior risk category")
    axis.set_ylabel("Tasks")
    axis.set_title("Task count by behavior risk category", fontweight="bold")
    axis.set_ylim(0, max(values) + 6)
    add_vertical_bar_labels(axis, values, y_pad=0.7)
    style_vertical_bar_axis(axis)
    emphasize_axis_text(axis, title_size=10.5, label_size=9.4, tick_size=8.4)
    for suffix in formats:
        path = out_dir / f"task_b_class_counts.{suffix}"
        fig.savefig(path, dpi=dpi if suffix == "png" else None, bbox_inches="tight")
    plt.close(fig)


def plot_three_panel_coverage(
    plt: Any,
    tasks: list[TaskMetadata],
    out_dir: Path,
    formats: list[str],
    dpi: int,
) -> None:
    domain_counts = ordered_domain_counts(tasks)
    service_counts = ordered_service_counts(tasks)
    b_counts = ordered_b_counts(tasks)

    title_size = 16.0
    label_size = 12.0
    tick_size = 10.8
    value_size = 10.4
    bar_alpha = 0.86
    domain_bar_thickness = 0.70
    service_bar_thickness = 0.78
    b_class_bar_width = 0.68

    fig = plt.figure(figsize=(10.8, 8.4), constrained_layout=False)
    domain_axis = fig.add_axes([0.18, 0.51, 0.29, 0.43])
    service_axis = fig.add_axes([0.62, 0.51, 0.31, 0.43])
    b_axis = fig.add_axes([0.13, 0.06, 0.76, 0.33])

    domain_labels = [label.replace(" ", "\n") for label, _count in domain_counts]
    domain_values = [count for _label, count in domain_counts]
    domain_y = list(range(len(domain_labels)))
    domain_axis.barh(
        domain_y,
        domain_values,
        color=BAR_COLOR,
        edgecolor=BAR_EDGE_COLOR,
        linewidth=0.65,
        alpha=bar_alpha,
        height=domain_bar_thickness,
    )
    domain_axis.set_yticks(domain_y, domain_labels)
    domain_axis.invert_yaxis()
    domain_axis.set_xlabel("Tasks")
    domain_axis.set_title("(a) Task domains", fontweight="bold")
    domain_axis.set_xlim(0, max(domain_values) + 12)
    add_bar_labels(domain_axis, domain_values, x_pad=1.0, fontsize=value_size, fontweight="bold")
    style_horizontal_bar_axis(domain_axis)
    emphasize_axis_text(
        domain_axis, title_size=title_size, label_size=label_size, tick_size=tick_size
    )

    service_labels = [label for _service, label, _count in service_counts]
    service_values = [count for _service, _label, count in service_counts]
    service_y = list(range(len(service_labels)))
    service_axis.barh(
        service_y,
        service_values,
        color=SERVICE_COLOR,
        edgecolor=BAR_EDGE_COLOR,
        linewidth=0.65,
        alpha=bar_alpha,
        height=service_bar_thickness,
    )
    service_axis.set_yticks(service_y, service_labels)
    service_axis.invert_yaxis()
    service_axis.set_xlabel("Task-API references")
    service_axis.set_title("(b) Web service APIs", fontweight="bold")
    service_axis.set_xlim(0, max(service_values) + 24)
    add_bar_labels(service_axis, service_values, x_pad=2.0, fontsize=value_size, fontweight="bold")
    style_horizontal_bar_axis(service_axis)
    emphasize_axis_text(
        service_axis, title_size=title_size, label_size=label_size, tick_size=tick_size
    )

    b_labels = [b_class for b_class, _label, _count in b_counts]
    b_values = [count for _b_class, _label, count in b_counts]
    b_x = list(range(len(b_labels)))
    b_axis.bar(
        b_x,
        b_values,
        color=B_CLASS_COLOR,
        edgecolor=BAR_EDGE_COLOR,
        linewidth=0.65,
        alpha=bar_alpha,
        width=b_class_bar_width,
    )
    b_axis.set_xticks(b_x, b_labels)
    b_axis.set_xlabel("Behavior risk category")
    b_axis.set_ylabel("Tasks")
    b_axis.set_title("(c) Task count by behavior risk category", fontweight="bold")
    b_axis.set_ylim(0, max(b_values) + 6)
    add_vertical_bar_labels(b_axis, b_values, y_pad=0.7, fontsize=value_size, fontweight="bold")
    style_vertical_bar_axis(b_axis)
    emphasize_axis_text(b_axis, title_size=title_size, label_size=label_size, tick_size=tick_size)

    for suffix in formats:
        path = out_dir / f"task_coverage_three_panel.{suffix}"
        fig.savefig(path, dpi=dpi if suffix == "png" else None, bbox_inches="tight")
    plt.close(fig)


def main() -> int:
    args = parse_args()
    formats = args.formats or ["pdf", "svg"]
    args.out_dir.mkdir(parents=True, exist_ok=True)

    tasks = load_tasks(args.tasks_dir)
    if not tasks:
        raise SystemExit("No tasks found.")

    values_path = write_task_values(tasks, args.out_dir)
    domain_tsv = write_domain_counts_tsv(tasks, args.out_dir)
    service_tsv = write_service_counts_tsv(tasks, args.out_dir)
    b_tsv = write_b_counts_tsv(tasks, args.out_dir)
    manifest = write_manifest(tasks, args.tasks_dir, args.out_dir, formats, args.skip_plots)

    if not args.skip_plots:
        plt = require_matplotlib()
        configure_matplotlib(plt)
        plot_scenario_coverage(plt, tasks, args.out_dir, formats, args.dpi)
        plot_b_class_counts(plt, tasks, args.out_dir, formats, args.dpi)
        plot_three_panel_coverage(plt, tasks, args.out_dir, formats, args.dpi)

    print(f"Wrote task coverage outputs to {args.out_dir}")
    print(f"Wrote values TSV: {values_path}")
    print(f"Wrote domain TSV: {domain_tsv}")
    print(f"Wrote Web service APIs TSV: {service_tsv}")
    print(f"Wrote behavior risk category TSV: {b_tsv}")
    print(f"Wrote manifest: {manifest}")
    print(f"Tasks: {len(tasks)}; scenario IDs: {len({task.scenario for task in tasks})}")
    print(
        "Domain counts: "
        + ", ".join(f"{label}={count}" for label, count in ordered_domain_counts(tasks))
    )
    print(
        "B counts: "
        + ", ".join(f"{b_class}={count}" for b_class, _label, count in ordered_b_counts(tasks))
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
