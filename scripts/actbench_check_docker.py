#!/usr/bin/env python3
"""Exercise the actual Docker image, host MCP, mock APIs and timeout cleanup.

No target model or judge is called. Failures are recorded, never substituted
with fake-backend results.
"""

from __future__ import annotations

import argparse
from dataclasses import replace
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from benchmark.backends.base import BackendRunContext
from benchmark.backends.opencode import OpenCodeBackend, _opencode_env
from benchmark.backends.claudecode import ClaudeCodeBackend, _claudecode_env, _write_mcp_config
from benchmark.backends.hermes import HermesBackend
from benchmark.backends.openagent import OpenAgentBackend, OpenAgentConfig
from benchmark.backends.docker_agents import (
    JsonApi,
    bootstrap_openagent,
    bootstrap_qwenpaw,
    prepare_openagent_home,
    prepare_openclaw_home,
)
from benchmark.docker_runtime import DockerRuntime, DEFAULT_IMAGES
from benchmark.docker_support import configure_mcp, isolated_env
from lib_api_services import start_api_services
from lib_mcp_gateway import register_gateway_context, unregister_gateway_context

PROBE = r"""
import json, os, pathlib, subprocess, urllib.error, urllib.request
url = os.environ["ACTBENCH_CHECK_MCP_URL"]
context = os.environ["ACTBENCH_CHECK_CONTEXT"]
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
def rpc(name, arguments):
    request = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
        "name": name, "arguments": {"context_id": context, **arguments}}}
    raw = json.dumps(request).encode()
    req = urllib.request.Request(url, data=raw, headers={"Content-Type": "application/json"})
    result = json.load(opener.open(req, timeout=15))
    assert not result.get("error"), result
    assert not result.get("result", {}).get("isError"), result
    return result
assert "ACTBENCH_CHECK_HOST_SECRET" not in os.environ
assert not pathlib.Path(os.environ["ACTBENCH_CHECK_HIDDEN_PATH"]).exists()
assert not pathlib.Path("/var/run/docker.sock").exists()
assert pathlib.Path("marker.txt").read_text() == "input\n"
pathlib.Path("native-output.txt").write_text("native write\n")
pathlib.Path(os.environ["HOME"], "home-output.txt").write_text("home write\n")
try:
    pathlib.Path("/actbench-root-write").write_text("must fail")
except OSError:
    pass
else:
    raise AssertionError("container root filesystem is writable")
rpc("actbench_write_file", {"path": "mcp-output.txt", "content": "MCP write\n"})
rpc("actbench_call_api", {"service": "taskboard", "method": "POST", "path": "/taskboard/tasks", "body": {}})
direct = urllib.request.Request(os.environ["ACTBENCH_CHECK_BUSINESS_URL"], data=b"{}",
    headers={"Content-Type": "application/json"})
with opener.open(direct, timeout=10) as response:
    assert response.status == 200
try:
    opener.open(url.rsplit("/mcp", 1)[0] + "/admin/health", timeout=10)
except urllib.error.HTTPError as exc:
    assert exc.code == 401, exc.code
else:
    raise AssertionError("MCP admin endpoint is accessible without its token")
try:
    opener.open(os.environ["ACTBENCH_CHECK_RAW_AUDIT_URL"], timeout=5)
except urllib.error.HTTPError as exc:
    assert exc.code == 401, exc.code
except (urllib.error.URLError, TimeoutError):
    pass  # Rootful bridge networking may make the loopback-only service unreachable.
else:
    raise AssertionError("Mock audit endpoint is accessible without its token")
version = subprocess.check_output(json.loads(os.environ["ACTBENCH_CHECK_VERSION_COMMAND"]), text=True).strip()
config_command = json.loads(os.environ.get("ACTBENCH_CHECK_CONFIG_COMMAND", "[]"))
if config_command:
    config = subprocess.run(config_command, capture_output=True, text=True, timeout=60)
    assert config.returncode == 0, config.stderr
print(json.dumps({"agent_version": version, "uid": os.getuid(), "mcp": "passed",
                  "direct_mock_api": "passed",
                  "workspace": "passed", "home": "passed", "host_files_hidden": True,
                  "rootfs_read_only": True, "admin_endpoints_protected": True,
                  "provider_config": "parsed" if config_command else "not_required"}))
"""


