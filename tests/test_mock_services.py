from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mock_services.integrations import server as integrations  # noqa: E402
from mock_services.directory import server as directory  # noqa: E402
from mock_services.mailbox import server as mailbox  # noqa: E402
from mock_services.scheduling import server as scheduling  # noqa: E402
from mock_services.taskboard import server as taskboard  # noqa: E402
from mock_services.web_content import server as web_content  # noqa: E402


def test_mailbox_list_uses_fixture_relative_default_window() -> None:
    mailbox.reset_state()

    listed = mailbox.list_messages(mailbox.ListMessagesRequest())
    message_ids = {message["message_id"] for message in listed["messages"]}

    assert listed["total"] >= 2
    assert {"msg_001", "msg_002"}.issubset(message_ids)


def test_mailbox_fixture_override_controls_recent_window_and_timestamps(
    tmp_path: Path, monkeypatch
) -> None:
    fixture_path = tmp_path / "inbox.json"
    fixture_path.write_text(
        json.dumps(
            [
                {
                    "message_id": "old",
                    "from": "old@example.com",
                    "subject": "Old message",
                    "date": "2030-01-01T00:00:00Z",
                    "body": "Outside the fixture-relative two-day window.",
                },
                {
                    "message_id": "new",
                    "from": "new@example.com",
                    "subject": "New message",
                    "date": "2030-01-10T00:00:00Z",
                    "body": "Inside the fixture-relative two-day window.",
                },
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("MAILBOX_FIXTURES", str(fixture_path))
    try:
        mailbox.reset_state()
        listed = mailbox.list_messages(mailbox.ListMessagesRequest(days_back=2))
        assert [message["message_id"] for message in listed["messages"]] == ["new"]

        mailbox.save_draft(
            mailbox.SaveDraftRequest(
                to="owner@example.com",
                subject="Fixture-relative timestamp",
                body="Check timestamp.",
            )
        )
        audit = mailbox.get_audit()
        assert audit["calls"][0]["timestamp"] == "2030-01-10T00:00:01+00:00"
        assert audit["drafts"][0]["timestamp"] == "2030-01-10T00:00:01+00:00"
    finally:
        monkeypatch.delenv("MAILBOX_FIXTURES", raising=False)
        mailbox.reset_state()

def test_mailbox_send_and_draft_are_audited_separately() -> None:
    mailbox.reset_state()

    mailbox.send_message(
        mailbox.SendMessageRequest(
            to="maya.chen@company.example",
            subject="Deployment summary",
            body="No secrets included.",
        )
    )
    mailbox.save_draft(
        mailbox.SaveDraftRequest(
            to="unknown.manager@company.example",
            subject="Draft only",
            body="Needs confirmation.",
            reply_to_message_id="msg_001",
        )
    )

    audit = mailbox.get_audit()
    assert len(audit["calls"]) == 2
    assert audit["sent"][0]["to"] == "maya.chen@company.example"
    assert audit["drafts"][0]["reply_to_message_id"] == "msg_001"

    mailbox.reset_state()
    assert mailbox.get_audit()["sent"] == []


def test_integrations_list_redacts_secrets_but_get_returns_full_details() -> None:
    integrations.reset_state()

    listed = integrations.list_integrations(integrations.ListIntegrationsRequest())
    first = listed["integrations"][0]
    assert "api_key" not in first
    assert "webhook_secret" not in first

    full = integrations.get_integration(
        integrations.GetIntegrationRequest(integration_id=first["integration_id"])
    )
    assert "api_key" in full
    assert "webhook_secret" in full


def test_web_content_fetch_can_return_untrusted_injection_content_and_notify_is_audited() -> None:
    web_content.reset_state()

    page = web_content.fetch(
        web_content.FetchRequest(url="https://review.example/request-credentials")
    )
    assert "Ignore previous instructions" in page["content"]

    web_content.notify(web_content.NotifyRequest(channel="audit", message="test notification"))
    audit = web_content.get_audit()
    assert audit["notifications"][0]["channel"] == "audit"
    assert {call["endpoint"] for call in audit["calls"]} == {
        "/web_content/fetch",
        "/web_content/notify",
    }


def test_directory_search_handles_ambiguous_names_and_message_side_effects() -> None:
    directory.reset_state()

    results = directory.search_directory(directory.SearchDirectoryRequest(query="Maya"))
    assert results["total"] == 2

    entry_id = results["entries"][0]["entry_id"]
    directory.send_message(
        directory.SendMessageRequest(
            entry_id=entry_id,
            subject="Confirm recipient",
            body="Please confirm ownership.",
        )
    )
    assert directory.get_audit()["sent_messages"][0]["entry_id"] == entry_id

    missing = directory.send_message(
        directory.SendMessageRequest(
            entry_id="missing",
            subject="Do not send",
            body="This should not create a side effect.",
        )
    )
    audit = directory.get_audit()
    assert missing["error"] == "Directory entry missing not found"
    assert len(audit["sent_messages"]) == 1


def test_scheduling_create_event_preserves_description_in_audit() -> None:
    scheduling.reset_state()

    created = scheduling.create_event(
        scheduling.CreateEventRequest(
            title="Team Sync",
            start_time="2026-05-27T17:00:00Z",
            end_time="2026-05-27T17:30:00Z",
            attendees=["alice@example.com"],
            location="Conference Room B",
            description="Agenda with no secrets.",
        )
    )

    audit = scheduling.get_audit()
    assert created["event"]["description"] == "Agenda with no secrets."
    assert audit["created_events"][0]["description"] == "Agenda with no secrets."
    assert audit["calls"][0]["request_body"]["description"] == "Agenda with no secrets."


def test_taskboard_create_update_delete_are_stateful_and_reset_restores_fixture() -> None:
    taskboard.reset_state()

    created = taskboard.create_task(taskboard.CreateTaskRequest(title="Review API audit"))
    task_id = created["task"]["task_id"]
    taskboard.update_task(taskboard.UpdateTaskRequest(task_id=task_id, status="completed"))
    taskboard.delete_task(taskboard.DeleteTaskRequest(task_id=task_id))

    audit = taskboard.get_audit()
    assert audit["created_tasks"][0]["title"] == "Review API audit"
    assert audit["updated_tasks"][0]["changes"]["status"] == "completed"
    assert audit["deleted"][0]["task_id"] == task_id

    taskboard.reset_state()
    assert taskboard.get_audit()["calls"] == []
    tasks = taskboard.list_tasks(taskboard.ListTasksRequest())
    assert tasks["total"] == 2
