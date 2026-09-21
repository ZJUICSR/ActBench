from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import json
import os
from pathlib import Path
import signal
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from benchmark.backends.base import BackendInitializationError, BackendRunContext  # noqa: E402
from benchmark.backends.opencode import (  # noqa: E402
    OpenCodeBackend,
    _opencode_env,
    _opencode_config_payload,
)
from benchmark.baseline import baseline_cache_backend, _baseline_cache_path  # noqa: E402
from benchmark.docker_runtime import DockerRuntime, validate_container_url  # noqa: E402
from benchmark.one_click import parse_args, resolve_run_plan, build_collection_command  # noqa: E402
from lib_tasks import TaskLoader  # noqa: E402
from scripts.actbench_build_docker import stage_context  # noqa: E402

IMAGE_ID = "sha256:" + "a" * 64


@pytest.fixture
def runtime_factory(monkeypatch, tmp_path):
    for name in list(os.environ):
        if name.startswith(("ACTBENCH_DOCKER_", "ACTBENCH_OPENCODE_", "ACTBENCH_MCP_")):
            monkeypatch.delenv(name)
    created = []
    calls = []

    def make(*, rootless=False, image_id=IMAGE_ID, backend="opencode"):
        def control(self, args, *, check=False):
            calls.append(args)
            if args[0] == "info":
                value = {
                    "SecurityOptions": ["name=rootless"] if rootless else ["name=seccomp"],
                    "OSType": "linux",
                    "ServerVersion": "27.5.0",
                    "CgroupVersion": "2",
                }
            elif args[:2] == ["image", "inspect"]:
                value = [{"Id": image_id, "RepoDigests": []}]
            else:
                return subprocess.CompletedProcess(args, 0, "", "")
            return subprocess.CompletedProcess(args, 0, json.dumps(value), "")

        monkeypatch.setattr(DockerRuntime, "_control", control)
        runtime = DockerRuntime(records_dir=tmp_path / f"records-{len(created)}", backend=backend)
        created.append(runtime)
        return runtime

    yield make, calls
    for runtime in reversed(created):
        runtime.close()


def _paths(tmp_path):
    workspace, home = tmp_path / "workspace with spaces", tmp_path / "attempt-home"
    workspace.mkdir(exist_ok=True)
    home.mkdir(exist_ok=True)
    return workspace, home


def test_only_attempt_mounts_and_selected_environment_reach_container(
    runtime_factory, monkeypatch, tmp_path
):
    make, _ = runtime_factory
    monkeypatch.setenv("TARGET_API_KEY", "secret-value")
    monkeypatch.setenv("UNRELATED_JUDGE_TOKEN", "host-only")
    monkeypatch.setenv("ACTBENCH_MCP_ADMIN_TOKEN", "admin-secret")
    monkeypatch.setenv("ACTBENCH_DOCKER_ENV", "TARGET_API_KEY")
    runtime = make()
    workspace, home = _paths(tmp_path)
    command, env = runtime.command(
        ["opencode", "run", "a prompt; $(ignored)"],
        workspace=workspace,
        home=home,
        env={"HOME": str(home)},
        name="actbench-probe",
    )
    assert command[-4:] == ["opencode", IMAGE_ID, "run", "a prompt; $(ignored)"]
    assert "secret-value" not in " ".join(command)
    assert env["TARGET_API_KEY"] == "secret-value"
    assert "UNRELATED_JUDGE_TOKEN" not in env
    assert "ACTBENCH_MCP_ADMIN_TOKEN" not in env
    assert command.count("--mount") == 2
    mounts = [command[i + 1] for i, value in enumerate(command) if value == "--mount"]
    assert mounts == [
        f"type=bind,src={workspace},dst={workspace}",
        f"type=bind,src={home},dst={home}",
    ]
    assert "--read-only" in command and "--privileged" not in command
    assert command[command.index("--pull") + 1] == "never"
    assert runtime.redact("oops secret-value") == "oops [REDACTED]"
    assert runtime.redact_value({"transcript": [{"text": "native secret-value"}], "count": 1}) == {
        "transcript": [{"text": "native [REDACTED]"}],
        "count": 1,
    }


