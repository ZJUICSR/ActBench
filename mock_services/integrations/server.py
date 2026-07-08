"""Mock integrations registry API service for ClawEval."""

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

app = FastAPI(title="ClawEval Mock Integrations API")
add_error_injection(app)

FIXTURES_PATH = (
    Path(__file__).resolve().parents[1] / "fixtures" / "integrations" / "integrations.json"
)

_integrations: list[dict[str, Any]] = []
_clock_now = utc_now()
_audit = AuditState(["updates", "notifications"], now_fn=lambda: _clock_now)


def _now() -> datetime:
    return _clock_now
_state_lock = RLock()


def _load_fixtures() -> None:
    global _integrations, _clock_now
    _integrations = load_json_fixture("INTEGRATIONS_FIXTURES", FIXTURES_PATH)
    _clock_now = mock_now(
        service_name="integrations",
        fixture=_integrations,
        field_names=("last_verified", "last_checked_at", "updated_at", "created_at", "timestamp"),
    )


_load_fixtures()


class ListIntegrationsRequest(BaseModel):
    status: str | None = None


class GetIntegrationRequest(BaseModel):
    integration_id: str


class UpdateIntegrationRequest(BaseModel):
    integration_id: str
    status: str | None = None
    notes: str | None = None


class SendNotificationRequest(BaseModel):
    to: str
    subject: str
    body: str


@app.get("/integrations/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/integrations/items")
def list_integrations(req: ListIntegrationsRequest | None = None) -> dict[str, Any]:
    req = req or ListIntegrationsRequest()
    results = []
    for integration in _integrations:
        if req.status and integration.get("status") != req.status:
            continue
        results.append(
            {
                "integration_id": integration["integration_id"],
                "name": integration["name"],
                "service": integration["service"],
                "status": integration["status"],
                "last_verified": integration["last_verified"],
                "monthly_calls": integration["monthly_calls"],
                "error_rate": integration["error_rate"],
            }
        )
    resp = {"integrations": results, "total": len(results)}
    _audit.log_call("/integrations/items", model_to_dict(req), resp)
    return resp


@app.post("/integrations/items/get")
def get_integration(req: GetIntegrationRequest) -> dict[str, Any]:
    request_body = model_to_dict(req)
    for integration in _integrations:
        if integration["integration_id"] == req.integration_id:
            resp = copy.deepcopy(integration)
            _audit.log_call("/integrations/items/get", request_body, resp)
            return resp
    resp = {"error": f"Integration {req.integration_id} not found"}
    _audit.log_call("/integrations/items/get", request_body, resp)
    return resp


@app.post("/integrations/items/update")
def update_integration(req: UpdateIntegrationRequest) -> dict[str, Any]:
    request_body = model_to_dict(req)
    with _state_lock:
        for integration in _integrations:
            if integration["integration_id"] == req.integration_id:
                if req.status:
                    integration["status"] = req.status
                if req.notes:
                    integration["notes"] = req.notes
                update_record = {
                    "integration_id": req.integration_id,
                    "changes": request_body,
                    "timestamp": _now().isoformat(),
                }
                _audit.add_action("updates", update_record)
                resp = {"status": "updated", "integration": copy.deepcopy(integration)}
                _audit.log_call("/integrations/items/update", request_body, resp)
                return resp
    resp = {"error": f"Integration {req.integration_id} not found"}
    _audit.log_call("/integrations/items/update", request_body, resp)
    return resp


@app.post("/integrations/notify")
def send_notification(req: SendNotificationRequest) -> dict[str, Any]:
    notification = {
        "to": req.to,
        "subject": req.subject,
        "body": req.body,
        "timestamp": _now().isoformat(),
    }
    _audit.add_action("notifications", notification)
    resp = {"status": "sent", "notification": notification}
    _audit.log_call("/integrations/notify", model_to_dict(req), resp)
    return resp


@app.get("/integrations/audit")
def get_audit() -> dict[str, Any]:
    return _audit.snapshot()


@app.post("/integrations/reset")
def reset_state() -> dict[str, str]:
    with _state_lock:
        _audit.reset()
        _load_fixtures()
    return {"status": "reset"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "9111")))
