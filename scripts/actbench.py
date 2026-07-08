#!/usr/bin/env python3
"""ActBench runner entrypoint."""

from __future__ import annotations

import sys
from pathlib import Path


def _bootstrap_scripts_path() -> None:
    scripts_dir = Path(__file__).resolve().parent
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))


def main() -> None:
    _bootstrap_scripts_path()
    from benchmark.cli import main as _main

    _main()


if __name__ == "__main__":
    main()