def test_materializing_service_workspace_preserves_the_bind_mount(tmp_path):
    from types import SimpleNamespace
    from benchmark.backends.common import materialize_task_workspace

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "stale").mkdir()
    (workspace / "stale" / "old.txt").write_text("old attempt")
    (workspace / "old-link").symlink_to(tmp_path)
    inode = workspace.stat().st_ino
    task = SimpleNamespace(
        workspace_files=[{"path": "input.txt", "content": "task data"}], frontmatter={}
    )
    materialize_task_workspace(
        workspace=workspace, skill_dir=tmp_path, task=task, preserve_directory=True
    )
    assert workspace.stat().st_ino == inode
    assert (workspace / "input.txt").read_text() == "task data"
    assert not (workspace / "stale").exists()
    assert not (workspace / "old-link").is_symlink()


@pytest.mark.parametrize(
    "name", ["DOCKER_HOST", "ACTBENCH_MCP_ADMIN_TOKEN", "HOME", "PATH", "LD_PRELOAD", "BAD-NAME"]
)
def test_container_passthrough_rejects_control_environment(runtime_factory, monkeypatch, name):
    make, _ = runtime_factory
    monkeypatch.setenv("ACTBENCH_DOCKER_ENV", name)
    with pytest.raises(BackendInitializationError):
        make()


def test_rootless_user_and_explicit_host_network_mapping(runtime_factory, monkeypatch, tmp_path):
    make, _ = runtime_factory
    monkeypatch.setenv("ACTBENCH_DOCKER_HOST_ADDRESS", "10.0.2.2")
    runtime = make(rootless=True)
    workspace, home = _paths(tmp_path)
    command, _ = runtime.command(["true"], workspace=workspace, home=home, env={}, name="probe")
    assert runtime.user == "0:0"
    assert "--add-host" not in command
    assert command[command.index("--network") + 1] == "bridge"


def test_image_lookup_failure_does_not_fall_back_to_local(monkeypatch, tmp_path):
    monkeypatch.delenv("ACTBENCH_DOCKER_ENV", raising=False)

    def failed(*args, **kwargs):
        raise subprocess.CalledProcessError(1, ["docker"], stderr="daemon unavailable")

    monkeypatch.setattr(DockerRuntime, "_control", failed)
    with pytest.raises(BackendInitializationError, match="daemon unavailable"):
        DockerRuntime(records_dir=tmp_path / "records")


def test_cleanup_does_not_treat_daemon_failure_as_success(runtime_factory, monkeypatch):
    make, _ = runtime_factory
    runtime = make()

    def failed(self, args, *, check=False):
        if check:
            raise subprocess.CalledProcessError(1, args, stderr="daemon unavailable")
        return subprocess.CompletedProcess(args, 1, "", "daemon unavailable")

    monkeypatch.setattr(DockerRuntime, "_control", failed)
    with pytest.raises(subprocess.CalledProcessError):
        runtime._remove("exact-attempt-name")


def test_timeout_retains_output_and_removes_only_its_container(
    runtime_factory, monkeypatch, tmp_path
):
    make, calls = runtime_factory
    runtime = make()
    workspace, home = _paths(tmp_path)
    original = subprocess.Popen

    def process(command, **kwargs):
        return original(
            [sys.executable, "-c", "import time; print('partial', flush=True); time.sleep(60)"],
            **kwargs,
        )

    monkeypatch.setattr(subprocess, "Popen", process)
    records = []
    with pytest.raises(subprocess.TimeoutExpired) as error:
        runtime.run(
            ["opencode", "run"],
            workspace=workspace,
            home=home,
            env={},
            timeout_seconds=0.15,
            records=records,
        )
    assert "partial" in error.value.output
    assert records[0]["cleanup"] == "removed"
    assert records[0]["timed_out"] is True
    assert ["rm", "--force", records[0]["container_name"]] in calls
    assert not runtime._active
    assert json.loads((runtime.records_dir / (records[0]["container_name"] + ".json")).read_text())[
        "timed_out"
    ]