def check(output: Path, backend_name: str = "opencode") -> dict:
    output.mkdir(parents=True, exist_ok=False)
    report: dict = {
        "schema_version": "actbench.docker_check.v1",
        "status": "failed",
        "model_invoked": False,
        "checks": {},
    }
    backend = OpenAgentBackend()
    runtime = None
    records = []
    group = None
    context_id = None
    config = None
    with tempfile.TemporaryDirectory(prefix="actbench-docker-check-") as temporary:
        root = Path(temporary)
        workspace = root / "workspace"
        workspace.mkdir()
        (workspace / "marker.txt").write_text("input\n")
        hidden = root / "controller-only.txt"
        hidden.write_text("controller sentinel\n")
        context = BackendRunContext(
            backend=backend_name,
            model="check/no-model",
            run_id=uuid.uuid4().hex,
            run_root=root,
            skill_dir=root,
            agent_id="docker-check",
            agent_workspace=root / "agent",
            timeout_multiplier=1,
            metadata={"execution": "docker", "docker_records_dir": str(output)},
        )
        previous = os.environ.get("ACTBENCH_CHECK_HOST_SECRET")
        os.environ["ACTBENCH_CHECK_HOST_SECRET"] = "host-only-sentinel"
        try:
            runtime = DockerRuntime(records_dir=output, backend=backend_name)
            home = root / "attempt-home"
            home.mkdir()
            config = configure_mcp(
                OpenAgentConfig(
                    base_url="http://127.0.0.1",
                    endpoint="/api/v1/chat/completions",
                    api_key="unused",
                    timeout_seconds=None,
                    mcp_enabled=True,
                    mcp_autostart=True,
                    mcp_host="127.0.0.1",
                    mcp_port=8765,
                    mcp_public_url="",
                    mcp_admin_token=secrets.token_urlsafe(32),
                ),
                runtime,
            )
            backend._initialize_mcp_gateway(config)
            report["runtime"] = runtime.metadata()
            env = isolated_env(home, runtime)
            versions = {
                "opencode": ["opencode", "--version"],
                "claudecode": ["claude", "--version"],
                "hermes": ["hermes", "version"],
                "openclaw": ["openclaw", "--version"],
                "qwenpaw": ["qwenpaw", "--version"],
                "openagent": ["openagent", "version"],
            }
            env["ACTBENCH_CHECK_VERSION_COMMAND"] = json.dumps(versions[backend_name])
            provider = {
                "base_url": "https://invalid.example/v1",
                "api_key_env": "CHECK_PROVIDER_KEY",
                "provider": "check",
                "model": "no-model",
            }
            runtime.target_env["CHECK_PROVIDER_KEY"] = "check-only-not-a-real-key"
            env["CHECK_PROVIDER_KEY"] = runtime.target_env["CHECK_PROVIDER_KEY"]
            if backend_name == "opencode":
                native = OpenCodeBackend()
                native._docker = runtime
                native_config = replace(
                    native._load_config(context),
                    opencode_home=home,
                    mcp_port=config.mcp_port,
                    mcp_public_url=config.mcp_public_url,
                )
                native._prepare_opencode_home(native_config)
                env.update(_opencode_env(native_config))
                env["ACTBENCH_CHECK_CONFIG_COMMAND"] = json.dumps(["opencode", "debug", "config"])
            elif backend_name == "claudecode":
                native = ClaudeCodeBackend()
                native._docker = runtime
                native_config = replace(
                    native._load_config(context),
                    claudecode_home=home,
                    docker_runtime=runtime,
                    mcp_port=config.mcp_port,
                    mcp_public_url=config.mcp_public_url,
                )
                native._prepare_claudecode_home(native_config)
                _write_mcp_config(native_config, session_id="check")
                env.update(_claudecode_env(native_config))
            elif backend_name == "hermes":
                native = HermesBackend()
                native._docker = runtime
                native_config = replace(
                    native._load_config(context),
                    hermes_home=home,
                    docker_runtime=runtime,
                    mcp_port=config.mcp_port,
                    mcp_public_url=config.mcp_public_url,
                )
                native._write_hermes_config(native_config)
                env["HERMES_HOME"] = str(home)
            elif backend_name == "openclaw":
                path = prepare_openclaw_home(home, workspace, context, provider)
                env.update(
                    OPENCLAW_STATE_DIR=str(home / ".openclaw"), OPENCLAW_CONFIG_PATH=str(path)
                )
                env["ACTBENCH_CHECK_CONFIG_COMMAND"] = json.dumps(
                    ["openclaw", "config", "validate", "--json"]
                )
            group = start_api_services(
                services=["taskboard"],
                run_id=context.run_id,
                attempt_id="docker-check",
                workspace=None,
                protect_admin=True,
                bind_host=runtime.bind_host,
            )
            context_id = secrets.token_urlsafe(32)
            register_gateway_context(
                mcp_url=config.mcp_admin_url,
                context_id=context_id,
                workspace=workspace,
                api_endpoints=group.endpoints,
                ttl_seconds=180,
                admin_token=config.mcp_admin_token,
            )
            env.update(
                ACTBENCH_CHECK_MCP_URL=config.mcp_public_url,
                ACTBENCH_CHECK_CONTEXT=context_id,
                ACTBENCH_CHECK_HIDDEN_PATH=str(hidden),
                ACTBENCH_CHECK_BUSINESS_URL=group.endpoints["taskboard"]["base_url"].replace(
                    "127.0.0.1", runtime.backend_host
                )
                + "/taskboard/tasks",
                ACTBENCH_CHECK_RAW_AUDIT_URL=group.endpoints["taskboard"]["audit"].replace(
                    "127.0.0.1", runtime.backend_host
                ),
            )
            completed = runtime.run(
                ["python3", "-c", PROBE],
                workspace=workspace,
                home=home,
                env=env,
                timeout_seconds=90,
                records=records,
                purpose="runtime_check",
            )
            if completed.returncode:
                raise RuntimeError(
                    runtime.redact(completed.stderr).replace(context_id, "[REDACTED]")
                )
            report["checks"].update(json.loads(completed.stdout))
            assert (workspace / "native-output.txt").read_text() == "native write\n"
            assert (workspace / "mcp-output.txt").read_text() == "MCP write\n"
            audit = group.collect_audit()["taskboard"]
            assert audit.get("calls"), "Mock API audit did not record the container request"
            report["checks"]["host_audit"] = "passed"
            if backend_name in {"qwenpaw", "openagent"}:
                service_env = isolated_env(home, runtime)
                if backend_name == "qwenpaw":
                    service_env.update(
                        QWENPAW_WORKING_DIR=str(home / "qwenpaw"),
                        QWENPAW_SECRET_DIR=str(home / "secrets"),
                        QWENPAW_BACKUP_DIR=str(home / "backups"),
                    )
                    command, port, health = (
                        ["qwenpaw", "app", "--host", "0.0.0.0", "--port", "8088"],
                        8088,
                        "/api/version",
                    )
                else:
                    prepare_openagent_home(home)
                    command, port, health = (
                        ["sh", "-c", 'cd "$HOME" && exec openagent serve'],
                        14000,
                        "/api/health",
                    )
                with runtime.service(
                    command,
                    workspace=workspace,
                    home=home,
                    env=service_env,
                    port=port,
                    health_path=health,
                    records=records,
                ) as url:
                    if backend_name == "qwenpaw":
                        bootstrap_qwenpaw(url, provider, runtime)
                        created = JsonApi(url).call(
                            "/api/agents",
                            {
                                "id": "actbench-docker-check",
                                "name": "ActBench Docker check",
                                "workspace_dir": str(workspace),
                                "skill_names": [],
                                "active_model": {"provider_id": "check", "model": "no-model"},
                            },
                        )
                        assert created["id"] == "actbench-docker-check"
                        assert (workspace / "sessions").is_dir()
                        report["checks"]["native_agent_workspace"] = "passed"
                    else:
                        bootstrap_openagent(url, provider, runtime, config.mcp_public_url)
                assert records[-1]["cleanup"] == "removed"
                report["checks"]["fresh_service_bootstrap"] = "passed"
            try:
                runtime.run(
                    ["python3", "-c", "import time; print('started', flush=True); time.sleep(60)"],
                    workspace=workspace,
                    home=home,
                    env=env,
                    timeout_seconds=2,
                    records=records,
                    purpose="timeout_check",
                )
            except subprocess.TimeoutExpired:
                assert records[-1]["cleanup"] == "removed"
                report["checks"]["timeout_cleanup"] = "passed"
            else:
                raise RuntimeError("Timeout probe unexpectedly completed")
            report["status"] = "passed"
        except Exception as exc:
            report["error"] = str(exc)
        finally:
            if previous is None:
                os.environ.pop("ACTBENCH_CHECK_HOST_SECRET", None)
            else:
                os.environ["ACTBENCH_CHECK_HOST_SECRET"] = previous
            if context_id and config:
                try:
                    unregister_gateway_context(
                        mcp_url=config.mcp_admin_url,
                        context_id=context_id,
                        admin_token=config.mcp_admin_token,
                    )
                except Exception as exc:
                    report.update(status="failed", cleanup_error=str(exc))
            if group:
                group.stop()
            try:
                backend.finalize_run(context)
            except Exception as exc:
                report.update(status="failed", cleanup_error=str(exc))
            if runtime:
                try:
                    runtime.close()
                except Exception as exc:
                    report.update(status="failed", cleanup_error=str(exc))
            report["executions"] = records
            (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, default=None, help="Fresh directory for check evidence"
    )
    parser.add_argument("--backend", choices=tuple(DEFAULT_IMAGES), default="opencode")
    args = parser.parse_args()
    output = args.output or Path("results/docker_checks") / (
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    )
    report = check(output.resolve(), args.backend)
    print(
        json.dumps(
            {
                "status": report["status"],
                "report": str(output / "report.json"),
                "error": report.get("error"),
            },
            indent=2,
        )
    )
    if report["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
