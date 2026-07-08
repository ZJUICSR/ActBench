"""Mock taskboard API service for ClawEval."""

from __future__ import annotations

import copy
import os
import sys
from datetime import datetime
from pathlib import Path
from threading import RLock
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel, Field

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from mock_services._base import AuditState, add_error_injection, load_json_fixture, mock_now, model_to_dict, utc_now

app = FastAPI(title="ClawEval Mock Taskboard API")
add_error_injection(app)

FIXTURES_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "taskboard" / "tasks.json"

_tasks: list[dict[str, Any]] = []
_clock_now = utc_now()
_audit = AuditState(["created_tasks", "updated_tasks", "deleted"], now_fn=lambda: _clock_now)


def _now() -> datetime:
    return _clock_now
_state_lock = RLock()


def _load_fixtures() -> None:
    global _tasks, _clock_now
    _tasks = load_json_fixture("TASKBOARD_FIXTURES", FIXTURES_PATH)
    _clock_now = mock_now(
        service_name="taskboard",
        fixture=_tasks,
        field_names=("created_at", "updated_at", "timestamp"),
    )


_load_fixtures()


class ListTasksRequest(BaseModel):
    status: str | None = None
    priority: str | None = None


class GetTaskRequest(BaseModel):
    task_id: str


class CreateTaskRequest(BaseModel):
    title: str
    description: str | None = None
    priority: str = "medium"
    due_date: str | None = None
    tags: list[str] = Field(default_factory=list)


class UpdateTaskRequest(BaseModel):
    task_id: str
    title: str | None = None
    description: str | None = None
    priority: str | None = None
    status: str | None = None
    tags: list[str] | None = None


class DeleteTaskRequest(BaseModel):
    task_id: str


@app.get("/taskboard/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/taskboard/tasks")
def list_tasks(req: ListTasksRequest | None = None) -> dict[str, Any]:
    req = req or ListTasksRequest()
    results = []
    for task in _tasks:
        if req.status and task.get("status") != req.status:
            continue
        if req.priority and task.get("priority") != req.priority:
            continue
        results.append(copy.deepcopy(task))
    resp = {"tasks": results, "total": len(results)}
    _audit.log_call("/taskboard/tasks", model_to_dict(req), resp)
    return resp


@app.post("/taskboard/tasks/get")
def get_task(req: GetTaskRequest) -> dict[str, Any]:
    request_body = model_to_dict(req)
    for task in _tasks:
        if task["task_id"] == req.task_id:
            resp = copy.deepcopy(task)
            _audit.log_call("/taskboard/tasks/get", request_body, resp)
            return resp
    resp = {"error": f"Task {req.task_id} not found"}
    _audit.log_call("/taskboard/tasks/get", request_body, resp)
    return resp


@app.post("/taskboard/tasks/create")
def create_task(req: CreateTaskRequest) -> dict[str, Any]:
    with _state_lock:
        task = {
            "task_id": f"task_{len(_tasks) + 1:03d}",
            "title": req.title,
            "description": req.description or "",
            "priority": req.priority,
            "status": "pending",
            "due_date": req.due_date,
            "tags": list(req.tags),
            "created_at": _now().isoformat(),
        }
        _tasks.append(task)
        _audit.add_action("created_tasks", task)
        resp = {"status": "created", "task": copy.deepcopy(task)}
        _audit.log_call("/taskboard/tasks/create", model_to_dict(req), resp)
        return resp


@app.post("/taskboard/tasks/update")
def update_task(req: UpdateTaskRequest) -> dict[str, Any]:
    request_body = model_to_dict(req)
    with _state_lock:
        for task in _tasks:
            if task["task_id"] == req.task_id:
                for field in ("title", "description", "priority", "status", "tags"):
                    value = getattr(req, field)
                    if value is not None:
                        task[field] = value
                record = {
                    "task_id": req.task_id,
                    "changes": request_body,
                    "task": copy.deepcopy(task),
                    "timestamp": _now().isoformat(),
                }
                _audit.add_action("updated_tasks", record)
                resp = {"status": "updated", "task": copy.deepcopy(task)}
                _audit.log_call("/taskboard/tasks/update", request_body, resp)
                return resp
    resp = {"error": f"Task {req.task_id} not found"}
    _audit.log_call("/taskboard/tasks/update", request_body, resp)
    return resp


@app.post("/taskboard/tasks/delete")
def delete_task(req: DeleteTaskRequest) -> dict[str, Any]:
    request_body = model_to_dict(req)
    with _state_lock:
        for index, task in enumerate(_tasks):
            if task["task_id"] == req.task_id:
                deleted = _tasks.pop(index)
                record = {
                    "task_id": req.task_id,
                    "task": copy.deepcopy(deleted),
                    "timestamp": _now().isoformat(),
                }
                _audit.add_action("deleted", record)
                resp = {"status": "deleted", "task": copy.deepcopy(deleted)}
                _audit.log_call("/taskboard/tasks/delete", request_body, resp)
                return resp
    resp = {"error": f"Task {req.task_id} not found"}
    _audit.log_call("/taskboard/tasks/delete", request_body, resp)
    return resp


@app.get("/taskboard/audit")
def get_audit() -> dict[str, Any]:
    return _audit.snapshot()


@app.post("/taskboard/reset")
def reset_state() -> dict[str, str]:
    with _state_lock:
        _audit.reset()
        _load_fixtures()
    return {"status": "reset"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "9102")))
