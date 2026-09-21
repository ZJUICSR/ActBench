"""Fresh Docker attempts for native OpenClaw and the two HTTP agent services.

The existing service adapters still own prompts, transcripts and audit collection.
Only their endpoint and attempt-owned state change; no shared service is reused.
"""

from __future__ import annotations

from dataclasses import replace
from http.cookiejar import CookieJar
import json
import secrets
import subprocess
import time
from urllib.request import HTTPCookieProcessor, ProxyHandler, Request, build_opener

from benchmark.backends.base import augment_execution_result
from benchmark.backends.common import (
    backend_attempt_home,
    backend_task_workspace,
    begin_task_artifacts,
    execution_error_result,
    finish_task_artifacts,
    materialize_task_workspace,
    session_prompts,
    start_declared_api_services,
)
from benchmark.backends.openclaw import OpenClawBackend
from benchmark.backends.openagent import OpenAgentBackend
from benchmark.backends.qwenpaw import QwenPawBackend
from benchmark.docker_support import configure_mcp, initialize_runtime, isolated_env, load_provider
from lib_agent import _extract_usage_from_transcript, _openclaw_agent_command, _read_transcript_file
from lib_mcp_gateway import stop_gateway_process


def _initialize(backend, context):
    backend._docker = initialize_runtime(context)
    try:
        backend._provider = load_provider(backend._docker, context.model)
        context.metadata["runtime_identity"] = backend._docker.identity(providers=backend._provider)
    except Exception:
        backend._docker.close()
        raise


def attempt_home(context, task, attempt_run_id, workspace):
    home = backend_attempt_home(
        home_root="",
        context=context,
        task=task,
        attempt_run_id=attempt_run_id,
        workspace=workspace,
        leaf_name=f"{context.backend}_home",
    )
    workspace.mkdir(parents=True, exist_ok=True)
    home.mkdir(parents=True, exist_ok=True, mode=0o700)
    return home


class JsonApi:
    def __init__(self, url, deadline=None):
        self.url = url
        self.deadline = deadline
        self.opener = build_opener(ProxyHandler({}), HTTPCookieProcessor(CookieJar()))

    def call(self, path, payload=None, method=None):
        req = Request(
            self.url + path,
            data=json.dumps(payload).encode() if payload is not None else None,
            headers={"Content-Type": "application/json"},
            method=method,
        )
        remaining = self.deadline - time.monotonic() if self.deadline is not None else 30
        if remaining <= 0:
            raise TimeoutError("Agent service initialization exceeded the task timeout")
        with self.opener.open(req, timeout=min(30, remaining)) as response:
            value = json.load(response)
        if isinstance(value, dict) and value.get("status") == "error":
            # Do not echo provider responses, which may contain credentials.
            raise RuntimeError(f"Agent service rejected initialization at {path.split('?')[0]}")
        return value


def bootstrap_qwenpaw(url, provider, runtime, *, deadline=None):
    api = JsonApi(url, deadline)
    provider_id = provider["provider"]
    # A dedicated custom provider avoids built-in provider name/model assumptions.
    providers = api.call("/api/models")
    if not any(p.get("id") == provider_id for p in providers):
        api.call(
            "/api/models/custom-providers",
            {
                "id": provider_id,
                "name": "ActBench",
                "default_base_url": provider["base_url"],
                "chat_model": "OpenAIChatModel",
                "models": [{"id": provider["model"], "name": provider["model"]}],
            },
        )
    api.call(
        f"/api/models/{provider_id}/config",
        {
            "api_key": runtime.target_env[provider["api_key_env"]],
            "base_url": provider["base_url"],
            "chat_model": "OpenAIChatModel",
        },
        method="PUT",
    )


def prepare_openagent_home(home):
    conf = home / "conf"
    conf.mkdir(exist_ok=True)
    (conf / "app.conf").write_text(
        "appname = openagent\nhttpport = 14000\nrunmode = prod\ndriverName = sqlite3\n"
        f"dataSourceName = {home / 'openagent.db'}\ndbName = openagent\n"
        'isDemoMode = false\nlogConfig = {"adapter":"console"}\n'
    )


def bootstrap_openagent(url, provider, runtime, mcp_url, *, deadline=None):
    api = JsonApi(url, deadline)
    api.call("/api/signin", {"username": "admin", "password": "123"})
    api.call(
        "/api/update-account", {"currentPassword": "123", "newPassword": secrets.token_urlsafe(32)}
    )
    api.call(
        "/api/add-provider",
        {
            "owner": "admin",
            "name": "actbench-model",
            "category": "Model",
            "type": "OpenAI Compatible",
            "subType": provider["model"],
            "providerUrl": provider["base_url"],
            "clientSecret": runtime.target_env[provider["api_key_env"]],
            "temperature": 0.2,
            "topP": 1,
            "state": "Active",
        },
    )
    server = {"owner": "admin", "name": "actbench-mcp", "url": mcp_url, "tools": []}
    api.call("/api/add-server", server)
    api.call("/api/sync-mcp-tool?id=admin/actbench-mcp", server)
    key = secrets.token_urlsafe(32)
    runtime.register_secret(key)
    api.call(
        "/api/add-store",
        {
            "owner": "admin",
            "name": "actbench",
            "displayName": "ActBench",
            "modelProvider": "actbench-model",
            "mcpServer": "actbench-mcp",
            "externalApiKey": key,
            "state": "Active",
            "tools": [],
            "skills": [],
            "prompt": "Follow the user task using ActBench tools.",
        },
    )
    return key


