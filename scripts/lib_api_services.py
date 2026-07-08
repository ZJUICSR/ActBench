"""Per-attempt mock API service orchestration for ClawEval."""

from __future__ import annotations

import atexit
import json
import os
import shutil
import socket
import subprocess
import sys
import time
from datetime import timedelta
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal
from urllib import error, request

REPO_ROOT = Path(__file__).resolve().parents[1]
API_RUN_ROOT = Path("/tmp/claweval/api")
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from mock_services._base import (  # noqa: E402
    MOCK_ACTIVITY_TIME_FIELDS,
    collect_fixture_datetimes,
    parse_mock_datetime,
)

MAILBOX_MOCK_TIME_FIELDS = ("date",)


@dataclass(frozen=True)
class ApiServiceSpec:
    name: str
    server_path: Path
    fixture_env: str
    fixture_path: Path
    default_port: int
    health_path: str
    audit_path: str
    reset_path: str
    business_paths: tuple[str, ...]


def _service_spec(
    name: str,
    *,
    default_port: int,
    fixture_filename: str,
    business_paths: tuple[str, ...],
) -> ApiServiceSpec:
    root = REPO_ROOT / "mock_services" / name
    fixture_env = f"{name.upper()}_FIXTURES"
    return ApiServiceSpec(
        name=name,
        server_path=root / "server.py",
        fixture_env=fixture_env,
        fixture_path=REPO_ROOT / "mock_services" / "fixtures" / name / fixture_filename,
        default_port=default_port,
        health_path=f"/{name}/health",
        audit_path=f"/{name}/audit",
        reset_path=f"/{name}/reset",
        business_paths=business_paths,
    )


SERVICE_SPECS: dict[str, ApiServiceSpec] = {
    "mailbox": _service_spec(
        "mailbox",
        default_port=9100,
        fixture_filename="inbox.json",
        business_paths=(
            "/mailbox/messages",
            "/mailbox/messages/get",
            "/mailbox/messages/send",
            "/mailbox/drafts/save",
        ),
    ),
    "scheduling": _service_spec(
        "scheduling",
        default_port=9101,
        fixture_filename="events.json",
        business_paths=(
            "/scheduling/events",
            "/scheduling/events/get",
            "/scheduling/events/create",
            "/scheduling/users/events",
            "/scheduling/events/delete",
        ),
    ),
    "taskboard": _service_spec(
        "taskboard",
        default_port=9102,
        fixture_filename="tasks.json",
        business_paths=(
            "/taskboard/tasks",
            "/taskboard/tasks/get",
            "/taskboard/tasks/create",
            "/taskboard/tasks/update",
            "/taskboard/tasks/delete",
        ),
    ),
    "directory": _service_spec(
        "directory",
        default_port=9103,
        fixture_filename="entries.json",
        business_paths=(
            "/directory/search",
            "/directory/entries/get",
            "/directory/messages/send",
        ),
    ),
    "notebook": _service_spec(
        "notebook",
        default_port=9105,
        fixture_filename="notes.json",
        business_paths=(
            "/notebook/notes",
            "/notebook/notes/get",
            "/notebook/notes/share",
        ),
    ),
    "ticketing": _service_spec(
        "ticketing",
        default_port=9107,
        fixture_filename="tickets.json",
        business_paths=(
            "/ticketing/tickets",
            "/ticketing/tickets/get",
            "/ticketing/tickets/update",
            "/ticketing/tickets/close",
        ),
    ),
    "integrations": _service_spec(
        "integrations",
        default_port=9111,
        fixture_filename="integrations.json",
        business_paths=(
            "/integrations/items",
            "/integrations/items/get",
            "/integrations/items/update",
            "/integrations/notify",
        ),
    ),
    "automation": _service_spec(
        "automation",
        default_port=9112,
        fixture_filename="jobs.json",
        business_paths=(
            "/automation/jobs",
            "/automation/jobs/get",
            "/automation/jobs/create",
            "/automation/jobs/update",
            "/automation/jobs/delete",
            "/automation/jobs/history",
        ),
    ),
    "web_content": _service_spec(
        "web_content",
        default_port=9114,
        fixture_filename="content.json",
        business_paths=(
            "/web_content/search",
            "/web_content/fetch",
            "/web_content/notify",
        ),
    ),
    "knowledge_base": _service_spec(
        "knowledge_base",
        default_port=9115,
        fixture_filename="articles.json",
        business_paths=(
            "/knowledge_base/search",
            "/knowledge_base/articles/get",
            "/knowledge_base/articles/update",
        ),
    ),
    "customer_records": _service_spec(
        "customer_records",
        default_port=9116,
        fixture_filename="customers.json",
        business_paths=(
            "/customer_records/customers",
            "/customer_records/customers/get",
            "/customer_records/followups/create",
            "/customer_records/export",
        ),
    ),
    "ledger": _service_spec(
        "ledger",
        default_port=9117,
        fixture_filename="transactions.json",
        business_paths=(
            "/ledger/transactions",
            "/ledger/transactions/get",
            "/ledger/reports/submit",
            "/ledger/payments/create",
        ),
    ),
}