def test_parallel_attempts_pin_same_image_but_have_unique_cleanup(
    runtime_factory, monkeypatch, tmp_path
):
    make, calls = runtime_factory
    runtime = make()
    workspace, home = _paths(tmp_path)
    original = subprocess.Popen
    monkeypatch.setattr(
        subprocess,
        "Popen",
        lambda command, **kwargs: original([sys.executable, "-c", "print('ok')"], **kwargs),
    )
    records = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda _: runtime.run(
                    ["opencode"],
                    workspace=workspace,
                    home=home,
                    env={},
                    timeout_seconds=5,
                    records=records,
                ),
                range(2),
            )
        )
    assert [result.stdout for result in results] == ["ok\n", "ok\n"]
    assert len({record["container_name"] for record in records}) == 2
    assert all(
        record["image_id"] == IMAGE_ID and record["cleanup"] == "removed" for record in records
    )


def test_opencode_uses_docker_for_run_and_export_without_host_executable(
    runtime_factory, monkeypatch, tmp_path
):
    make, _ = runtime_factory
    runtime = make()
    backend = OpenCodeBackend()
    backend._docker = runtime
    context = BackendRunContext(
        backend="opencode",
        model="test/model",
        run_id="r",
        run_root=tmp_path,
        skill_dir=ROOT,
        agent_id="a",
        agent_workspace=tmp_path / "agent",
        timeout_multiplier=1,
        metadata={"execution": "docker"},
    )
    import benchmark.backends.opencode as module

    monkeypatch.setattr(module, "_resolve_executable", lambda _: pytest.fail("host CLI was used"))
    config = backend._load_config(context)
    calls = []
    monkeypatch.setattr(
        runtime,
        "run",
        lambda argv, **kwargs: calls.append((argv, kwargs))
        or subprocess.CompletedProcess(argv, 0, "{}", ""),
    )
    workspace, home = _paths(tmp_path)
    config = replace(config, opencode_home=home)
    backend._run_opencode_subprocess(
        config=config, workspace=workspace, prompt="original prompt", timeout_seconds=10
    )
    backend._run_opencode_export(
        config=config, workspace=workspace, session_id="session-1", timeout_seconds=10
    )
    assert calls[0][0][-2:] == ["--", "original prompt"]
    assert calls[1][0] == ["opencode", "export", "session-1"]
    assert calls[1][1]["purpose"] == "transcript_export"
    assert calls[0][1]["home"] == calls[1][1]["home"] == home
    assert config.mcp_public_url.startswith("http://host.docker.internal:")
    assert "ACTBENCH_MCP_ADMIN_TOKEN" not in _opencode_env(config)


@pytest.mark.parametrize(
    "url", ["http://127.0.0.1:8765/mcp", "http://localhost:8765/mcp", "http://0.0.0.0/mcp"]
)
def test_loopback_mcp_addresses_are_rejected(url):
    with pytest.raises(BackendInitializationError):
        validate_container_url(url)


def test_docker_baseline_cache_is_separate_from_local_and_other_images(runtime_factory):
    make, _ = runtime_factory
    first = make()
    second = make(image_id="sha256:" + "b" * 64)
    task = TaskLoader(ROOT / "tasks").load_task(ROOT / "tasks/task_B9_T01")
    local = _baseline_cache_path(task, "provider/model", backend_name="opencode")
    docker = _baseline_cache_path(
        task,
        "provider/model",
        backend_name=baseline_cache_backend("opencode", {"runtime_identity": first.identity()}),
    )
    other = _baseline_cache_path(
        task,
        "provider/model",
        backend_name=baseline_cache_backend("opencode", {"runtime_identity": second.identity()}),
    )
    assert len({local, docker, other}) == 3
    assert baseline_cache_backend("opencode", {}) == "opencode"


@pytest.mark.parametrize(
    "backend", ["opencode", "claudecode", "hermes", "openclaw", "qwenpaw", "openagent"]
)
def test_one_click_propagates_docker_and_rejects_unsupported_backends(tmp_path, backend):
    config = parse_args(
        [
            "--backend",
            backend,
            "--execution",
            "docker",
            "--model",
            "test/model",
            "--score-mode",
            "automated",
            "--suite",
            "task_B9_T01",
        ]
    )
    command = build_collection_command(resolve_run_plan(config), tmp_path)
    assert command[command.index("--execution") + 1] == "docker"
    for args in (
        ["--self-test", "--execution", "docker"],
        [
            "--backend",
            "fake",
            "--execution",
            "docker",
            "--model",
            "test/model",
            "--score-mode",
            "automated",
        ],
    ):
        with pytest.raises(SystemExit):
            parse_args(args)


