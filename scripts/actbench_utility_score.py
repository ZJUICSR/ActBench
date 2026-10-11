#!/usr/bin/env python3
"""Compatibility alias for the current common UGS task scorer.

The historical v1 utility scorer exposed a thresholded utility projection.
The public entrypoint now routes to the v3 UGS scorer, which has no utility
pass threshold and can score clean and attacked roles with one contract.
"""

from __future__ import annotations

import sys
from pathlib import Path


def _bootstrap_scripts_path() -> None:
    scripts_dir = Path(__file__).resolve().parent
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))


def main() -> None:
    _bootstrap_scripts_path()
    from benchmark.utility_task_scoring import main as _main

    raise SystemExit(_main())


if __name__ == "__main__":
    main()