API_ACTION_READ = "read"
API_ACTION_WRITE = "write"
API_ACTION_UNKNOWN = "unknown"
ApiActionType = Literal["read", "write", "unknown"]


ENDPOINT_ACTION_TYPES: dict[str, ApiActionType] = {
    "/mailbox/messages": API_ACTION_READ,
    "/mailbox/messages/get": API_ACTION_READ,
    "/mailbox/messages/send": API_ACTION_WRITE,
    "/mailbox/drafts/save": API_ACTION_WRITE,
    "/scheduling/events": API_ACTION_READ,
    "/scheduling/events/get": API_ACTION_READ,
    "/scheduling/events/create": API_ACTION_WRITE,
    "/scheduling/users/events": API_ACTION_READ,
    "/scheduling/events/delete": API_ACTION_WRITE,
    "/taskboard/tasks": API_ACTION_READ,
    "/taskboard/tasks/get": API_ACTION_READ,
    "/taskboard/tasks/create": API_ACTION_WRITE,
    "/taskboard/tasks/update": API_ACTION_WRITE,
    "/taskboard/tasks/delete": API_ACTION_WRITE,
    "/directory/search": API_ACTION_READ,
    "/directory/entries/get": API_ACTION_READ,
    "/directory/messages/send": API_ACTION_WRITE,
    "/notebook/notes": API_ACTION_READ,
    "/notebook/notes/get": API_ACTION_READ,
    "/notebook/notes/share": API_ACTION_WRITE,
    "/ticketing/tickets": API_ACTION_READ,
    "/ticketing/tickets/get": API_ACTION_READ,
    "/ticketing/tickets/update": API_ACTION_WRITE,
    "/ticketing/tickets/close": API_ACTION_WRITE,
    "/integrations/items": API_ACTION_READ,
    "/integrations/items/get": API_ACTION_READ,
    "/integrations/items/update": API_ACTION_WRITE,
    "/integrations/notify": API_ACTION_WRITE,
    "/automation/jobs": API_ACTION_READ,
    "/automation/jobs/get": API_ACTION_READ,
    "/automation/jobs/create": API_ACTION_WRITE,
    "/automation/jobs/update": API_ACTION_WRITE,
    "/automation/jobs/delete": API_ACTION_WRITE,
    "/automation/jobs/history": API_ACTION_READ,
    "/web_content/search": API_ACTION_READ,
    "/web_content/fetch": API_ACTION_READ,
    "/web_content/notify": API_ACTION_WRITE,
    "/knowledge_base/search": API_ACTION_READ,
    "/knowledge_base/articles/get": API_ACTION_READ,
    "/knowledge_base/articles/update": API_ACTION_WRITE,
    "/customer_records/customers": API_ACTION_READ,
    "/customer_records/customers/get": API_ACTION_READ,
    "/customer_records/followups/create": API_ACTION_WRITE,
    "/customer_records/export": API_ACTION_READ,
    "/ledger/transactions": API_ACTION_READ,
    "/ledger/transactions/get": API_ACTION_READ,
    "/ledger/reports/submit": API_ACTION_WRITE,
    "/ledger/payments/create": API_ACTION_WRITE,
}


def endpoint_action_type(endpoint: str) -> ApiActionType:
    """Return whether a mock API business endpoint reads or mutates task state."""
    return ENDPOINT_ACTION_TYPES.get(str(endpoint).strip(), API_ACTION_UNKNOWN)


def service_endpoint_action_types(service: str) -> dict[str, ApiActionType]:
    """Return action classifications for a service's declared business endpoints."""
    spec = SERVICE_SPECS.get(str(service).strip())
    if not spec:
        return {}
    return {path: endpoint_action_type(path) for path in spec.business_paths}


_ACTIVE_GROUPS: list["ApiServiceGroup"] = []


def _cleanup_active_groups() -> None:
    for group in list(_ACTIVE_GROUPS):
        group.stop()


atexit.register(_cleanup_active_groups)


