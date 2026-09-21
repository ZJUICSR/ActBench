"""Docker subprocess execution for a single target-agent attempt.

Only the materialized workspace and attempt HOME are mounted. Host paths are
preserved inside the container so recorded file operations need no rewriting.
The controller, mock services, artifacts and graders remain on the host.
"""

from __future__ import annotations

import atexit
from contextlib import contextmanager
import hashlib
import json
import os
import re
import signal
import subprocess
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from urllib.request import ProxyHandler, build_opener

from benchmark.backends.base import BackendInitializationError

DEFAULT_IMAGE = "actbench-opencode:1.17.18"
DEFAULT_IMAGES = {
    "opencode": DEFAULT_IMAGE,
    "claudecode": "actbench-claudecode:2.1.268",
    "hermes": "actbench-hermes:0.18.2",
    "openclaw": "actbench-openclaw:2026.5.18",
    "qwenpaw": "actbench-qwenpaw:1.1.11.post2",
    "openagent": "actbench-openagent:2.83.1",
}


def image_for_backend(backend: str) -> str:
    return os.environ.get(f"ACTBENCH_DOCKER_{backend.upper()}_IMAGE") or os.environ.get(
        "ACTBENCH_DOCKER_IMAGE", DEFAULT_IMAGES[backend]
    )


_ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_HOST_ENV = {
    "PATH",
    "HOME",
    "DOCKER_HOST",
    "DOCKER_CONTEXT",
    "DOCKER_CONFIG",
    "DOCKER_TLS_VERIFY",
    "DOCKER_CERT_PATH",
    "XDG_RUNTIME_DIR",
    "SSH_AUTH_SOCK",
    "LANG",
    "LC_ALL",
    "SSL_CERT_FILE",
    "SSL_CERT_DIR",
}
_LITERAL_ENV = {
    "HOME",
    "XDG_CONFIG_HOME",
    "XDG_DATA_HOME",
    "XDG_STATE_HOME",
    "XDG_CACHE_HOME",
    "OPENCODE_CONFIG_DIR",
    "OPENCODE_DB",
    "TMPDIR",
}


def _mount(path: Path, *, destination: str | None = None) -> str:
    source = str(path.resolve(strict=True))
    target = destination or source
    if any(c in source + target for c in ",\n\r\x00") or not target.startswith("/"):
        raise ValueError("Docker bind paths must be absolute and contain no commas or newlines")
    return f"type=bind,src={source},dst={target}"