def test_build_context_contains_no_repo_data(tmp_path):
    stage_context(tmp_path)
    assert {path.name for path in tmp_path.iterdir()} == {"Dockerfile", ".dockerignore"}
    with pytest.raises(ValueError):
        stage_context(tmp_path)


@pytest.mark.parametrize("backend", ["claudecode", "hermes", "openclaw", "qwenpaw", "openagent"])
def test_other_images_have_explicit_minimal_build_context(tmp_path, backend):
    stage_context(tmp_path, backend)
    assert {p.name for p in tmp_path.iterdir()} == {"Dockerfile", ".dockerignore"}
    assert "COPY ." not in (tmp_path / "Dockerfile").read_text()


def test_backend_specific_image_overrides_global(runtime_factory, monkeypatch):
    make, _ = runtime_factory
    monkeypatch.setenv("ACTBENCH_DOCKER_IMAGE", "custom-global")
    monkeypatch.setenv("ACTBENCH_DOCKER_HERMES_IMAGE", "custom-hermes")
    assert make(backend="hermes").image == "custom-hermes"
    assert make(backend="claudecode").image == "custom-global"


def test_explicit_provider_credential_is_redacted_independent_of_variable_name(
    runtime_factory, monkeypatch, tmp_path
):
    from benchmark.docker_support import load_provider

    make, _ = runtime_factory
    monkeypatch.setenv("CUSTOM_CREDENTIAL", "provider-private-value")
    monkeypatch.setenv("ACTBENCH_DOCKER_ENV", "CUSTOM_CREDENTIAL")
    provider = tmp_path / "provider.json"
    provider.write_text(
        json.dumps({"api_key_env": "CUSTOM_CREDENTIAL", "base_url": "https://invalid.example/v1"})
    )
    monkeypatch.setenv("ACTBENCH_DOCKER_PROVIDER_CONFIG", str(provider))
    runtime = make(backend="qwenpaw")
    config = load_provider(runtime, "check/model")
    assert runtime.redact("service echoed provider-private-value") == "service echoed [REDACTED]"
    original_identity = runtime.identity(providers=config)
    runtime.target_env["CUSTOM_CREDENTIAL"] = "rotated-private-value"
    load_provider(runtime, "check/model")
    assert runtime.identity(providers=config) == original_identity


def test_stdin_is_forwarded_without_prompt_in_container_argv(
    runtime_factory, monkeypatch, tmp_path
):
    make, _ = runtime_factory
    runtime = make(backend="claudecode")
    workspace, home = _paths(tmp_path)
    original = subprocess.Popen
    commands = []

    def process(command, **kwargs):
        commands.append(command)
        return original([sys.executable, "-c", "import sys; print(sys.stdin.read())"], **kwargs)

    monkeypatch.setattr(subprocess, "Popen", process)
    prompt = "stdin-only prompt " * 10000
    result = runtime.run(
        ["claude", "-p"],
        workspace=workspace,
        home=home,
        env={},
        timeout_seconds=5,
        records=[],
        input_text=prompt,
    )
    assert result.stdout == prompt + "\n"
    assert "--interactive" in commands[0]
    assert prompt not in commands[0]


