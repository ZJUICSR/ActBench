"""Mock enterprise directory API service for ClawEval."""

from __future__ import annotations

import copy
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from mock_services._base import AuditState, add_error_injection, load_json_fixture, mock_now, model_to_dict, utc_now

app = FastAPI(title="ClawEval Mock Directory API")
add_error_injection(app)

FIXTURES_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "directory" / "entries.json"

_entries: list[dict[str, Any]] = []
_clock_now = utc_now()
_audit = AuditState(["sent_messages"], now_fn=lambda: _clock_now)


def _now() -> datetime:
    return _clock_now


def _load_fixtures() -> None:
    global _entries, _clock_now
    _entries = load_json_fixture("DIRECTORY_FIXTURES", FIXTURES_PATH)
    _clock_now = mock_now(
        service_name="directory",
        fixture=_entries,
        field_names=("created_at", "updated_at", "timestamp", "date"),
    )


_load_fixtures()


class SearchDirectoryRequest(BaseModel):
    query: str | None = None
    department: str | None = None


class GetEntryRequest(BaseModel):
    entry_id: str


class SendMessageRequest(BaseModel):
    entry_id: str
    subject: str
    body: str


@app.get("/directory/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/directory/search")
def search_directory(req: SearchDirectoryRequest | None = None) -> dict[str, Any]:
    req = req or SearchDirectoryRequest()
    query = (req.query or "").lower()
    department = (req.department or "").lower()
    results = []
    for entry in _entries:
        if department and entry.get("department", "").lower() != department:
            continue
        haystack = " ".join(
            str(entry.get(key, "")) for key in ("name", "email", "department", "role", "aliases")
        ).lower()
        if query and query not in haystack:
            continue
        results.append(
            {
                "entry_id": entry["entry_id"],
                "name": entry["name"],
                "email": entry["email"],
                "department": entry.get("department"),
                "role": entry.get("role"),
            }
        )
    resp = {"entries": results, "total": len(results)}
    _audit.log_call("/directory/search", model_to_dict(req), resp)
    return resp


@app.post("/directory/entries/get")
def get_entry(req: GetEntryRequest) -> dict[str, Any]:
    request_body = model_to_dict(req)
    for entry in _entries:
        if entry["entry_id"] == req.entry_id:
            resp = copy.deepcopy(entry)
            _audit.log_call("/directory/entries/get", request_body, resp)
            return resp
    resp = {"error": f"Directory entry {req.entry_id} not found"}
    _audit.log_call("/directory/entries/get", request_body, resp)
    return resp


@app.post("/directory/messages/send")
def send_message(req: SendMessageRequest) -> dict[str, Any]:
    request_body = model_to_dict(req)
    entry = next((item for item in _entries if item["entry_id"] == req.entry_id), None)
    if entry is None:
        resp = {"error": f"Directory entry {req.entry_id} not found"}
        _audit.log_call("/directory/messages/send", request_body, resp)
        return resp
    record = {
        "entry_id": req.entry_id,
        "to": entry["email"],
        "subject": req.subject,
        "body": req.body,
        "timestamp": _now().isoformat(),
    }
    _audit.add_action("sent_messages", record)
    resp = {"status": "sent", "message": record}
    _audit.log_call("/directory/messages/send", request_body, resp)
    return resp


@app.get("/directory/audit")
def get_audit() -> dict[str, Any]:
    return _audit.snapshot()


@app.post("/directory/reset")
def reset_state() -> dict[str, str]:
    _audit.reset()
    _load_fixtures()
    return {"status": "reset"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "9103")))
