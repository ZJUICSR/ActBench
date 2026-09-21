#!/usr/bin/env python3
"""Build a target-only agent image from an explicit, tiny build context."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from deeptrap.paths import data_root
from benchmark.docker_runtime import DEFAULT_IMAGES, image_for_backend


def stage_context(destination: Path, backend: str = "opencode") -> None:
    destination.mkdir(parents=True, exist_ok=True)
    if any(destination.iterdir()):
        raise ValueError(f"Build context must be empty: {destination}")
    if backend not in DEFAULT_IMAGES:
        raise ValueError(f"Unknown Docker backend: {backend}")
    source = data_root() / "docker" / backend
    for name in ("Dockerfile", ".dockerignore"):
        shutil.copy2(source / name, destination / name)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=tuple(DEFAULT_IMAGES), default="opencode")
    parser.add_argument("--tag", default=None)
    parser.add_argument("--docker", default=os.environ.get("ACTBENCH_DOCKER_BIN", "docker"))
    parser.add_argument("--opencode-version", default=None)
    parser.add_argument(
        "--build-arg",
        action="append",
        default=[],
        help="Build argument, e.g. HTTPS_PROXY=http://host:port",
    )
    parser.add_argument(
        "--context-only", type=Path, help="Stage the build context without contacting Docker"
    )
    args = parser.parse_args()
    if args.context_only:
        stage_context(args.context_only, args.backend)
        print(
            json.dumps(
                {"context": str(args.context_only), "files": ["Dockerfile", ".dockerignore"]}
            )
        )
        return
    with tempfile.TemporaryDirectory(prefix="actbench-docker-build-") as directory:
        stage_context(Path(directory), args.backend)
        command = [args.docker, "build", "--tag", args.tag or image_for_backend(args.backend)]
        if args.opencode_version:
            command.extend(["--build-arg", f"OPENCODE_VERSION={args.opencode_version}"])
        for value in args.build_arg:
            command.extend(["--build-arg", value])
        try:
            subprocess.run([*command, directory], check=True)
        except (OSError, subprocess.CalledProcessError) as exc:
            raise SystemExit(
                "Docker build failed; check the Docker daemon and the build output above."
            ) from exc


if __name__ == "__main__":
    main()