def get_declared_mock_services(config: dict[str, Any] | None) -> list[str]:
    if not config:
        return []
    raw_services = config.get("mock_services") or []
    if isinstance(raw_services, str):
        raw_services = [raw_services]
    if not isinstance(raw_services, list):
        raise ValueError("mock_services must be a list of service names")

    services: list[str] = []
    for raw_name in raw_services:
        name = str(raw_name).strip()
        if not name:
            continue
        if name not in SERVICE_SPECS:
            known = ", ".join(sorted(SERVICE_SPECS))
            raise ValueError(f"Unknown mock service '{name}'. Known services: {known}")
        if name not in services:
            services.append(name)
    return services


def get_fixture_overrides(config: dict[str, Any] | None) -> dict[str, Path]:
    if not config:
        return {}
    raw_overrides = config.get("mock_service_fixtures") or {}
    if not isinstance(raw_overrides, dict):
        raise ValueError("mock_service_fixtures must be a mapping of service name to path")

    overrides: dict[str, Path] = {}
    for raw_name, raw_path in raw_overrides.items():
        name = str(raw_name).strip()
        if name not in SERVICE_SPECS:
            known = ", ".join(sorted(SERVICE_SPECS))
            raise ValueError(f"Unknown fixture override service '{name}'. Known services: {known}")
        path = Path(str(raw_path))
        if not path.is_absolute():
            path = REPO_ROOT / path
        overrides[name] = path
    return overrides


def _safe_path_component(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in ("-", "_", ".") else "_" for ch in value)


def _allocate_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _business_key(service_name: str, path: str) -> str:
    prefix = f"/{service_name}/"
    if path.startswith(prefix):
        path = path[len(prefix) :]
    return path.strip("/").replace("/", "_")


def _http_json(url: str, *, method: str = "GET", timeout: float = 5.0) -> dict[str, Any]:
    data = b"{}" if method == "POST" else None
    headers = {"Content-Type": "application/json", "X-Health-Check": "1"}
    req = request.Request(url, data=data, headers=headers, method=method)
    with request.urlopen(req, timeout=timeout) as resp:
        payload = resp.read().decode("utf-8")
    parsed = json.loads(payload) if payload else {}
    return parsed if isinstance(parsed, dict) else {"data": parsed}


def _wait_for_health(base_url: str, health_path: str, timeout_seconds: float = 10.0) -> None:
    deadline = time.time() + timeout_seconds
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            _http_json(f"{base_url}{health_path}", timeout=1.0)
            return
        except (OSError, error.URLError, TimeoutError) as exc:
            last_error = exc
            time.sleep(0.2)
    raise RuntimeError(f"Service health check timed out for {base_url}{health_path}: {last_error}")


def _read_log_tail(path: Path, max_chars: int = 4000) -> str:
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8", errors="replace")
    return text[-max_chars:]


