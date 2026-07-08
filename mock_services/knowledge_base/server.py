"""Mock knowledge base API service for ClawEval."""

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

app = FastAPI(title="ClawEval Mock Knowledge Base API")
add_error_injection(app)

FIXTURES_PATH = (
    Path(__file__).resolve().parents[1] / "fixtures" / "knowledge_base" / "articles.json"
)

_articles: list[dict[str, Any]] = []
_clock_now = utc_now()
_audit = AuditState(["updated_articles"], now_fn=lambda: _clock_now)


def _now() -> datetime:
    return _clock_now
_state_lock = RLock()


def _load_fixtures() -> None:
    global _articles, _clock_now
    _articles = load_json_fixture("KNOWLEDGE_BASE_FIXTURES", FIXTURES_PATH)
    _clock_now = mock_now(
        service_name="knowledge_base",
        fixture=_articles,
        field_names=("updated_at", "created_at", "published_at", "timestamp", "date"),
    )


_load_fixtures()


class SearchRequest(BaseModel):
    query: str
    category: str | None = None
    max_results: int = 10


class GetArticleRequest(BaseModel):
    article_id: str


class UpdateArticleRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    article_id: str
    title: str | None = None
    body: str | None = None
    tags: list[str] | None = None
    category: str | None = None
    updated_by: str | None = None


@app.get("/knowledge_base/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/knowledge_base/search")
def search(req: SearchRequest) -> dict[str, Any]:
    query = req.query.lower()
    results = []
    for article in _articles:
        if req.category and article.get("category") != req.category:
            continue
        haystack = " ".join(
            [
                article.get("title", ""),
                article.get("body", ""),
                " ".join(article.get("tags", [])),
            ]
        ).lower()
        if query in haystack:
            results.append(
                {
                    "article_id": article["article_id"],
                    "title": article["title"],
                    "category": article.get("category"),
                    "tags": article.get("tags", []),
                    "updated_at": article.get("updated_at"),
                    "snippet": article.get("body", "")[:240],
                }
            )
    resp = {"articles": results[: req.max_results], "total": len(results)}
    _audit.log_call("/knowledge_base/search", model_to_dict(req), resp)
    return resp


@app.post("/knowledge_base/articles/get")
def get_article(req: GetArticleRequest) -> dict[str, Any]:
    request_body = model_to_dict(req)
    for article in _articles:
        if article["article_id"] == req.article_id:
            resp = copy.deepcopy(article)
            _audit.log_call("/knowledge_base/articles/get", request_body, resp)
            return resp
    resp = {"error": f"Article {req.article_id} not found"}
    _audit.log_call("/knowledge_base/articles/get", request_body, resp)
    return resp


@app.post("/knowledge_base/articles/update")
def update_article(req: UpdateArticleRequest) -> dict[str, Any]:
    request_body = model_to_dict(req)
    with _state_lock:
        for article in _articles:
            if article["article_id"] == req.article_id:
                for field in ("title", "body", "tags", "category"):
                    value = getattr(req, field)
                    if value is not None:
                        article[field] = value
                article["updated_at"] = _now().isoformat()
                record = {
                    "article_id": req.article_id,
                    "changes": request_body,
                    "article": copy.deepcopy(article),
                    "updated_by": req.updated_by,
                    "timestamp": _now().isoformat(),
                }
                _audit.add_action("updated_articles", record)
                resp = {"status": "updated", "article": copy.deepcopy(article)}
                _audit.log_call("/knowledge_base/articles/update", request_body, resp)
                return resp
    resp = {"error": f"Article {req.article_id} not found"}
    _audit.log_call("/knowledge_base/articles/update", request_body, resp)
    return resp


@app.get("/knowledge_base/audit")
def get_audit() -> dict[str, Any]:
    return _audit.snapshot()


@app.post("/knowledge_base/reset")
def reset_state() -> dict[str, str]:
    with _state_lock:
        _audit.reset()
        _load_fixtures()
    return {"status": "reset"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "9115")))
