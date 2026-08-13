"""Unified DeepTrap command-line interface."""

from __future__ import annotations

import importlib
import sys
from collections.abc import Sequence

from deeptrap import __version__


COMMANDS = {
    "run": ("scripts.actbench", "Run benchmark tasks against an agent backend"),
    "test": ("scripts.actbench_test", "Run a bounded evaluation or local self-test"),
    "score": ("scripts.actbench_score", "Score collected trajectories"),
    "pack": ("scripts.actbench_pack_raw_by_task", "Build a raw-by-task result pack"),
    "utility-prep": ("scripts.actbench_utility_prep", "Prepare utility-scoring records"),
    "utility-score": ("scripts.actbench_utility_score", "Score benchmark utility"),
    "utility-report": (
        "scripts.actbench_utility_checker_report",
        "Report task-specific utility checker coverage",
    ),
}


def _print_help() -> None:
    print("DeepTrap security evaluation for tool-using agents")
    print()
    print("Usage: deeptrap <command> [options]")
    print()
    print("Commands:")
    width = max(len(command) for command in COMMANDS)
    for command, (_, description) in COMMANDS.items():
        print(f"  {command:<{width}}  {description}")
    print()
    print("Run 'deeptrap <command> --help' for command-specific options.")


def main(argv: Sequence[str] | None = None) -> None:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in {"-h", "--help"}:
        _print_help()
        return
    if args[0] in {"-V", "--version"}:
        print(f"deeptrap {__version__}")
        return

    command = args.pop(0)
    entry = COMMANDS.get(command)
    if entry is None:
        available = ", ".join(COMMANDS)
        raise SystemExit(f"deeptrap: unknown command {command!r}; choose from: {available}")

    module_name, _ = entry
    module = importlib.import_module(module_name)
    previous_argv = sys.argv
    sys.argv = [f"deeptrap {command}", *args]
    try:
        module.main()
    finally:
        sys.argv = previous_argv