class ApiServiceGroup:
    def __init__(
        self,
        *,
        service_names: list[str],
        run_id: str,
        attempt_id: str,
        fixture_overrides: dict[str, Path] | None = None,
        workspace: Path | None = None,
    ) -> None:
        self.service_names = service_names
        self.run_id = run_id
        self.attempt_id = attempt_id
        self.fixture_overrides = fixture_overrides or {}
        self.workspace = workspace
        self.root = API_RUN_ROOT / _safe_path_component(run_id) / _safe_path_component(attempt_id)
        self.processes: dict[str, subprocess.Popen[str]] = {}
        self.endpoints: dict[str, dict[str, Any]] = {}
        self.prepared_fixtures: dict[str, Path] = {}
        self.mock_now: str | None = None

    def start(self) -> "ApiServiceGroup":
        if not self.service_names:
            return self

        self.root.mkdir(parents=True, exist_ok=True)
        try:
            for name in self.service_names:
                self.prepared_fixtures[name] = self._prepare_fixture(SERVICE_SPECS[name])
            self.mock_now = self._derive_group_mock_now()
            for name in self.service_names:
                self._start_one(name)
            if self.workspace:
                self.write_endpoints_file(self.workspace)
        except Exception:
            self.stop()
            raise

        _ACTIVE_GROUPS.append(self)
        return self

    def _start_one(self, name: str) -> None:
        spec = SERVICE_SPECS[name]
        fixture_path = self.prepared_fixtures[name]
        env = os.environ.copy()
        env["PORT"] = str(_allocate_port())
        env[spec.fixture_env] = str(fixture_path)
        if self.mock_now:
            env["CLAWEVAL_MOCK_NOW"] = self.mock_now
        env["PYTHONPATH"] = (
            str(REPO_ROOT)
            if not env.get("PYTHONPATH")
            else f"{REPO_ROOT}{os.pathsep}{env['PYTHONPATH']}"
        )

        port = int(env["PORT"])
        base_url = f"http://127.0.0.1:{port}"
        log_dir = self.root / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / f"{name}.log"
        with log_path.open("a", encoding="utf-8") as log_file:
            process = subprocess.Popen(
                [sys.executable, str(spec.server_path)],
                cwd=str(REPO_ROOT),
                env=env,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                text=True,
            )
        self.processes[name] = process
        try:
            _wait_for_health(base_url, spec.health_path)
        except Exception as exc:
            log_tail = _read_log_tail(log_path)
            detail = f"\nService log tail:\n{log_tail}" if log_tail else ""
            raise RuntimeError(f"Failed to start mock service '{name}': {exc}{detail}") from exc

        self.endpoints[name] = {
            "base_url": base_url,
            "health": f"{base_url}{spec.health_path}",
            "audit": f"{base_url}{spec.audit_path}",
            "reset": f"{base_url}{spec.reset_path}",
            "log": str(log_path),
            "business": {
                _business_key(name, path): f"{base_url}{path}" for path in spec.business_paths
            },
            "business_paths": [f"{base_url}{path}" for path in spec.business_paths],
        }

    def _derive_group_mock_now(self) -> str | None:
        explicit = parse_mock_datetime(os.environ.get("CLAWEVAL_MOCK_NOW"))
        if explicit is not None:
            return explicit.isoformat()

        mailbox_path = self.prepared_fixtures.get("mailbox")
        if mailbox_path is not None:
            try:
                mailbox_fixture = json.loads(mailbox_path.read_text(encoding="utf-8"))
                mailbox_dates = collect_fixture_datetimes(
                    mailbox_fixture, field_names=MAILBOX_MOCK_TIME_FIELDS
                )
            except Exception:  # noqa: BLE001 - fall back to all fixture times below
                mailbox_dates = []
            if mailbox_dates:
                return (max(mailbox_dates) + timedelta(seconds=1)).isoformat()

        all_dates = []
        for fixture_path in self.prepared_fixtures.values():
            try:
                fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001 - ignore unparsable fixtures for clock derivation
                continue
            all_dates.extend(collect_fixture_datetimes(fixture, field_names=MOCK_ACTIVITY_TIME_FIELDS))
        if all_dates:
            return (max(all_dates) + timedelta(seconds=1)).isoformat()
        return None

    def _prepare_fixture(self, spec: ApiServiceSpec) -> Path:
        source = self.fixture_overrides.get(spec.name, spec.fixture_path)
        if not source.exists():
            raise FileNotFoundError(f"Fixture not found for service '{spec.name}': {source}")
        dest_dir = self.root / "fixtures" / spec.name
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / spec.fixture_path.name
        shutil.copy2(source, dest)
        return dest

    def write_endpoints_file(self, workspace: Path) -> Path:
        workspace.mkdir(parents=True, exist_ok=True)
        path = workspace / "api_endpoints.json"
        path.write_text(json.dumps(self.endpoints, indent=2, ensure_ascii=False), encoding="utf-8")
        return path

    def collect_audit(self) -> dict[str, dict[str, Any]]:
        audit_data: dict[str, dict[str, Any]] = {}
        for name, endpoint in self.endpoints.items():
            audit_url = endpoint["audit"]
            try:
                audit_data[name] = _http_json(audit_url, timeout=5.0)
            except Exception as exc:  # noqa: BLE001 - audit collection is best-effort
                audit_data[name] = {"error": str(exc)}
        return audit_data

    def reset_all(self) -> dict[str, dict[str, Any]]:
        results: dict[str, dict[str, Any]] = {}
        for name, endpoint in self.endpoints.items():
            try:
                results[name] = _http_json(endpoint["reset"], method="POST", timeout=5.0)
            except Exception as exc:  # noqa: BLE001 - reset errors should be visible to caller
                results[name] = {"error": str(exc)}
        return results

    def stop(self) -> None:
        for process in self.processes.values():
            if process.poll() is not None:
                continue
            process.terminate()
        for process in self.processes.values():
            if process.poll() is not None:
                continue
            try:
                process.wait(timeout=3.0)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3.0)
        self.processes = {}
        if self in _ACTIVE_GROUPS:
            _ACTIVE_GROUPS.remove(self)


def start_api_services(
    *,
    services: list[str],
    run_id: str,
    attempt_id: str,
    fixture_overrides: dict[str, Path] | None = None,
    workspace: Path | None = None,
) -> ApiServiceGroup | None:
    if not services:
        return None
    return ApiServiceGroup(
        service_names=services,
        run_id=run_id,
        attempt_id=attempt_id,
        fixture_overrides=fixture_overrides,
        workspace=workspace,
    ).start()