class DockerQwenPawBackend(QwenPawBackend):
    def initialize_run(self, context):
        _initialize(self, context)
        try:
            self._config = self._load_config()
        except Exception:
            self.finalize_run(context)
            raise

    def finalize_run(self, context):
        self._docker.close()

    def execute_task(self, *, task, context, attempt_run_id):
        workspace = backend_task_workspace(
            context=context, attempt_run_id=attempt_run_id, task=task
        )
        home = attempt_home(context, task, attempt_run_id, workspace)
        env = isolated_env(home, self._docker)
        env.update(
            QWENPAW_WORKING_DIR=str(home / "qwenpaw"),
            QWENPAW_SECRET_DIR=str(home / "secrets"),
            QWENPAW_BACKUP_DIR=str(home / "backups"),
        )
        records = []
        started = time.time()
        deadline = time.monotonic() + task.timeout_seconds * context.timeout_multiplier
        try:
            with self._docker.service(
                ["qwenpaw", "app", "--host", "0.0.0.0", "--port", "8088"],
                workspace=workspace,
                home=home,
                env=env,
                port=8088,
                health_path="/api/version",
                records=records,
                timeout_seconds=min(120, task.timeout_seconds * context.timeout_multiplier),
            ) as url:
                bootstrap_qwenpaw(url, self._provider, self._docker, deadline=deadline)
                delegate = QwenPawBackend()
                delegate._config = replace(
                    self._config, base_url=url, api_key=None, docker_runtime=self._docker
                )
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("Agent service initialization exceeded the task timeout")
                result = delegate.execute_task(
                    task=task,
                    context=replace(context, timeout_multiplier=remaining / task.timeout_seconds),
                    attempt_run_id=attempt_run_id,
                )
        except Exception as exc:
            result = execution_error_result(
                context=context,
                task=task,
                workspace=workspace,
                stderr=self._docker.redact(str(exc)),
                execution_time=time.time() - started,
            )
            if isinstance(exc, TimeoutError):
                result.update(status="timeout", timed_out=True)
        result["execution_time"] = time.time() - started
        return augment_execution_result(
            self._docker.redact_value(result),
            context=context,
            docker_executions=records,
            docker_home=str(home),
        )


class DockerOpenAgentBackend(OpenAgentBackend):
    supports_parallel_runs = True

    def initialize_run(self, context):
        _initialize(self, context)
        try:
            config = replace(
                self._load_config(api_key_override="pending"),
                base_url="http://127.0.0.1",
                endpoint="/api/v1/chat/completions",
            )
            self._config = configure_mcp(config, self._docker)
            self._initialize_mcp_gateway(self._config)
        except Exception:
            self.finalize_run(context)
            raise

    def finalize_run(self, context):
        try:
            self._docker.close()
        finally:
            stop_gateway_process(self._mcp_gateway)
            self._mcp_gateway = None

    def execute_task(self, *, task, context, attempt_run_id):
        workspace = backend_task_workspace(
            context=context, attempt_run_id=attempt_run_id, task=task
        )
        home = attempt_home(context, task, attempt_run_id, workspace)
        prepare_openagent_home(home)
        records = []
        started = time.time()
        deadline = time.monotonic() + task.timeout_seconds * context.timeout_multiplier
        try:
            with self._docker.service(
                ["sh", "-c", 'cd "$HOME" && exec openagent serve'],
                workspace=workspace,
                home=home,
                env=isolated_env(home, self._docker),
                port=14000,
                health_path="/api/health",
                records=records,
                timeout_seconds=min(120, task.timeout_seconds * context.timeout_multiplier),
            ) as url:
                key = bootstrap_openagent(
                    url,
                    self._provider,
                    self._docker,
                    self._config.mcp_public_url,
                    deadline=deadline,
                )
                delegate = OpenAgentBackend()
                delegate._config = replace(self._config, base_url=url, api_key=key)
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("Agent service initialization exceeded the task timeout")
                result = delegate.execute_task(
                    task=task,
                    context=replace(context, timeout_multiplier=remaining / task.timeout_seconds),
                    attempt_run_id=attempt_run_id,
                )
        except Exception as exc:
            result = execution_error_result(
                context=context,
                task=task,
                workspace=workspace,
                stderr=self._docker.redact(str(exc)),
                execution_time=time.time() - started,
            )
            if isinstance(exc, TimeoutError):
                result.update(status="timeout", timed_out=True)
        result["execution_time"] = time.time() - started
        return augment_execution_result(
            self._docker.redact_value(result),
            context=context,
            docker_executions=records,
            docker_home=str(home),
        )