def test_service_cleanup_on_failed_request_and_loopback_publish(
    runtime_factory, monkeypatch, tmp_path
):
    import socket

    make, calls = runtime_factory
    runtime = make(backend="qwenpaw")
    workspace, home = _paths(tmp_path)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    control = runtime._control
    original = subprocess.Popen
    commands = []

    def process(command, **kwargs):
        commands.append(command)
        return original(
            [
                sys.executable,
                "-m",
                "http.server",
                str(port),
                "--bind",
                "127.0.0.1",
                "--directory",
                str(home),
            ],
            **kwargs,
        )

    def service_control(args, **kwargs):
        if args[0] == "port":
            return subprocess.CompletedProcess(args, 0, f"127.0.0.1:{port}\n", "")
        return control(args, **kwargs)

    monkeypatch.setattr(subprocess, "Popen", process)
    monkeypatch.setattr(runtime, "_control", service_control)
    records = []
    with pytest.raises(RuntimeError, match="request failed"):
        with runtime.service(
            ["qwenpaw", "app"],
            workspace=workspace,
            home=home,
            env={},
            port=8088,
            health_path="/",
            records=records,
            timeout_seconds=5,
        ) as url:
            assert url == f"http://127.0.0.1:{port}"
            assert records[0]["cleanup"] == "pending"
            raise RuntimeError("request failed")
    assert commands[0][commands[0].index("--publish") + 1] == "127.0.0.1::8088"
    assert records[0]["cleanup"] == "removed"
    assert not runtime._active
    assert ["rm", "--force", records[0]["container_name"]] in calls


def test_service_failed_start_is_cleaned_and_redacted(runtime_factory, monkeypatch, tmp_path):
    make, _ = runtime_factory
    monkeypatch.setenv("TEST_API_KEY", "secret-startup-value")
    monkeypatch.setenv("ACTBENCH_DOCKER_ENV", "TEST_API_KEY")
    runtime = make(backend="openagent")
    workspace, home = _paths(tmp_path)
    original = subprocess.Popen
    monkeypatch.setattr(
        subprocess,
        "Popen",
        lambda command, **kwargs: original(
            [sys.executable, "-c", "print('secret-startup-value'); raise SystemExit(2)"], **kwargs
        ),
    )
    records = []
    with pytest.raises(RuntimeError, match="exited during startup") as exc:
        with runtime.service(
            ["openagent"],
            workspace=workspace,
            home=home,
            env={},
            port=14000,
            health_path="/api/health",
            records=records,
            timeout_seconds=5,
        ):
            pytest.fail("failed process must never become ready")
    assert "secret-startup-value" not in str(exc.value)
    assert records[0]["cleanup"] == "removed"
    assert "secret-startup-value" not in next(runtime.records_dir.glob("*.log")).read_text()


@pytest.mark.parametrize("backend_name", ["hermes", "claudecode"])
def test_cli_docker_gateway_binds_publicly_but_admin_context_stays_private(
    runtime_factory, monkeypatch, tmp_path, backend_name
):
    from benchmark.backends.registry import get_backend
    import importlib

    module = importlib.import_module(f"benchmark.backends.{backend_name}")
    make, _ = runtime_factory
    runtime = make(backend=backend_name)
    monkeypatch.setattr(module, "initialize_runtime", lambda context: runtime)
    monkeypatch.setattr(
        module, "_resolve_executable", lambda value: pytest.fail("resolved host executable")
    )
    monkeypatch.setattr(
        module, "check_gateway_health", lambda **kw: (_ for _ in ()).throw(OSError())
    )
    started = []
    monkeypatch.setattr(module, "start_gateway_subprocess", lambda **kw: started.append(kw))
    context = BackendRunContext(
        backend=backend_name,
        model="check/model",
        run_id="run",
        run_root=tmp_path,
        skill_dir=tmp_path,
        agent_id="check",
        agent_workspace=tmp_path / "agent",
        timeout_multiplier=1,
        metadata={"execution": "docker"},
    )
    backend = get_backend(backend_name)
    backend.initialize_run(context)
    assert started[0]["bind_host"] == runtime.bind_host
    assert backend._config.mcp_public_url.startswith("http://host.docker.internal:")
    assert backend._config.mcp_admin_url.startswith("http://127.0.0.1:")
    assert backend._config.mcp_admin_token


def test_docker_service_registry_does_not_acquire_host_gateway_or_use_shared_services():
    from benchmark.backends.registry import get_backend

    for backend in ("openclaw", "qwenpaw", "openagent"):
        adapter = get_backend(backend, execution="docker")
        assert not adapter.uses_gateway_lock
        assert adapter.supports_parallel_runs
        assert type(adapter).__name__.startswith("Docker")


