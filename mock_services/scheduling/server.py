"""Mock scheduling API service for ClawEval."""

from __future__ import annotations

import copy
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import RLock
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel, Field

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from mock_services._base import AuditState, add_error_injection, load_json_fixture, mock_now, model_to_dict, utc_now

app = FastAPI(title="ClawEval Mock Scheduling API")
add_error_injection(app)

FIXTURES_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "scheduling" / "events.json"

_events: list[dict[str, Any]] = []
_clock_now = utc_now()
_audit = AuditState(["deleted", "created_events"], now_fn=lambda: _clock_now)


def _now() -> datetime:
    return _clock_now
_state_lock = RLock()


def _load_fixtures() -> None:
    global _events, _clock_now
    _events = load_json_fixture("SCHEDULING_FIXTURES", FIXTURES_PATH)
    _clock_now = mock_now(
        service_name="scheduling",
        fixture=_events,
        field_names=("start_time", "end_time", "created_at", "updated_at", "timestamp"),
    )


_load_fixtures()


class ListEventsRequest(BaseModel):
    date: str
    days: int = 1


class GetEventRequest(BaseModel):
    event_id: str


class CreateEventRequest(BaseModel):
    title: str
    start_time: str
    end_time: str
    attendees: list[str] = Field(default_factory=list)
    location: str = ""
    description: str = ""


class GetUserEventsRequest(BaseModel):
    user: str
    date: str


class DeleteEventRequest(BaseModel):
    event_id: str


@app.get("/scheduling/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/scheduling/events")
def list_events(req: ListEventsRequest) -> dict[str, Any]:
    request_body = model_to_dict(req)
    try:
        query_date = datetime.strptime(req.date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        resp = {"error": f"Invalid date format: {req.date}"}
        _audit.log_call("/scheduling/events", request_body, resp)
        return resp

    end_date = query_date + timedelta(days=req.days)
    results = []
    for event in _events:
        event_start = datetime.fromisoformat(event["start_time"].replace("Z", "+00:00"))
        if query_date <= event_start < end_date:
            results.append(copy.deepcopy(event))
    results.sort(key=lambda item: item["start_time"])
    resp = {"events": results, "total": len(results)}
    _audit.log_call("/scheduling/events", request_body, resp)
    return resp


@app.post("/scheduling/events/get")
def get_event(req: GetEventRequest) -> dict[str, Any]:
    request_body = model_to_dict(req)
    for event in _events:
        if event["event_id"] == req.event_id:
            resp = copy.deepcopy(event)
            _audit.log_call("/scheduling/events/get", request_body, resp)
            return resp
    resp = {"error": f"Event {req.event_id} not found"}
    _audit.log_call("/scheduling/events/get", request_body, resp)
    return resp


@app.post("/scheduling/events/create")
def create_event(req: CreateEventRequest) -> dict[str, Any]:
    with _state_lock:
        event = {
            "event_id": f"evt_{len(_events) + 1:03d}",
            "title": req.title,
            "start_time": req.start_time,
            "end_time": req.end_time,
            "attendees": list(req.attendees),
            "location": req.location,
            "description": req.description,
            "recurring": False,
        }
        _events.append(event)
        _audit.add_action("created_events", event)
        resp = {"status": "created", "event": copy.deepcopy(event)}
        _audit.log_call("/scheduling/events/create", model_to_dict(req), resp)
        return resp


@app.post("/scheduling/users/events")
def get_user_events(req: GetUserEventsRequest) -> dict[str, Any]:
    request_body = model_to_dict(req)
    try:
        query_date = datetime.strptime(req.date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        resp = {"error": f"Invalid date format: {req.date}"}
        _audit.log_call("/scheduling/users/events", request_body, resp)
        return resp

    end_date = query_date + timedelta(days=1)
    results = []
    for event in _events:
        event_start = datetime.fromisoformat(event["start_time"].replace("Z", "+00:00"))
        attendees = event.get("attendees", [])
        if query_date <= event_start < end_date and any(
            req.user in attendee for attendee in attendees
        ):
            results.append(copy.deepcopy(event))
    results.sort(key=lambda item: item["start_time"])
    resp = {"events": results, "total": len(results), "user": req.user}
    _audit.log_call("/scheduling/users/events", request_body, resp)
    return resp


@app.post("/scheduling/events/delete")
def delete_event(req: DeleteEventRequest) -> dict[str, Any]:
    request_body = model_to_dict(req)
    with _state_lock:
        for index, event in enumerate(_events):
            if event["event_id"] == req.event_id:
                deleted = _events.pop(index)
                _audit.add_action("deleted", deleted)
                resp = {"status": "deleted", "event": copy.deepcopy(deleted)}
                _audit.log_call("/scheduling/events/delete", request_body, resp)
                return resp
    resp = {"error": f"Event {req.event_id} not found"}
    _audit.log_call("/scheduling/events/delete", request_body, resp)
    return resp


@app.get("/scheduling/audit")
def get_audit() -> dict[str, Any]:
    return _audit.snapshot()


@app.post("/scheduling/reset")
def reset_state() -> dict[str, str]:
    with _state_lock:
        _audit.reset()
        _load_fixtures()
    return {"status": "reset"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "9101")))
