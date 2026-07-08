"""Mock customer records API service for ClawEval."""

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

app = FastAPI(title="ClawEval Mock Customer Records API")
add_error_injection(app)

FIXTURES_PATH = (
    Path(__file__).resolve().parents[1] / "fixtures" / "customer_records" / "customers.json"
)

_customers: list[dict[str, Any]] = []
_clock_now = utc_now()
_audit = AuditState(["created_followups", "exports"], now_fn=lambda: _clock_now)


def _now() -> datetime:
    return _clock_now
_state_lock = RLock()


def _load_fixtures() -> None:
    global _customers, _clock_now
    _customers = load_json_fixture("CUSTOMER_RECORDS_FIXTURES", FIXTURES_PATH)
    _clock_now = mock_now(
        service_name="customer_records",
        fixture=_customers,
        field_names=("created_at", "updated_at", "last_contact_date", "timestamp"),
    )


_load_fixtures()


class ListCustomersRequest(BaseModel):
    status: str | None = None
    tier: str | None = None
    owner: str | None = None


class GetCustomerRequest(BaseModel):
    customer_id: str


class CreateFollowupRequest(BaseModel):
    customer_id: str
    owner: str
    note: str
    due_date: str | None = None
    priority: str = "medium"


class ExportRequest(BaseModel):
    segment: str | None = None
    include_contacts: bool = False
    requested_by: str | None = None
    reason: str | None = None


@app.get("/customer_records/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/customer_records/customers")
def list_customers(req: ListCustomersRequest | None = None) -> dict[str, Any]:
    req = req or ListCustomersRequest()
    results = []
    for customer in _customers:
        if req.status and customer.get("status") != req.status:
            continue
        if req.tier and customer.get("tier") != req.tier:
            continue
        if req.owner and customer.get("owner") != req.owner:
            continue
        results.append(
            {
                "customer_id": customer["customer_id"],
                "name": customer["name"],
                "tier": customer.get("tier"),
                "owner": customer.get("owner"),
                "status": customer.get("status"),
                "renewal_date": customer.get("renewal_date"),
                "health_score": customer.get("health_score"),
            }
        )
    resp = {"customers": results, "total": len(results)}
    _audit.log_call("/customer_records/customers", model_to_dict(req), resp)
    return resp


@app.post("/customer_records/customers/get")
def get_customer(req: GetCustomerRequest) -> dict[str, Any]:
    request_body = model_to_dict(req)
    for customer in _customers:
        if customer["customer_id"] == req.customer_id:
            resp = copy.deepcopy(customer)
            _audit.log_call("/customer_records/customers/get", request_body, resp)
            return resp
    resp = {"error": f"Customer {req.customer_id} not found"}
    _audit.log_call("/customer_records/customers/get", request_body, resp)
    return resp


@app.post("/customer_records/followups/create")
def create_followup(req: CreateFollowupRequest) -> dict[str, Any]:
    request_body = model_to_dict(req)
    with _state_lock:
        customer = next(
            (item for item in _customers if item["customer_id"] == req.customer_id),
            None,
        )
        if customer is None:
            resp = {"error": f"Customer {req.customer_id} not found"}
            _audit.log_call("/customer_records/followups/create", request_body, resp)
            return resp
        followup = {
            "followup_id": _audit.next_action_id("created_followups", "FU"),
            "customer_id": req.customer_id,
            "customer_name": customer.get("name"),
            "owner": req.owner,
            "note": req.note,
            "due_date": req.due_date,
            "priority": req.priority,
            "created_at": _now().isoformat(),
        }
        _audit.add_action("created_followups", followup)
        resp = {"status": "created", "followup": followup}
        _audit.log_call("/customer_records/followups/create", request_body, resp)
        return resp


@app.post("/customer_records/export")
def export_customers(req: ExportRequest) -> dict[str, Any]:
    request_body = model_to_dict(req)
    rows = []
    for customer in _customers:
        if (
            req.segment
            and customer.get("tier") != req.segment
            and customer.get("status") != req.segment
        ):
            continue
        row = {
            "customer_id": customer["customer_id"],
            "name": customer["name"],
            "tier": customer.get("tier"),
            "status": customer.get("status"),
            "owner": customer.get("owner"),
            "renewal_date": customer.get("renewal_date"),
        }
        if req.include_contacts:
            row["contacts"] = copy.deepcopy(customer.get("contacts", []))
        rows.append(row)
    with _state_lock:
        export_record = {
            "export_id": _audit.next_action_id("exports", "EXP"),
            "segment": req.segment,
            "include_contacts": req.include_contacts,
            "requested_by": req.requested_by,
            "reason": req.reason,
            "row_count": len(rows),
            "timestamp": _now().isoformat(),
        }
        _audit.add_action("exports", export_record)
        resp = {"status": "exported", "export": export_record, "rows": rows}
        _audit.log_call("/customer_records/export", request_body, resp)
        return resp


@app.get("/customer_records/audit")
def get_audit() -> dict[str, Any]:
    return _audit.snapshot()


@app.post("/customer_records/reset")
def reset_state() -> dict[str, str]:
    with _state_lock:
        _audit.reset()
        _load_fixtures()
    return {"status": "reset"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "9116")))
