#!/usr/bin/env python3
"""ActBench raw_by_task packer entrypoint."""

from __future__ import annotations

import sys
from pathlib import Path


def _bootstrap_scripts_path() -> None:
    scripts_dir = Path(__file__).resolve().parent
    repo_root = scripts_dir.parent
    for path in (repo_root, scripts_dir):
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))


def main() -> None:
    _bootstrap_scripts_path()
    from benchmark.pack_raw_by_task import main as _main

    raise SystemExit(_main())


if __name__ == "__main__":
    main()