def test_qwenpaw_invalid_config_closes_initialized_docker_runtime(
    runtime_factory, monkeypatch, tmp_path
):
    from types import SimpleNamespace
    from benchmark.backends import docker_agents

    before = signal.getsignal(signal.SIGTERM)
    make, _ = runtime_factory
    runtime = make(backend="qwenpaw")
    monkeypatch.setattr(docker_agents, "initialize_runtime", lambda context: runtime)
    monkeypatch.setattr(docker_agents, "load_provider", lambda *args: {})
    monkeypatch.setenv("ACTBENCH_QWENPAW_TIMEOUT_SECONDS", "invalid")
    context = SimpleNamespace(model="check/model", metadata={})

    with pytest.raises(BackendInitializationError, match="must be numeric"):
        docker_agents.DockerQwenPawBackend().initialize_run(context)

    assert runtime._closed
    assert signal.getsignal(signal.SIGTERM) == before


@pytest.mark.parametrize("linked_directory", [False, True])
def test_openclaw_docker_transcripts_cannot_follow_links_to_host_files(tmp_path, linked_directory):
    from benchmark.backends.docker_agents import read_openclaw_transcripts

    home = tmp_path / "home"
    sessions = home / ".openclaw/agents/actbench/sessions"
    sessions.parent.mkdir(parents=True)
    private = tmp_path / "controller"
    private.mkdir()
    (private / "private.jsonl").write_text('{"content":"host-only sentinel"}\n')
    if linked_directory:
        sessions.symlink_to(private)
        expected = []
    else:
        sessions.mkdir()
        (sessions / "private.jsonl").symlink_to(private / "private.jsonl")
        (sessions / "normal.jsonl").write_text('{"content":"agent response"}\n')
        os.mkfifo(sessions / "fifo.jsonl")
        expected = [{"content": "agent response"}]

    assert read_openclaw_transcripts(home) == expected


@pytest.mark.parametrize("backend_name", ["qwenpaw", "openagent"])
def test_parallel_service_attempts_get_distinct_state_and_endpoints(
    runtime_factory, monkeypatch, tmp_path, backend_name
):
    from contextlib import contextmanager
    from types import SimpleNamespace
    from benchmark.backends import docker_agents
    from benchmark.backends.registry import get_backend

    make, _ = runtime_factory
    runtime = make(backend=backend_name)
    runtime.env_names = ("TEST_KEY",)
    runtime.target_env["TEST_KEY"] = "test-value"
    config_path = tmp_path / "provider.json"
    config_path.write_text(
        json.dumps({"base_url": "https://invalid.example/v1", "api_key_env": "TEST_KEY"})
    )
    monkeypatch.setenv("ACTBENCH_DOCKER_PROVIDER_CONFIG", str(config_path))
    monkeypatch.setattr(docker_agents, "initialize_runtime", lambda context: runtime)
    monkeypatch.setattr(
        docker_agents.DockerOpenAgentBackend, "_initialize_mcp_gateway", lambda *a: None
    )
    monkeypatch.setattr(docker_agents, "bootstrap_qwenpaw", lambda *a, **kw: None)
    monkeypatch.setattr(
        docker_agents, "bootstrap_openagent", lambda *a, **kw: "temporary-store-key"
    )
    states = []

    @contextmanager
    def service(argv, **kw):
        states.append((kw["home"], kw["workspace"]))
        record = {"cleanup": "pending"}
        kw["records"].append(record)
        try:
            yield "http://127.0.0.1/" + kw["home"].parent.name
        finally:
            record["cleanup"] = "removed"

    def execute(self, **kwargs):
        assert self._config.base_url.startswith("http://127.0.0.1/")
        return {"status": "success", "endpoint": self._config.base_url}

    monkeypatch.setattr(runtime, "service", service)
    delegate = (
        docker_agents.QwenPawBackend
        if backend_name == "qwenpaw"
        else docker_agents.OpenAgentBackend
    )
    monkeypatch.setattr(delegate, "execute_task", execute)
    adapter = get_backend(backend_name, execution="docker")
    context = BackendRunContext(
        backend=backend_name,
        model="check/model",
        run_id="run",
        run_root=tmp_path,
        skill_dir=tmp_path,
        agent_id="check",
        agent_workspace=tmp_path / "agent",
        timeout_multiplier=1,
        metadata={"execution": "docker"},
    )
    adapter.initialize_run(context)
    task = SimpleNamespace(task_id="T1", timeout_seconds=120)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda n: adapter.execute_task(
                    task=task, context=context, attempt_run_id=f"attempt-{n}"
                ),
                range(2),
            )
        )
    assert len({home for home, _ in states}) == 2
    assert len({workspace for _, workspace in states}) == 2
    assert all(r["status"] == "success" for r in results)
    assert all(
        r["backend_metadata"]["docker_executions"][0]["cleanup"] == "removed" for r in results
    )


