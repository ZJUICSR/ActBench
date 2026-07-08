"""Mock ticketing API service for ClawEval."""

from __future__ import annotations

import copy
import os
import sys
from datetime import datetime
from pathlib import Path
from threading import RLock
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel, ConfigDict

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from mock_services._base import AuditState, add_error_injection, load_json_fixture, mock_now, model_to_dict, utc_now

app = FastAPI(title="ClawEval Mock Ticketing API")
add_error_injection(app)

FIXTURES_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "ticketing" / "tickets.json"

_tickets: list[dict[str, Any]] = []
_clock_now = utc_now()
_audit = AuditState(["closed", "updated_tickets"], now_fn=lambda: _clock_now)


def _now() -> datetime:
    return _clock_now
_state_lock = RLock()


def _load_fixtures() -> None:
    global _tickets, _clock_now
    _tickets = load_json_fixture("TICKETING_FIXTURES", FIXTURES_PATH)
    _clock_now = mock_now(
        service_name="ticketing",
        fixture=_tickets,
        field_names=("created_at", "updated_at", "closed_at", "timestamp"),
    )


_load_fixtures()


class ListTicketsRequest(BaseModel):
    status: str = "open"


class GetTicketRequest(BaseModel):
    ticket_id: str


class UpdateTicketRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    ticket_id: str
    priority: str | None = None
    tags: list[str] | None = None
    category: str | None = None


class CloseTicketRequest(BaseModel):
    ticket_id: str
    resolution: str


@app.get("/ticketing/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/ticketing/tickets")
def list_tickets(req: ListTicketsRequest | None = None) -> dict[str, Any]:
    req = req or ListTicketsRequest()
    results = []
    for ticket in _tickets:
        if req.status != "all" and ticket.get("status") != req.status:
            continue
        results.append(
            {
                "ticket_id": ticket["ticket_id"],
                "title": ticket["title"],
                "reporter": ticket["reporter"],
                "department": ticket["department"],
                "priority": ticket["priority"],
                "status": ticket["status"],
                "created_at": ticket["created_at"],
            }
        )
    resp = {"tickets": results, "total": len(results)}
    _audit.log_call("/ticketing/tickets", model_to_dict(req), resp)
    return resp


@app.post("/ticketing/tickets/get")
def get_ticket(req: GetTicketRequest) -> dict[str, Any]:
    request_body = model_to_dict(req)
    for ticket in _tickets:
        if ticket["ticket_id"] == req.ticket_id:
            resp = copy.deepcopy(ticket)
            _audit.log_call("/ticketing/tickets/get", request_body, resp)
            return resp
    resp = {"error": f"Ticket {req.ticket_id} not found"}
    _audit.log_call("/ticketing/tickets/get", request_body, resp)
    return resp


@app.post("/ticketing/tickets/update")
def update_ticket(req: UpdateTicketRequest) -> dict[str, Any]:
    request_body = model_to_dict(req)
    with _state_lock:
        for ticket in _tickets:
            if ticket["ticket_id"] == req.ticket_id:
                if req.priority is not None:
                    ticket["priority"] = req.priority
                if req.tags is not None:
                    ticket["tags"] = req.tags
                if req.category is not None:
                    ticket["category"] = req.category
                updated = copy.deepcopy(ticket)
                _audit.add_action("updated_tickets", updated)
                resp = {"status": "updated", "ticket": updated}
                _audit.log_call("/ticketing/tickets/update", request_body, resp)
                return resp
    resp = {"error": f"Ticket {req.ticket_id} not found"}
    _audit.log_call("/ticketing/tickets/update", request_body, resp)
    return resp


@app.post("/ticketing/tickets/close")
def close_ticket(req: CloseTicketRequest) -> dict[str, Any]:
    request_body = model_to_dict(req)
    with _state_lock:
        for ticket in _tickets:
            if ticket["ticket_id"] == req.ticket_id:
                ticket["status"] = "closed"
                ticket["resolution"] = req.resolution
                ticket["closed_at"] = _now().isoformat()
                closed = copy.deepcopy(ticket)
                _audit.add_action("closed", closed)
                resp = {"status": "closed", "ticket": closed}
                _audit.log_call("/ticketing/tickets/close", request_body, resp)
                return resp
    resp = {"error": f"Ticket {req.ticket_id} not found"}
    _audit.log_call("/ticketing/tickets/close", request_body, resp)
    return resp


@app.get("/ticketing/audit")
def get_audit() -> dict[str, Any]:
    return _audit.snapshot()


@app.post("/ticketing/reset")
def reset_state() -> dict[str, str]:
    with _state_lock:
        _audit.reset()
        _load_fixtures()
    return {"status": "reset"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "9107")))
