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
        "--run-workers",
        "--parallel-runs",
        dest="run_workers",
        type=int,
        default=1,
        help="Number of same-task repeat runs to execute concurrently (default: 1)",
    )
    parser.add_argument(
        "--run-number",
        action="append",
        default=None,
        help=(
            "Only execute selected 1-based repeat run number(s); may be repeated or "
            "comma-separated, e.g. --run-number 2 or --run-number 1,3"
        ),
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
        "--regenerate-baselines",
        action="store_true",
        help="Regenerate benign baselines even when a valid cache entry already exists",
    )
    parser.add_argument(
        "--skip-scoring",
        action="store_true",
        help="Skip inline attack scoring; record execution artifacts and trajectories only",
    )
    parser.add_argument(
        "--baseline-only",
        action="store_true",
        help="Generate benign baselines for the selected tasks, then skip attack execution",
    )
    parser.add_argument(
        "--execution-retries",
        type=int,
        default=0,
        help="Retry each task repeat up to N times when execution status is retryable (default: 0)",
    )
    parser.add_argument(
        "--retry-status",
        default="error,timeout",
        help="Comma-separated execution statuses that trigger --execution-retries (default: error,timeout)",
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
    args = parser.parse_args()
    if args.skip_baseline_gen and args.regenerate_baselines:
        parser.error("--regenerate-baselines cannot be used with --skip-baseline-gen")
    if args.baseline_only and args.skip_baseline_gen:
        parser.error("--baseline-only cannot be used with --skip-baseline-gen")
    if args.execution_retries < 0:
        parser.error("--execution-retries must be a non-negative integer")
    if args.execution_retries > 0 and not any(part.strip() for part in args.retry_status.split(",")):
        parser.error("--retry-status must include at least one status when --execution-retries > 0")
    if args.run_number:
        for raw_value in args.run_number:
            for part in str(raw_value).split(","):
                text = part.strip()
                if not text:
                    continue
                try:
                    number = int(text)
                except ValueError:
                    parser.error(f"--run-number must be a positive integer, got {text!r}")
                if number < 1:
                    parser.error("--run-number must be a positive integer")
    return args


def main() -> None:
    run_benchmark(_parse_args())


if __name__ == "__main__":
    main()
