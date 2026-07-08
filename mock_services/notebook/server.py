"""Mock notebook API service for ClawEval."""

from __future__ import annotations

import copy
import os
import sys
from datetime import datetime
from pathlib import Path
from threading import RLock
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from mock_services._base import AuditState, add_error_injection, load_json_fixture, mock_now, model_to_dict, utc_now

app = FastAPI(title="ClawEval Mock Notebook API")
add_error_injection(app)

FIXTURES_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "notebook" / "notes.json"

_notes: list[dict[str, Any]] = []
_clock_now = utc_now()
_audit = AuditState(["shared"], now_fn=lambda: _clock_now)


def _now() -> datetime:
    return _clock_now
_state_lock = RLock()


def _load_fixtures() -> None:
    global _notes, _clock_now
    _notes = load_json_fixture("NOTEBOOK_FIXTURES", FIXTURES_PATH)
    _clock_now = mock_now(
        service_name="notebook",
        fixture=_notes,
        field_names=("created_at", "updated_at", "date", "timestamp"),
    )


_load_fixtures()


class ListRequest(BaseModel):
    max_results: int = 10


class GetRequest(BaseModel):
    note_id: str


class ShareRequest(BaseModel):
    note_id: str
    recipients: list[str]


@app.get("/notebook/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/notebook/notes")
def list_notes(req: ListRequest | None = None) -> dict[str, Any]:
    req = req or ListRequest()
    results = []
    for note in _notes[: req.max_results]:
        results.append(
            {
                "note_id": note["note_id"],
                "title": note["title"],
                "created_at": note["created_at"],
                "participants": note["participants"],
                "duration_minutes": note["duration_minutes"],
            }
        )
    resp = {"notes": results, "total": len(results)}
    _audit.log_call("/notebook/notes", model_to_dict(req), resp)
    return resp


@app.post("/notebook/notes/get")
def get_note(req: GetRequest) -> dict[str, Any]:
    request_body = model_to_dict(req)
    for note in _notes:
        if note["note_id"] == req.note_id:
            resp = copy.deepcopy(note)
            _audit.log_call("/notebook/notes/get", request_body, resp)
            return resp
    resp = {"error": f"Note {req.note_id} not found"}
    _audit.log_call("/notebook/notes/get", request_body, resp)
    return resp


@app.post("/notebook/notes/share")
def share_note(req: ShareRequest) -> dict[str, Any]:
    request_body = model_to_dict(req)
    with _state_lock:
        if not any(note["note_id"] == req.note_id for note in _notes):
            resp = {"error": f"Note {req.note_id} not found"}
            _audit.log_call("/notebook/notes/share", request_body, resp)
            return resp
        record = {
            "note_id": req.note_id,
            "recipients": list(req.recipients),
            "timestamp": _now().isoformat(),
        }
        _audit.add_action("shared", record)
        resp = {"status": "shared", "record": record}
        _audit.log_call("/notebook/notes/share", request_body, resp)
        return resp


@app.get("/notebook/audit")
def get_audit() -> dict[str, Any]:
    return _audit.snapshot()


@app.post("/notebook/reset")
def reset_state() -> dict[str, str]:
    with _state_lock:
        _audit.reset()
        _load_fixtures()
    return {"status": "reset"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "9105")))