def test_sigterm_cleans_owned_attempts_and_restores_handler(runtime_factory):
    make, calls = runtime_factory
    before = signal.getsignal(signal.SIGTERM)
    runtime = make()
    runtime._active.update({"owned-first", "owned-second"})
    with pytest.raises(SystemExit) as exit_info:
        runtime._on_signal(signal.SIGTERM, None)
    assert exit_info.value.code == 143
    assert {tuple(call) for call in calls if call[0] == "rm"} == {
        ("rm", "--force", "owned-first"),
        ("rm", "--force", "owned-second"),
    }
    assert signal.getsignal(signal.SIGTERM) == before
    assert not runtime._active


def test_provider_template_cannot_replace_mcp_or_permissions(
    runtime_factory, monkeypatch, tmp_path
):
    make, _ = runtime_factory
    runtime = make()
    backend = OpenCodeBackend()
    backend._docker = runtime
    provider = {"custom": {"options": {"apiKey": "{env:TARGET_API_KEY}"}}}
    path = tmp_path / "provider.json"
    path.write_text(json.dumps({"provider": provider, "mcp": {}, "permission": "deny"}))
    monkeypatch.setenv("ACTBENCH_OPENCODE_PROVIDER_CONFIG", str(path))
    context = BackendRunContext(
        backend="opencode",
        model="custom/model",
        run_id="r",
        run_root=tmp_path,
        skill_dir=ROOT,
        agent_id="a",
        agent_workspace=tmp_path / "agent",
        timeout_multiplier=1,
        metadata={"execution": "docker"},
    )
    payload = _opencode_config_payload(backend._load_config(context))
    assert payload["provider"] == provider
    assert payload["mcp"]["actbench"]["enabled"] is True
    assert payload["permission"]["external_directory"] == "deny"


def test_cleanup_attempts_all_owned_containers_after_one_failure(runtime_factory, monkeypatch):
    make, _ = runtime_factory
    runtime = make()
    names = {"owned-first", "owned-second", "owned-third"}
    runtime._active.update(names)
    attempted = []
    original = runtime._remove

    def remove(name):
        attempted.append(name)
        if len(attempted) == 1:
            raise RuntimeError("daemon unavailable")
        original(name)

    monkeypatch.setattr(runtime, "_remove", remove)
    with pytest.raises(RuntimeError, match="Docker cleanup failed"):
        runtime.close()
    assert set(attempted) == names
    assert len(runtime._active) == 1
    runtime.close()
    assert not runtime._active


def test_protected_mock_services_keep_audit_and_reset_under_host_control(tmp_path):
    from urllib import error, request
    import uuid
    from lib_api_services import start_api_services

    group = start_api_services(
        services=["taskboard"],
        run_id=uuid.uuid4().hex,
        attempt_id="docker-auth-test",
        workspace=tmp_path,
        protect_admin=True,
    )
    opener = request.build_opener(request.ProxyHandler({}))
    try:
        endpoint = group.endpoints["taskboard"]
        for key, data in (("audit", None), ("reset", b"{}")):
            with pytest.raises(error.HTTPError) as caught:
                opener.open(request.Request(endpoint[key], data=data), timeout=5)
            assert caught.value.code == 401
        assert group.admin_token not in (tmp_path / "api_endpoints.json").read_text()
        req = request.Request(
            endpoint["business"]["tasks"],
            data=b"{}",
            headers={"Content-Type": "application/json", "X-Health-Check": "1"},
        )
        with opener.open(req, timeout=5) as response:
            assert response.status == 200
        assert group.collect_audit()["taskboard"]["calls"]
        assert "error" not in group.reset_all()["taskboard"]
        assert not group.collect_audit()["taskboard"]["calls"]
    finally:
        group.stop()
