#!/usr/bin/env python3
"""Command-line entrypoint for ActBench runs."""

from __future__ import annotations

import argparse
import logging
import sys

from benchmark.backends.registry import available_backend_names
from benchmark.runner import run_benchmark

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("actbench.log"),
        logging.FileHandler("benchmark.log"),
    ],
)

logger = logging.getLogger("benchmark")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="ActBench target-agent evaluation runner")
    parser.add_argument(
        "--tasks-dir",
        default=None,
        help="Task directory to load (default: repository tasks/)",
    )
    parser.add_argument(
        "--model",
        required=False,
        default="deepseek/deepseek-v4-pro",
        help="Model identifier (default: deepseek/deepseek-v4-pro)",
    )
    parser.add_argument(
        "--backend",
        choices=available_backend_names(),
        default="openclaw",
        help="Target-agent backend to execute tasks (default: openclaw)",
    )
    parser.add_argument(
        "--suite",
        default="all",
        help=(
            'Tasks to run: "all", "automated-only", behavior code/slug '
            '(e.g. "B1", "B11", "obfuscated_execution"), legacy risk code/type '
            '(e.g. "R1", "R2", "unauthorized_execution"), canonical or legacy task IDs '
            '(e.g. "task_B6_T01", "task_R2_T01"), or comma-separated prefixes/IDs'
        ),
    )
    parser.add_argument(
        "--output-dir",
        default="results",
        help="Results directory",
    )
    parser.add_argument(
        "--timeout-multiplier",
        type=float,
        default=1.0,
        help="Scale all task timeouts",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=1,
        help="Number of runs per task for averaging",
    )
    parser.add_argument(
        "--judge-model",
        "--reward-judge",
        "--judge",
        dest="judge_model",
        default=None,
        help=(
            "Judge model for attack_success, stealth, security-awareness, and interception scoring "
            "(default: deepseek/deepseek-v4-pro). "
            "Routed by prefix: 'deepseek/...' → DeepSeek, otherwise OpenRouter. "
            "Requires the matching API key env var."
        ),
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging (shows transcript contents, workspace files, etc.)",
    )
    parser.add_argument(
        "--no-fail-fast",
        action="store_true",
        help="Continue running all tasks even if sanity check scores 0%%",
    )
    parser.add_argument(
        "--skip-baseline-gen",
        action="store_true",
        help=(
            "Skip pre-generating benign baselines; use cached ones only "
            "(faster but may reduce scoring accuracy)"
        ),
    )
    parser.add_argument(
        "--training-artifact-dir",
        default=None,
        help="Directory for raw training artifacts (default: results/<run>_<model>_artifacts)",
    )
    parser.add_argument(
        "--no-training-artifacts",
        action="store_true",
        help="Disable raw training artifact recording",
    )
    return parser.parse_args()


def main() -> None:
    run_benchmark(_parse_args())


if __name__ == "__main__":
    main()
