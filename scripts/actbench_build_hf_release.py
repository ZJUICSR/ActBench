#!/usr/bin/env python3
"""Build the complete ActBench Hugging Face dataset release."""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> None:
    scripts_dir = Path(__file__).resolve().parent
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    from benchmark.release_hf_publish import main as publish_main

    raise SystemExit(publish_main())


if __name__ == "__main__":
    main()