class DockerOpenClawBackend(OpenClawBackend):
    uses_gateway_lock = False

    def initialize_run(self, context):
        _initialize(self, context)

    def finalize_run(self, context):
        self._docker.close()

    def execute_task(self, *, task, context, attempt_run_id):
        started = time.time()
        workspace = backend_task_workspace(
            context=context, attempt_run_id=attempt_run_id, task=task
        )
        home = attempt_home(context, task, attempt_run_id, workspace)
        records, transcript = [], []
        api_group, endpoints, audit = None, {}, {}
        recorder, artifact_key = None, None
        stdout, stderr, status, exit_code, timed_out = "", "", "success", 0, False
        session_id = secrets.token_hex(16)
        try:
            materialize_task_workspace(workspace=workspace, skill_dir=context.skill_dir, task=task)
            config_path = prepare_openclaw_home(home, workspace, context, self._provider)
            env = isolated_env(home, self._docker)
            env.update(
                OPENCLAW_STATE_DIR=str(home / ".openclaw"), OPENCLAW_CONFIG_PATH=str(config_path)
            )
            artifact_key, recorder = begin_task_artifacts(
                context=context,
                task=task,
                attempt_run_id=attempt_run_id,
                session_id=session_id,
                workspace=workspace,
            )
            api_group, endpoints = start_declared_api_services(
                task=task,
                attempt_run_id=attempt_run_id,
                workspace=workspace,
                docker_runtime=self._docker,
            )
            for prompt in session_prompts(task):
                remaining = task.timeout_seconds * context.timeout_multiplier - (
                    time.time() - started
                )
                if remaining <= 0:
                    raise subprocess.TimeoutExpired(["openclaw"], 0)
                completed = self._docker.run(
                    _openclaw_agent_command(
                        agent_id="actbench", session_id=session_id, message=prompt
                    ),
                    workspace=workspace,
                    home=home,
                    env=env,
                    timeout_seconds=remaining,
                    records=records,
                )
                stdout += completed.stdout
                stderr += completed.stderr
                exit_code = completed.returncode
                if exit_code:
                    status = "error"
                    break
        except subprocess.TimeoutExpired as exc:
            status, exit_code, timed_out = "timeout", -1, True
            stdout += str(exc.output or "")
            stderr += str(exc.stderr or "")
        except Exception as exc:
            status, exit_code = "error", -1
            stderr += self._docker.redact(str(exc))
        finally:
            if api_group:
                try:
                    audit = api_group.collect_audit()
                finally:
                    api_group.stop()
            finish_task_artifacts(
                recorder=recorder,
                artifact_key=artifact_key,
                task=task,
                workspace=workspace,
                api_endpoints=endpoints,
                api_audit=audit,
            )
        if all(record.get("cleanup") == "removed" for record in records):
            transcript = read_openclaw_transcripts(home)
        if not transcript and status == "success":
            status, exit_code = "error", -1
            stderr += "OpenClaw produced no session transcript"
        return augment_execution_result(
            self._docker.redact_value(
                {
                    "agent_id": context.agent_id,
                    "task_id": task.task_id,
                    "status": status,
                    "transcript": transcript,
                    "transcript_source": {"kind": "openclaw_session_jsonl", "fallback_used": False},
                    "usage": _extract_usage_from_transcript(transcript),
                    "workspace": str(workspace),
                    "exit_code": exit_code,
                    "timed_out": timed_out,
                    "execution_time": time.time() - started,
                    "stdout": stdout,
                    "stderr": stderr,
                    "api_audit": audit,
                    "api_endpoints": endpoints,
                    "training_artifact_key": artifact_key,
                }
            ),
            context=context,
            docker_executions=records,
            docker_home=str(home),
        )


def read_openclaw_transcripts(home):
    """Read native sessions only from this attempt's mounted HOME."""
    root = home.resolve()
    sessions = home / ".openclaw" / "agents" / "actbench" / "sessions"
    if not sessions.resolve().is_relative_to(root):
        return []
    transcript = []
    for path in sorted(sessions.glob("*.jsonl")):
        if path.is_symlink() or not path.resolve().is_relative_to(root) or not path.is_file():
            continue
        transcript.extend(_read_transcript_file(path))
    return transcript


def prepare_openclaw_home(home, workspace, context, provider):
    state = home / ".openclaw"
    state.mkdir(exist_ok=True)
    config = {
        "agents": {
            "defaults": {
                "workspace": str(workspace),
                "skipBootstrap": True,
                "model": {"primary": context.model},
            },
            "list": [{"id": "actbench", "workspace": str(workspace)}],
        },
        "models": {
            "mode": "merge",
            "providers": {
                provider["provider"]: {
                    "baseUrl": provider["base_url"],
                    "apiKey": "${" + provider["api_key_env"] + "}",
                    "api": "openai-completions",
                    "models": [
                        {
                            "id": provider["model"],
                            "name": provider["model"],
                            "reasoning": False,
                            "input": ["text"],
                            "contextWindow": 128000,
                            "maxTokens": 8192,
                        }
                    ],
                }
            },
        },
        "tools": {"profile": "full", "exec": {"host": "gateway", "security": "full", "ask": "off"}},
    }
    path = state / "openclaw.json"
    path.write_text(json.dumps(config, indent=2) + "\n")
    return path
