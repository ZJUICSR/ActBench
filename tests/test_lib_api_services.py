from __future__ import annotations

import json
import sys
from pathlib import Path
from urllib import error, request

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
for path in (ROOT, SCRIPTS_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from lib_api_services import (  # noqa: E402
    get_declared_mock_services,
    get_fixture_overrides,
    start_api_services,
)


def _post_json(url: str, payload: dict) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with request.urlopen(req, timeout=5.0) as resp:
        return json.loads(resp.read().decode("utf-8"))


def test_declared_services_and_fixture_overrides_parse_repo_relative_paths() -> None:
    config = {
        "mock_services": ["mailbox", "knowledge_base", "ledger", "mailbox"],
        "mock_service_fixtures": {
            "mailbox": "mock_services/fixtures/mailbox/inbox.json",
            "knowledge_base": "mock_services/fixtures/knowledge_base/articles.json",
        },
    }

    assert get_declared_mock_services(config) == ["mailbox", "knowledge_base", "ledger"]
    overrides = get_fixture_overrides(config)
    assert overrides["mailbox"] == ROOT / "mock_services" / "fixtures" / "mailbox" / "inbox.json"
    assert (
        overrides["knowledge_base"]
        == ROOT / "mock_services" / "fixtures" / "knowledge_base" / "articles.json"
    )


def test_service_group_writes_endpoints_and_collects_audit(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    group = start_api_services(
        services=["mailbox", "integrations"],
        run_id="test_run",
        attempt_id="attempt_one",
        workspace=workspace,
    )
    assert group is not None
    try:
        endpoint_file = workspace / "api_endpoints.json"
        assert endpoint_file.exists()
        endpoints = json.loads(endpoint_file.read_text(encoding="utf-8"))
        assert set(endpoints) == {"mailbox", "integrations"}
        assert Path(endpoints["mailbox"]["log"]).exists()

        _post_json(
            endpoints["mailbox"]["business"]["messages_send"],
            {
                "to": "maya.chen@company.example",
                "subject": "API isolation",
                "body": "hello",
            },
        )
        audit = group.collect_audit()
        assert audit["mailbox"]["sent"][0]["subject"] == "API isolation"
        assert audit["integrations"]["calls"] == []
    finally:
        group.stop()


def test_two_service_groups_are_isolated_and_reset_does_not_cross_contaminate(
    tmp_path: Path,
) -> None:
    group_a = start_api_services(
        services=["mailbox"],
        run_id="test_run",
        attempt_id="attempt_a",
        workspace=tmp_path / "workspace_a",
    )
    group_b = start_api_services(
        services=["mailbox"],
        run_id="test_run",
        attempt_id="attempt_b",
        workspace=tmp_path / "workspace_b",
    )
    assert group_a is not None
    assert group_b is not None

    try:
        mailbox_a = group_a.endpoints["mailbox"]
        mailbox_b = group_b.endpoints["mailbox"]
        assert mailbox_a["base_url"] != mailbox_b["base_url"]

        _post_json(
            mailbox_a["business"]["messages_send"],
            {"to": "a@example.com", "subject": "group a", "body": "only a"},
        )
        _post_json(
            mailbox_b["business"]["messages_send"],
            {"to": "b@example.com", "subject": "group b", "body": "only b"},
        )
        group_a.reset_all()

        audit_a = group_a.collect_audit()
        audit_b = group_b.collect_audit()
        assert audit_a["mailbox"]["sent"] == []
        assert audit_b["mailbox"]["sent"][0]["subject"] == "group b"
    finally:
        group_a.stop()
        group_b.stop()


def test_mailbox_fixture_override_uses_fixture_relative_clock(tmp_path: Path) -> None:
    fixture_path = tmp_path / "inbox.json"
    fixture_path.write_text(
        json.dumps(
            [
                {
                    "message_id": "old",
                    "from": "old@example.com",
                    "subject": "Old message",
                    "date": "2030-01-01T00:00:00Z",
                    "body": "Outside the recent window.",
                },
                {
                    "message_id": "new",
                    "from": "new@example.com",
                    "subject": "New message",
                    "date": "2030-01-10T00:00:00Z",
                    "body": "Inside the recent window.",
                },
            ]
        ),
        encoding="utf-8",
    )
    group = start_api_services(
        services=["mailbox"],
        run_id="test_run",
        attempt_id="attempt_clock",
        workspace=tmp_path / "workspace_clock",
        fixture_overrides={"mailbox": fixture_path},
    )
    assert group is not None
    try:
        mailbox_endpoints = group.endpoints["mailbox"]["business"]
        listed = _post_json(mailbox_endpoints["messages"], {"days_back": 2})
        assert [message["message_id"] for message in listed["messages"]] == ["new"]

        _post_json(
            mailbox_endpoints["messages_send"],
            {"to": "owner@example.com", "subject": "Clock", "body": "Check timestamp"},
        )
        audit = group.collect_audit()["mailbox"]
        assert audit["calls"][0]["timestamp"] == "2030-01-10T00:00:01+00:00"
        assert audit["sent"][0]["timestamp"] == "2030-01-10T00:00:01+00:00"
    finally:
        group.stop()

def test_stop_makes_service_unreachable(tmp_path: Path) -> None:
    group = start_api_services(
        services=["mailbox"],
        run_id="test_run",
        attempt_id="attempt_stop",
        workspace=tmp_path / "workspace",
    )
    assert group is not None
    health_url = group.endpoints["mailbox"]["health"]
    group.stop()

    req = request.Request(health_url, method="GET")
    try:
        request.urlopen(req, timeout=1.0)
    except (OSError, error.URLError, TimeoutError):
        return
    raise AssertionError("service was still reachable after stop()")


def test_service_group_uses_single_mailbox_anchored_mock_now(tmp_path: Path) -> None:
    mailbox_fixture = tmp_path / "mailbox.json"
    mailbox_fixture.write_text(
        json.dumps(
            [
                {
                    "message_id": "msg_recent",
                    "from": "customer@example.com",
                    "subject": "Recent urgent message",
                    "date": "2025-06-15T09:00:00Z",
                    "body": "Recent mailbox world message.",
                }
            ]
        ),
        encoding="utf-8",
    )
    taskboard_fixture = tmp_path / "tasks.json"
    taskboard_fixture.write_text(
        json.dumps(
            [
                {
                    "task_id": "task_001",
                    "title": "Future due task",
                    "description": "Due date must not anchor group clock.",
                    "priority": "medium",
                    "status": "pending",
                    "due_date": "2030-01-01",
                    "tags": [],
                }
            ]
        ),
        encoding="utf-8",
    )
    group = start_api_services(
        services=["mailbox", "taskboard"],
        run_id="test_run",
        attempt_id="attempt_group_clock",
        workspace=tmp_path / "workspace_group_clock",
        fixture_overrides={"mailbox": mailbox_fixture, "taskboard": taskboard_fixture},
    )
    assert group is not None
    try:
        mailbox_endpoints = group.endpoints["mailbox"]["business"]
        listed = _post_json(mailbox_endpoints["messages"], {})
        assert [message["message_id"] for message in listed["messages"]] == ["msg_recent"]

        taskboard_endpoints = group.endpoints["taskboard"]["business"]
        created = _post_json(taskboard_endpoints["tasks_create"], {"title": "Created under group clock"})
        assert created["task"]["created_at"] == "2025-06-15T09:00:01+00:00"
    finally:
        group.stop()


def test_service_group_respects_explicit_global_mock_now(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("CLAWEVAL_MOCK_NOW", "2040-01-01T00:00:00Z")
    group = start_api_services(
        services=["mailbox", "taskboard"],
        run_id="test_run",
        attempt_id="attempt_explicit_clock",
        workspace=tmp_path / "workspace_explicit_clock",
    )
    assert group is not None
    try:
        mailbox_endpoints = group.endpoints["mailbox"]["business"]
        _post_json(
            mailbox_endpoints["messages_send"],
            {"to": "owner@example.com", "subject": "Clock", "body": "Explicit clock"},
        )
        taskboard_endpoints = group.endpoints["taskboard"]["business"]
        created = _post_json(taskboard_endpoints["tasks_create"], {"title": "Explicit clock task"})
        audit = group.collect_audit()
        assert audit["mailbox"]["sent"][0]["timestamp"] == "2040-01-01T00:00:00+00:00"
        assert created["task"]["created_at"] == "2040-01-01T00:00:00+00:00"
    finally:
        group.stop()


def test_automation_fixture_fields_anchor_group_clock_and_reset(tmp_path: Path) -> None:
    automation_fixture = tmp_path / "jobs.json"
    automation_fixture.write_text(
        json.dumps(
            [
                {
                    "job_id": "JOB-001",
                    "name": "Nightly sync",
                    "cron_expression": "0 2 * * *",
                    "action": "sync_records",
                    "enabled": True,
                    "last_status": "success",
                    "last_run": "2030-01-10T02:00:00Z",
                    "next_run": "2030-01-11T02:00:00Z",
                    "tags": ["sync"],
                    "execution_history": [],
                }
            ]
        ),
        encoding="utf-8",
    )
    group = start_api_services(
        services=["automation"],
        run_id="test_run",
        attempt_id="attempt_automation_clock",
        workspace=tmp_path / "workspace_automation_clock",
        fixture_overrides={"automation": automation_fixture},
    )
    assert group is not None
    try:
        endpoints = group.endpoints["automation"]["business"]
        created = _post_json(
            endpoints["jobs_create"],
            {"name": "Created", "cron_expression": "0 3 * * *", "action": "notify"},
        )
        assert created["job"]["created_at"] == "2030-01-11T02:00:01+00:00"

        group.reset_all()
        created_after_reset = _post_json(
            endpoints["jobs_create"],
            {"name": "Created again", "cron_expression": "0 4 * * *", "action": "notify"},
        )
        assert created_after_reset["job"]["created_at"] == "2030-01-11T02:00:01+00:00"
    finally:
        group.stop()


def test_integrations_fixture_fields_anchor_group_clock_and_reset(tmp_path: Path) -> None:
    integrations_fixture = tmp_path / "integrations.json"
    integrations_fixture.write_text(
        json.dumps(
            [
                {
                    "integration_id": "int_001",
                    "name": "CRM Sync",
                    "status": "healthy",
                    "last_verified": "2030-02-01T12:00:00Z",
                    "owner": "ops@example.com",
                    "api_key": "placeholder",
                    "webhook_secret": "placeholder",
                    "error_rate": 0.0,
                    "notes": "Fixture clock anchor.",
                }
            ]
        ),
        encoding="utf-8",
    )
    group = start_api_services(
        services=["integrations"],
        run_id="test_run",
        attempt_id="attempt_integrations_clock",
        workspace=tmp_path / "workspace_integrations_clock",
        fixture_overrides={"integrations": integrations_fixture},
    )
    assert group is not None
    try:
        endpoints = group.endpoints["integrations"]["business"]
        _post_json(
            endpoints["items_update"],
            {"integration_id": "int_001", "status": "degraded"},
        )
        audit = group.collect_audit()["integrations"]
        assert audit["updates"][0]["timestamp"] == "2030-02-01T12:00:01+00:00"

        group.reset_all()
        _post_json(
            endpoints["notify"],
            {"to": "ops@example.com", "subject": "Clock", "body": "Check reset."},
        )
        audit_after_reset = group.collect_audit()["integrations"]
        assert audit_after_reset["notifications"][0]["timestamp"] == "2030-02-01T12:00:01+00:00"
    finally:
        group.stop()


def test_non_mailbox_group_clock_ignores_business_due_dates(tmp_path: Path) -> None:
    taskboard_fixture = tmp_path / "tasks.json"
    taskboard_fixture.write_text(
        json.dumps(
            [
                {
                    "task_id": "task_001",
                    "title": "Future deadline",
                    "description": "Due date should not anchor mock now.",
                    "priority": "medium",
                    "status": "pending",
                    "updated_at": "2026-06-01T10:00:00Z",
                    "due_date": "2030-01-01",
                    "tags": [],
                }
            ]
        ),
        encoding="utf-8",
    )
    group = start_api_services(
        services=["taskboard"],
        run_id="test_run",
        attempt_id="attempt_taskboard_due_date",
        workspace=tmp_path / "workspace_taskboard_due_date",
        fixture_overrides={"taskboard": taskboard_fixture},
    )
    assert group is not None
    try:
        created = _post_json(
            group.endpoints["taskboard"]["business"]["tasks_create"],
            {"title": "Created under activity clock"},
        )
        assert created["task"]["created_at"] == "2026-06-01T10:00:01+00:00"
    finally:
        group.stop()


def test_non_mailbox_group_clock_ignores_customer_renewal_dates(tmp_path: Path) -> None:
    customer_fixture = tmp_path / "customers.json"
    customer_fixture.write_text(
        json.dumps(
            [
                {
                    "customer_id": "cust_001",
                    "name": "Acme Corp",
                    "tier": "enterprise",
                    "status": "active",
                    "owner": "owner@example.com",
                    "updated_at": "2026-05-01T00:00:00Z",
                    "renewal_date": "2030-01-01",
                    "contacts": [],
                    "notes": "Renewal date should not anchor now.",
                }
            ]
        ),
        encoding="utf-8",
    )
    group = start_api_services(
        services=["customer_records"],
        run_id="test_run",
        attempt_id="attempt_customer_renewal_date",
        workspace=tmp_path / "workspace_customer_renewal_date",
        fixture_overrides={"customer_records": customer_fixture},
    )
    assert group is not None
    try:
        created = _post_json(
            group.endpoints["customer_records"]["business"]["followups_create"],
            {"customer_id": "cust_001", "owner": "owner@example.com", "note": "Follow up."},
        )
        assert created["followup"]["created_at"] == "2026-05-01T00:00:01+00:00"
    finally:
        group.stop()
    workspace = tmp_path / "workspace"
    group = start_api_services(
        services=["knowledge_base", "customer_records", "ledger"],
        run_id="test_run",
        attempt_id="attempt_more_services",
        workspace=workspace,
    )
    assert group is not None
    try:
        endpoints = json.loads((workspace / "api_endpoints.json").read_text(encoding="utf-8"))
        assert set(endpoints) == {"knowledge_base", "customer_records", "ledger"}

        _post_json(
            endpoints["knowledge_base"]["business"]["search"],
            {"query": "deployment"},
        )
        _post_json(
            endpoints["customer_records"]["business"]["followups_create"],
            {
                "customer_id": "CUST-001",
                "owner": "agent@example.com",
                "note": "Schedule renewal review.",
            },
        )
        _post_json(
            endpoints["ledger"]["business"]["reports_submit"],
            {
                "title": "Pending review summary",
                "summary": "Reviewed suspicious transactions.",
                "transaction_ids": ["TXN-001"],
                "submitted_by": "agent@example.com",
            },
        )

        audit = group.collect_audit()
        assert audit["knowledge_base"]["calls"][0]["endpoint"] == "/knowledge_base/search"
        assert audit["customer_records"]["created_followups"][0]["customer_id"] == "CUST-001"
        assert audit["ledger"]["submitted_reports"][0]["title"] == "Pending review summary"
    finally:
        group.stop()
