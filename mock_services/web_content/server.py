"""Mock search/fetch web content API service for ClawEval."""

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

app = FastAPI(title="ClawEval Mock Web Content API")
add_error_injection(app)

FIXTURES_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "web_content" / "content.json"

_data: dict[str, Any] = {}
_clock_now = utc_now()
_audit = AuditState(["notifications"], now_fn=lambda: _clock_now)


def _now() -> datetime:
    return _clock_now


def _load_fixtures() -> None:
    global _data, _clock_now
    _data = load_json_fixture("WEB_CONTENT_FIXTURES", FIXTURES_PATH)
    _clock_now = mock_now(
        service_name="web_content",
        fixture=_data,
        field_names=("published_at", "updated_at", "date", "timestamp"),
    )


_load_fixtures()


class SearchRequest(BaseModel):
    query: str
    max_results: int = 5


class FetchRequest(BaseModel):
    url: str


class NotifyRequest(BaseModel):
    channel: str
    message: str


@app.get("/web_content/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/web_content/search")
def search(req: SearchRequest) -> dict[str, Any]:
    query = req.query.lower()
    matches = []
    for group in _data.get("search_results", []):
        keywords = [str(keyword).lower() for keyword in group.get("query_keywords", [])]
        if keywords and not any(keyword in query for keyword in keywords):
            continue
        matches.extend(copy.deepcopy(group.get("results", [])))
    if not matches:
        for page in _data.get("pages", []):
            haystack = f"{page.get('title', '')} {page.get('content', '')}".lower()
            if any(term in haystack for term in query.split()):
                matches.append(
                    {
                        "title": page.get("title", page["url"]),
                        "url": page["url"],
                        "snippet": page.get("snippet", page.get("content", "")[:180]),
                    }
                )
    resp = {"results": matches[: req.max_results], "total": len(matches)}
    _audit.log_call("/web_content/search", model_to_dict(req), resp)
    return resp


@app.post("/web_content/fetch")
def fetch(req: FetchRequest) -> dict[str, Any]:
    request_body = model_to_dict(req)
    for page in _data.get("pages", []):
        if page["url"] == req.url:
            resp = copy.deepcopy(page)
            _audit.log_call("/web_content/fetch", request_body, resp)
            return resp
    resp = {"error": f"URL {req.url} not found"}
    _audit.log_call("/web_content/fetch", request_body, resp)
    return resp


@app.post("/web_content/notify")
def notify(req: NotifyRequest) -> dict[str, Any]:
    notification = {
        "channel": req.channel,
        "message": req.message,
        "timestamp": _now().isoformat(),
    }
    _audit.add_action("notifications", notification)
    resp = {"status": "sent", "notification": notification}
    _audit.log_call("/web_content/notify", model_to_dict(req), resp)
    return resp


@app.get("/web_content/audit")
def get_audit() -> dict[str, Any]:
    return _audit.snapshot()


@app.post("/web_content/reset")
def reset_state() -> dict[str, str]:
    _audit.reset()
    _load_fixtures()
    return {"status": "reset"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "9114")))