class DockerRuntime:
    """Pin an image once per run; remove only containers created by this instance."""

    def __init__(self, *, records_dir: Path, backend: str = "opencode") -> None:
        self.records_dir = records_dir.resolve()
        self.backend = backend
        self.binary = os.environ.get("ACTBENCH_DOCKER_BIN", "docker")
        self.image = image_for_backend(backend)
        self.backend_host = os.environ.get("ACTBENCH_DOCKER_HOST_ADDRESS", "host.docker.internal")
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", self.backend_host):
            raise BackendInitializationError(
                "ACTBENCH_DOCKER_HOST_ADDRESS must be a hostname or IPv4 address"
            )
        self.bind_host = os.environ.get("ACTBENCH_DOCKER_MCP_BIND_HOST", "0.0.0.0")
        self.env_names = tuple(
            filter(
                None,
                (part.strip() for part in os.environ.get("ACTBENCH_DOCKER_ENV", "").split(",")),
            )
        )
        for name in self.env_names:
            if (
                not _ENV_NAME.fullmatch(name)
                or name.startswith(("DOCKER_", "ACTBENCH_"))
                or name in _HOST_ENV
                or name in _LITERAL_ENV
                or name in {"PYTHONPATH", "LD_PRELOAD", "LD_LIBRARY_PATH"}
            ):
                raise BackendInitializationError(f"Invalid target environment variable: {name!r}")
            if name not in os.environ:
                raise BackendInitializationError(
                    f"Requested target environment variable is unset: {name}"
                )
        self.target_env = {name: os.environ[name] for name in self.env_names}
        proxy = os.environ.get("ACTBENCH_DOCKER_PROXY_URL", "").strip()
        if proxy:
            if urlsplit(proxy).scheme not in {"http", "https"}:
                raise BackendInitializationError(
                    "ACTBENCH_DOCKER_PROXY_URL must be an HTTP(S) proxy URL"
                )
            self.target_env.update(
                {name: proxy for name in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy")}
            )
        self.host_env = {name: value for name, value in os.environ.items() if name in _HOST_ENV}
        self.owner = uuid.uuid4().hex
        self._active: set[str] = set()
        self._lock = threading.RLock()
        self._closed = False
        self._previous_signals: dict[int, Any] = {}
        self._secret_values = [
            value
            for name, value in self.target_env.items()
            if value and re.search(r"KEY|TOKEN|SECRET|PASSWORD|AUTH", name, re.I)
        ]
        try:
            info = json.loads(self._control(["info", "--format", "{{json .}}"], check=True).stdout)
            security = info.get("SecurityOptions")
            if not isinstance(security, list) or info.get("OSType") != "linux":
                raise ValueError("a Linux Docker daemon with readable SecurityOptions is required")
            self.rootless = any("rootless" in str(option) for option in security)
            self.user = os.environ.get("ACTBENCH_DOCKER_USER") or (
                "0:0" if self.rootless else f"{os.getuid()}:{os.getgid()}"
            )
            if not re.fullmatch(r"\d+(?::\d+)?", self.user):
                raise ValueError("ACTBENCH_DOCKER_USER must be a numeric UID[:GID]")
            image = json.loads(self._control(["image", "inspect", self.image], check=True).stdout)[
                0
            ]
            self.image_id = image["Id"]
            if not re.fullmatch(r"sha256:[0-9a-f]{64}", self.image_id):
                raise ValueError("Docker did not return an immutable image ID")
            self.image_digests = image.get("RepoDigests") or []
            self.server_version = info.get("ServerVersion")
            self.cgroup_version = str(info.get("CgroupVersion", ""))
        except (OSError, ValueError, KeyError, IndexError, subprocess.SubprocessError) as exc:
            detail = self.redact(
                str(getattr(exc, "stderr", None) or getattr(exc, "stdout", None) or exc)
            ).strip()
            raise BackendInitializationError(
                f"Docker preflight failed: {detail}. Enable a Linux Docker daemon and run "
                f"'deeptrap docker-build --backend {self.backend}' first; no local-agent fallback is used."
            ) from exc
        self.limits = {
            flag: os.environ[name]
            for flag, name in (
                ("--cpus", "ACTBENCH_DOCKER_CPUS"),
                ("--memory", "ACTBENCH_DOCKER_MEMORY"),
                ("--pids-limit", "ACTBENCH_DOCKER_PIDS_LIMIT"),
            )
            if os.environ.get(name)
        }
        if self.limits and self.rootless and self.cgroup_version != "2":
            raise BackendInitializationError("Rootless Docker resource limits require cgroup v2")
        self.records_dir.mkdir(parents=True, exist_ok=True)
        (self.records_dir / "runtime.json").write_text(json.dumps(self.metadata(), indent=2) + "\n")
        atexit.register(self.close)
        if threading.current_thread() is threading.main_thread():
            for signum in (signal.SIGINT, signal.SIGTERM):
                self._previous_signals[signum] = signal.getsignal(signum)
                signal.signal(signum, self._on_signal)

    def _control(self, args: list[str], *, check: bool = False) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [self.binary, *args],
            env=self.host_env,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=30,
            check=check,
        )

    def redact(self, value: str) -> str:
        for secret in sorted(self._secret_values, key=len, reverse=True):
            value = value.replace(secret, "[REDACTED]")
        return value

    def register_secret(self, value: str) -> None:
        if value and value not in self._secret_values:
            self._secret_values.append(value)

    def redact_value(self, value: Any) -> Any:
        """Apply the same credential redaction to HTTP and native-file transcripts."""
        if isinstance(value, str):
            return self.redact(value)
        if isinstance(value, dict):
            return {key: self.redact_value(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self.redact_value(item) for item in value]
        return value

    def metadata(self) -> dict[str, Any]:
        return {
            "backend": self.backend,
            "image": self.image,
            "image_id": self.image_id,
            "repo_digests": self.image_digests,
            "owner": self.owner,
            "server_version": self.server_version,
            "rootless": self.rootless,
            "user": self.user,
            "cgroup_version": self.cgroup_version,
            "read_only_rootfs": True,
            "network": "bridge",
            "backend_host": self.backend_host,
            "environment_names": sorted(self.target_env),
            "resource_limits": dict(self.limits),
        }

    def identity(self, *, providers: dict[str, Any] | None = None) -> str:
        # Exclude invocation owner and credentials. A retagged image or changed
        # provider definition must never reuse a prior benign baseline.
        value = {
            "image_id": self.image_id,
            "providers": providers,
            "user": self.user,
            "limits": self.limits,
            "environment_names": self.env_names,
            "environment_values": {
                key: value
                for key, value in self.target_env.items()
                if value not in self._secret_values
                and not re.search(r"KEY|TOKEN|SECRET|PASSWORD|AUTH", key, re.I)
            },
        }
        return "docker-" + hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()

    def command(
        self,
        argv: list[str],
        *,
        workspace: Path,
        home: Path,
        env: dict[str, str],
        name: str,
        interactive: bool = False,
        service_port: int | None = None,
    ) -> tuple[list[str], dict[str, str]]:
        workspace, home = workspace.resolve(strict=True), home.resolve(strict=True)
        if workspace == home or workspace.is_relative_to(home) or home.is_relative_to(workspace):
            raise ValueError("Docker workspace and attempt HOME must be separate directories")
        command = [
            self.binary,
            "run",
            "--rm",
            "--init",
            "--pull",
            "never",
            "--name",
            name,
            "--label",
            "actbench.managed=1",
            "--label",
            f"actbench.owner={self.owner}",
            "--read-only",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--network",
            "bridge",
            "--user",
            self.user,
            "--workdir",
            str(workspace),
            "--mount",
            _mount(workspace),
            "--mount",
            _mount(home),
            "--tmpfs",
            "/tmp:rw,nosuid,nodev,mode=1777,size=512m",
        ]
        if self.backend_host == "host.docker.internal":
            command.extend(["--add-host", "host.docker.internal:host-gateway"])
        if interactive:
            command.append("--interactive")
        if service_port is not None:
            command.extend(["--publish", f"127.0.0.1::{service_port}"])
        for flag, value in self.limits.items():
            command.extend([flag, value])
        # Explicit runtime fields plus explicitly selected provider variables.
        # Docker control credentials remain in the host CLI environment only.
        host_env = dict(self.host_env)
        values = {**self.target_env, **env}
        for key, value in sorted(values.items()):
            if (
                not _ENV_NAME.fullmatch(key)
                or key.startswith("DOCKER_")
                or key == "ACTBENCH_MCP_ADMIN_TOKEN"
            ):
                raise ValueError(f"Invalid container environment variable: {key!r}")
            if key in _LITERAL_ENV:
                command.extend(["--env", f"{key}={value}"])
            else:
                command.extend(["--env", key])
                host_env[key] = value
        command.extend(["--entrypoint", argv[0], self.image_id, *argv[1:]])
        return command, host_env

    def run(
        self,
        argv: list[str],
        *,
        workspace: Path,
        home: Path,
        env: dict[str, str],
        timeout_seconds: float,
        records: list[dict[str, Any]],
        purpose: str = "agent",
        input_text: str | None = None,
    ) -> subprocess.CompletedProcess[str]:
        name = f"actbench-{self.owner[:12]}-{uuid.uuid4().hex[:12]}"
        command, host_env = self.command(
            argv,
            workspace=workspace,
            home=home,
            env=env,
            name=name,
            interactive=input_text is not None,
        )
        record: dict[str, Any] = {
            "schema_version": "actbench.docker_execution.v1",
            "owner": self.owner,
            "container_name": name,
            "purpose": purpose,
            "image_id": self.image_id,
            "cleanup": "pending",
        }
        records.append(record)
        record_path = self.records_dir / f"{name}.json"
        record_path.write_text(json.dumps(record, indent=2) + "\n")
        process = None
        timed_out = False
        # File-backed output also handles large opencode export payloads.
        with (
            tempfile.TemporaryFile(mode="w+", encoding="utf-8") as out,
            tempfile.TemporaryFile(mode="w+", encoding="utf-8") as err,
            tempfile.TemporaryFile(mode="w+", encoding="utf-8") as inp,
        ):
            if input_text is not None:
                inp.write(input_text)
                inp.seek(0)
            try:
                with self._lock:
                    if self._closed:
                        raise RuntimeError("Docker execution was cancelled")
                    self._active.add(name)
                    process = subprocess.Popen(
                        command,
                        env=host_env,
                        stdin=inp if input_text is not None else subprocess.DEVNULL,
                        stdout=out,
                        stderr=err,
                        start_new_session=True,
                    )
                try:
                    process.wait(timeout=timeout_seconds)
                except subprocess.TimeoutExpired:
                    timed_out = True
            finally:
                try:
                    self._remove(name)
                    record["cleanup"] = "removed"
                except Exception:
                    record["cleanup"] = "failed"
                    raise
                finally:
                    if process is not None and process.poll() is None:
                        try:
                            os.killpg(process.pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                        process.wait(timeout=5)
                    record_path.write_text(json.dumps(record, indent=2) + "\n")
            out.seek(0)
            err.seek(0)
            stdout, stderr = self.redact(out.read()), self.redact(err.read())
        record.update(exit_code=process.returncode, timed_out=timed_out)
        record_path.write_text(json.dumps(record, indent=2) + "\n")
        if timed_out:
            raise subprocess.TimeoutExpired(argv[:1], timeout_seconds, output=stdout, stderr=stderr)
        return subprocess.CompletedProcess(argv, process.returncode, stdout, stderr)

    @contextmanager
    def service(
        self,
        argv: list[str],
        *,
        workspace: Path,
        home: Path,
        env: dict[str, str],
        port: int,
        health_path: str,
        records: list[dict[str, Any]],
        timeout_seconds: float = 120,
    ):
        """Keep one attempt's service alive; publish only on host loopback.

        The caller's task timeout bounds requests after readiness. Every exit,
        including failed startup or cancelled requests, removes this container.
        """
        name = f"actbench-{self.owner[:12]}-{uuid.uuid4().hex[:12]}"
        command, host_env = self.command(
            argv, workspace=workspace, home=home, env=env, name=name, service_port=port
        )
        record = {
            "schema_version": "actbench.docker_execution.v1",
            "owner": self.owner,
            "container_name": name,
            "purpose": "agent-service",
            "image_id": self.image_id,
            "cleanup": "pending",
        }
        records.append(record)
        record_path = self.records_dir / f"{name}.json"
        record_path.write_text(json.dumps(record, indent=2) + "\n")
        process = None
        started = time.monotonic()
        opener = build_opener(ProxyHandler({}))
        with tempfile.TemporaryFile(mode="w+", encoding="utf-8") as logs:
            try:
                with self._lock:
                    if self._closed:
                        raise RuntimeError("Docker execution was cancelled")
                    self._active.add(name)
                    process = subprocess.Popen(
                        command,
                        env=host_env,
                        stdin=subprocess.DEVNULL,
                        stdout=logs,
                        stderr=logs,
                        start_new_session=True,
                    )
                base_url = None
                while time.monotonic() - started < timeout_seconds:
                    if process.poll() is not None:
                        logs.seek(0)
                        raise RuntimeError(
                            "Agent service exited during startup: "
                            + self.redact(logs.read()[-6000:])
                        )
                    if base_url is None:
                        mapped = self._control(["port", name, f"{port}/tcp"])
                        match = re.fullmatch(r"127\.0\.0\.1:(\d+)", mapped.stdout.strip())
                        if match:
                            base_url = "http://" + match.group(0)
                    if base_url:
                        try:
                            with opener.open(base_url + health_path, timeout=1) as response:
                                if response.status == 200:
                                    break
                        except OSError:
                            pass
                    time.sleep(0.2)
                else:
                    raise TimeoutError(
                        f"{self.backend} service did not become ready in {timeout_seconds}s"
                    )
                record["ready"] = True
                yield base_url
            finally:
                try:
                    self._remove(name)
                    record["cleanup"] = "removed"
                except Exception:
                    record["cleanup"] = "failed"
                    raise
                finally:
                    if process is not None and process.poll() is None:
                        try:
                            os.killpg(process.pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                        process.wait(timeout=5)
                    logs.seek(0)
                    (self.records_dir / f"{name}.log").write_text(self.redact(logs.read()))
                    record_path.write_text(json.dumps(record, indent=2) + "\n")

    def _remove(self, name: str) -> None:
        result = self._control(["rm", "--force", name])
        if result.returncode:
            # Normal --rm completion races with cleanup. Only a successful,
            # empty query proves removal; daemon failures are not success.
            remaining = self._control(
                [
                    "ps",
                    "--all",
                    "--quiet",
                    "--filter",
                    f"name=^/{name}$",
                    "--filter",
                    f"label=actbench.owner={self.owner}",
                ],
                check=True,
            )
            if remaining.stdout.strip():
                raise RuntimeError(
                    f"Could not remove Docker container {name}: {result.stderr.strip()}"
                )
        with self._lock:
            self._active.discard(name)

    def _on_signal(self, signum: int, frame: Any) -> None:
        try:
            self.close()
        finally:
            raise SystemExit(128 + signum)

    def close(self) -> None:
        with self._lock:
            self._closed = True
            names = list(self._active)
        errors = []
        try:
            for name in names:
                try:
                    self._remove(name)
                except Exception as exc:
                    errors.append(f"{name}: {self.redact(str(exc))}")
            if errors:
                raise RuntimeError("Docker cleanup failed: " + "; ".join(errors))
        finally:
            atexit.unregister(self.close)
            if threading.current_thread() is threading.main_thread():
                for signum, handler in self._previous_signals.items():
                    signal.signal(signum, handler)
                self._previous_signals.clear()


def validate_container_url(url: str) -> None:
    parsed = urlsplit(url)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.hostname in {"127.0.0.1", "localhost", "::1", "0.0.0.0"}
    ):
        raise BackendInitializationError(
            "Docker MCP URL must use a host address reachable from the container"
        )
