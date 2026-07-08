"""Mock Mailbox API service for ClawEval."""

from __future__ import annotations

import copy
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from mock_services._base import (
    AuditState,
    add_error_injection,
    mock_now,
    load_json_fixture,
    model_to_dict,
    utc_now,
)

app = FastAPI(title="ClawEval Mock Mailbox API")
add_error_injection(app)

FIXTURES_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "mailbox" / "inbox.json"

_emails: list[dict[str, Any]] = []
_clock_now = utc_now()
_audit = AuditState(["sent", "drafts"], now_fn=lambda: _clock_now)


def _now() -> datetime:
    return _clock_now


def _load_fixtures() -> None:
    global _emails, _clock_now
    _emails = load_json_fixture("MAILBOX_FIXTURES", FIXTURES_PATH)
    _clock_now = mock_now(service_name="mailbox", fixture=_emails, field_names=("date",))


_load_fixtures()


class ListMessagesRequest(BaseModel):
    days_back: int = 7
    max_results: int = 20


class GetMessageRequest(BaseModel):
    message_id: str


class SendMessageRequest(BaseModel):
    to: str
    subject: str
    body: str


class SaveDraftRequest(BaseModel):
    to: str
    subject: str
    body: str
    reply_to_message_id: str | None = None


@app.get("/mailbox/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/mailbox/messages")
def list_messages(req: ListMessagesRequest | None = None) -> dict[str, Any]:
    req = req or ListMessagesRequest()
    now = _now()
    cutoff = now - timedelta(days=req.days_back)
    results = []
    for email in _emails:
        email_date = datetime.fromisoformat(email["date"].replace("Z", "+00:00"))
        if email_date >= cutoff:
            results.append(
                {
                    "message_id": email["message_id"],
                    "from": email["from"],
                    "subject": email["subject"],
                    "date": email["date"],
                    "is_read": email.get("is_read", False),
                    "labels": email.get("labels", []),
                }
            )
    resp = {"messages": results[: req.max_results], "total": len(results)}
    _audit.log_call("/mailbox/messages", model_to_dict(req), resp)
    return resp


@app.post("/mailbox/messages/get")
def get_message(req: GetMessageRequest) -> dict[str, Any]:
    request_body = model_to_dict(req)
    for email in _emails:
        if email["message_id"] == req.message_id:
            resp = copy.deepcopy(email)
            _audit.log_call("/mailbox/messages/get", request_body, resp)
            return resp
    resp = {"error": f"Message {req.message_id} not found"}
    _audit.log_call("/mailbox/messages/get", request_body, resp)
    return resp


@app.post("/mailbox/messages/send")
def send_message(req: SendMessageRequest) -> dict[str, Any]:
    msg = {
        "to": req.to,
        "subject": req.subject,
        "body": req.body,
        "timestamp": _now().isoformat(),
    }
    _audit.add_action("sent", msg)
    resp = {"status": "sent", "message": msg}
    _audit.log_call("/mailbox/messages/send", model_to_dict(req), resp)
    return resp


@app.post("/mailbox/drafts/save")
def save_draft(req: SaveDraftRequest) -> dict[str, Any]:
    draft = {
        "to": req.to,
        "subject": req.subject,
        "body": req.body,
        "reply_to_message_id": req.reply_to_message_id,
        "timestamp": _now().isoformat(),
    }
    _audit.add_action("drafts", draft)
    resp = {"status": "draft_saved", "draft": draft}
    _audit.log_call("/mailbox/drafts/save", model_to_dict(req), resp)
    return resp


@app.get("/mailbox/audit")
def get_audit() -> dict[str, Any]:
    return _audit.snapshot()


@app.post("/mailbox/reset")
def reset_state() -> dict[str, str]:
    _audit.reset()
    _load_fixtures()
    return {"status": "reset"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "9100")))
