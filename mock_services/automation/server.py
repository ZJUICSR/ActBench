"""Mock automation API service for ClawEval."""

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

app = FastAPI(title="ClawEval Mock Automation API")
add_error_injection(app)

FIXTURES_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "automation" / "jobs.json"

_jobs: list[dict[str, Any]] = []
_clock_now = utc_now()
_audit = AuditState(["created_jobs", "updated_jobs", "deleted_jobs"], now_fn=lambda: _clock_now)


def _now() -> datetime:
    return _clock_now
_state_lock = RLock()


def _load_fixtures() -> None:
    global _jobs, _clock_now
    _jobs = load_json_fixture("AUTOMATION_FIXTURES", FIXTURES_PATH)
    _clock_now = mock_now(
        service_name="automation",
        fixture=_jobs,
        field_names=("last_run", "next_run", "last_run_at", "next_run_at", "created_at", "updated_at", "timestamp"),
    )


_load_fixtures()


class ListJobsRequest(BaseModel):
    status: str | None = None
    enabled: bool | None = None
    tag: str | None = None


class GetJobRequest(BaseModel):
    job_id: str


class CreateJobRequest(BaseModel):
    name: str
    cron_expression: str
    action: str
    enabled: bool = True
    tags: list[str] | None = None
    created_by: str | None = None


class UpdateJobRequest(BaseModel):
    job_id: str
    enabled: bool | None = None
    cron_expression: str | None = None
    name: str | None = None
    action: str | None = None
    tags: list[str] | None = None


class DeleteJobRequest(BaseModel):
    job_id: str


class JobHistoryRequest(BaseModel):
    job_id: str
    limit: int = 10


@app.get("/automation/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/automation/jobs")
def list_jobs(req: ListJobsRequest | None = None) -> dict[str, Any]:
    req = req or ListJobsRequest()
    results = []
    for job in _jobs:
        if req.status and job.get("last_status") != req.status:
            continue
        if req.enabled is not None and job.get("enabled") != req.enabled:
            continue
        if req.tag and req.tag not in job.get("tags", []):
            continue
        results.append(
            {
                "job_id": job["job_id"],
                "name": job["name"],
                "cron_expression": job["cron_expression"],
                "enabled": job["enabled"],
                "last_status": job.get("last_status"),
                "last_run": job.get("last_run"),
                "next_run": job.get("next_run"),
                "tags": job.get("tags", []),
            }
        )
    resp = {"jobs": results, "total": len(results)}
    _audit.log_call("/automation/jobs", model_to_dict(req), resp)
    return resp


@app.post("/automation/jobs/get")
def get_job(req: GetJobRequest) -> dict[str, Any]:
    request_body = model_to_dict(req)
    for job in _jobs:
        if job["job_id"] == req.job_id:
            resp = copy.deepcopy(job)
            _audit.log_call("/automation/jobs/get", request_body, resp)
            return resp
    resp = {"error": f"Job {req.job_id} not found"}
    _audit.log_call("/automation/jobs/get", request_body, resp)
    return resp


@app.post("/automation/jobs/create")
def create_job(req: CreateJobRequest) -> dict[str, Any]:
    with _state_lock:
        job = {
            "job_id": f"JOB-{len(_jobs) + 1:03d}",
            "name": req.name,
            "cron_expression": req.cron_expression,
            "action": req.action,
            "enabled": req.enabled,
            "last_run": None,
            "next_run": None,
            "last_status": None,
            "created_by": req.created_by,
            "tags": req.tags or [],
            "created_at": _now().isoformat(),
            "execution_history": [],
        }
        _jobs.append(job)
        _audit.add_action("created_jobs", job)
        resp = {"status": "created", "job": copy.deepcopy(job)}
        _audit.log_call("/automation/jobs/create", model_to_dict(req), resp)
        return resp


@app.post("/automation/jobs/update")
def update_job(req: UpdateJobRequest) -> dict[str, Any]:
    request_body = model_to_dict(req)
    with _state_lock:
        for job in _jobs:
            if job["job_id"] == req.job_id:
                for field in ("enabled", "cron_expression", "name", "action", "tags"):
                    value = getattr(req, field)
                    if value is not None:
                        job[field] = value
                updated = copy.deepcopy(job)
                _audit.add_action("updated_jobs", updated)
                resp = {"status": "updated", "job": updated}
                _audit.log_call("/automation/jobs/update", request_body, resp)
                return resp
    resp = {"error": f"Job {req.job_id} not found"}
    _audit.log_call("/automation/jobs/update", request_body, resp)
    return resp


@app.post("/automation/jobs/delete")
def delete_job(req: DeleteJobRequest) -> dict[str, Any]:
    request_body = model_to_dict(req)
    with _state_lock:
        for index, job in enumerate(_jobs):
            if job["job_id"] == req.job_id:
                deleted = _jobs.pop(index)
                _audit.add_action("deleted_jobs", deleted)
                resp = {"status": "deleted", "job": copy.deepcopy(deleted)}
                _audit.log_call("/automation/jobs/delete", request_body, resp)
                return resp
    resp = {"error": f"Job {req.job_id} not found"}
    _audit.log_call("/automation/jobs/delete", request_body, resp)
    return resp


@app.post("/automation/jobs/history")
def job_history(req: JobHistoryRequest) -> dict[str, Any]:
    request_body = model_to_dict(req)
    for job in _jobs:
        if job["job_id"] == req.job_id:
            history = job.get("execution_history", [])
            resp = {"job_id": req.job_id, "history": history[: req.limit], "total": len(history)}
            _audit.log_call("/automation/jobs/history", request_body, resp)
            return resp
    resp = {"error": f"Job {req.job_id} not found"}
    _audit.log_call("/automation/jobs/history", request_body, resp)
    return resp


@app.get("/automation/audit")
def get_audit() -> dict[str, Any]:
    return _audit.snapshot()


@app.post("/automation/reset")
def reset_state() -> dict[str, str]:
    with _state_lock:
        _audit.reset()
        _load_fixtures()
    return {"status": "reset"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "9112")))
