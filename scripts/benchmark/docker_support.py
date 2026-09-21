"""Shared host-side setup for isolated agent runtimes."""

from __future__ import annotations

from dataclasses import replace
import os
import json
import re
from pathlib import Path
import socket
from typing import Any

from benchmark.backends.base import BackendInitializationError, BackendRunContext
from benchmark.docker_runtime import DockerRuntime, validate_container_url


def initialize_runtime(context: BackendRunContext) -> DockerRuntime | None:
    if context.metadata.get("execution") != "docker":
        return None
    runtime = DockerRuntime(
        backend=context.backend,
        records_dir=Path(
            context.metadata.get("docker_records_dir")
            or context.run_root / context.run_id / "docker"
        ),
    )
    context.metadata.update(docker=runtime.metadata(), runtime_identity=runtime.identity())
    return runtime


def configure_mcp(config: Any, runtime: DockerRuntime | None) -> Any:
    if runtime is None:
        return config
    if not config.mcp_enabled:
        raise BackendInitializationError(f"Docker {runtime.backend} requires ActBench MCP")
    port = config.mcp_port
    if config.mcp_autostart and "ACTBENCH_MCP_PORT" not in os.environ:
        with socket.socket() as sock:
            sock.bind((config.mcp_host, 0))
            port = sock.getsockname()[1]
    public = os.environ.get("ACTBENCH_MCP_URL", f"http://{runtime.backend_host}:{port}/mcp")
    validate_container_url(public)
    return replace(config, docker_runtime=runtime, mcp_port=port, mcp_public_url=public)


def isolated_env(home: Path, runtime: DockerRuntime) -> dict[str, str]:
    """Only explicit provider variables and attempt-owned writable directories."""
    env = dict(runtime.target_env)
    env.update(HOME=str(home), NO_COLOR="1", CI="1", TERM="dumb")
    for kind in ("config", "data", "state", "cache"):
        directory = home / kind
        directory.mkdir(parents=True, exist_ok=True)
        env[f"XDG_{kind.upper()}_HOME"] = str(directory)
    bypass = ",".join(("localhost", "127.0.0.1", "::1", runtime.backend_host))
    env.update(NO_PROXY=bypass, no_proxy=bypass)
    return env


def load_provider(runtime, model: str) -> dict:
    path = os.environ.get("ACTBENCH_DOCKER_PROVIDER_CONFIG", "").strip()
    if not path:
        raise BackendInitializationError(
            f"Docker {runtime.backend} requires ACTBENCH_DOCKER_PROVIDER_CONFIG; "
            "see config/docker.provider.example.json"
        )
    data = json.loads(Path(path).expanduser().read_text())
    key_env = data.get("api_key_env", "")
    if key_env not in runtime.env_names or not runtime.target_env.get(key_env):
        raise BackendInitializationError(
            "Provider api_key_env must be selected in ACTBENCH_DOCKER_ENV"
        )
    runtime.register_secret(runtime.target_env[key_env])
    url = data.get("base_url", "")
    if not isinstance(url, str) or not url.startswith(("https://", "http://")):
        raise BackendInitializationError("Provider base_url must be an HTTP(S) URL")
    provider, sep, model_id = model.partition("/")
    if not sep or not re.fullmatch(r"[A-Za-z0-9_-]+", provider) or not model_id:
        raise BackendInitializationError("Use --model provider/model with Docker service agents")
    return {
        "base_url": url.rstrip("/"),
        "api_key_env": key_env,
        "provider": provider,
        "model": model_id,
    }
