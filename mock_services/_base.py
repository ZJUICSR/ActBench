"""Shared helpers for local mock API services."""

from __future__ import annotations

import copy
import asyncio
import json
import os
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import RLock
from typing import Any, Callable

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

REPO_ROOT = Path(__file__).resolve().parents[1]
EXEMPT_SUFFIXES = ("/audit", "/reset", "/health", "/docs", "/openapi.json")
MOCK_ACTIVITY_TIME_FIELDS = (
    "date",
    "created_at",
    "updated_at",
    "timestamp",
    "posted_at",
    "published_at",
    "last_checked_at",
    "last_run",
    "next_run",
    "last_run_at",
    "next_run_at",
    "last_verified",
    "closed_at",
)
MOCK_BUSINESS_TIME_FIELDS = (
    "start_time",
    "end_time",
    "due_date",
    "renewal_date",
    "last_contact_date",
)
DEFAULT_MOCK_TIME_FIELDS = MOCK_ACTIVITY_TIME_FIELDS


def load_json_fixture(env_var: str, default_path: Path) -> Any:
    """Load a JSON fixture from an env override or repo-local default."""
    path = Path(os.environ.get(env_var, str(default_path)))
    if not path.is_absolute():
        path = REPO_ROOT / path
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def model_to_dict(model: Any) -> dict[str, Any]:
    """Return a Pydantic model as a dict for both v1 and v2."""
    if model is None:
        return {}
    if hasattr(model, "model_dump"):
        return model.model_dump(exclude_none=True)
    if hasattr(model, "dict"):
        return model.dict(exclude_none=True)
    if isinstance(model, dict):
        return model
    return {}


def utc_now() -> datetime:
    """Return the real current UTC time for services without a mock clock."""
    return datetime.now(timezone.utc)


def parse_mock_datetime(value: Any) -> datetime | None:
    """Parse fixture/env datetime strings into timezone-aware UTC datetimes."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _parse_fixture_datetime(value: Any) -> datetime | None:
    return parse_mock_datetime(value)


def _iter_fixture_records(fixture: Any):
    if isinstance(fixture, dict):
        yield fixture
        for value in fixture.values():
            yield from _iter_fixture_records(value)
    elif isinstance(fixture, list):
        for item in fixture:
            yield from _iter_fixture_records(item)


def fixture_relative_now(
    fixture: Any,
    *,
    field_names: tuple[str, ...] = ("date",),
    offset: timedelta = timedelta(seconds=1),
    fallback: Callable[[], datetime] = utc_now,
) -> datetime:
    """Derive a deterministic mock 'now' from the latest timestamp in fixture data."""
    parsed_dates = collect_fixture_datetimes(fixture, field_names=field_names)
    if parsed_dates:
        return max(parsed_dates) + offset
    fallback_value = fallback()
    if fallback_value.tzinfo is None:
        return fallback_value.replace(tzinfo=timezone.utc)
    return fallback_value.astimezone(timezone.utc)


def collect_fixture_datetimes(
    fixture: Any,
    *,
    field_names: tuple[str, ...] = DEFAULT_MOCK_TIME_FIELDS,
) -> list[datetime]:
    """Collect all parseable UTC datetimes from named fields in fixture data."""
    parsed_dates: list[datetime] = []
    fields = set(field_names)
    for record in _iter_fixture_records(fixture):
        for field in fields:
            parsed = parse_mock_datetime(record.get(field))
            if parsed is not None:
                parsed_dates.append(parsed)
    return parsed_dates


def mock_now(
    *,
    service_name: str | None = None,
    fixture: Any | None = None,
    field_names: tuple[str, ...] = DEFAULT_MOCK_TIME_FIELDS,
) -> datetime:
    """Return the configured mock clock, falling back to fixture-relative time."""
    if service_name:
        service_env = f"{service_name.upper()}_MOCK_NOW"
        parsed = parse_mock_datetime(os.environ.get(service_env))
        if parsed is not None:
            return parsed
    parsed = parse_mock_datetime(os.environ.get("CLAWEVAL_MOCK_NOW"))
    if parsed is not None:
        return parsed
    if fixture is not None:
        return fixture_relative_now(fixture, field_names=field_names)
    return utc_now()


class AuditState:
    """In-memory audit log plus named side-effect buckets."""

    def __init__(self, action_keys: list[str], now_fn: Callable[[], datetime] | None = None):
        self.action_keys = action_keys
        self._now_fn = now_fn or utc_now
        self._lock = RLock()
        self.calls: list[dict[str, Any]] = []
        self.actions: dict[str, list[dict[str, Any]]] = {key: [] for key in action_keys}

    def log_call(self, endpoint: str, request_body: dict[str, Any], response_body: Any) -> None:
        with self._lock:
            self.calls.append(
                {
                    "endpoint": endpoint,
                    "request_body": copy.deepcopy(request_body),
                    "response_body": copy.deepcopy(response_body),
                    "timestamp": self._now_fn().isoformat(),
                }
            )

    def add_action(self, key: str, value: dict[str, Any]) -> None:
        with self._lock:
            if key not in self.actions:
                self.actions[key] = []
            self.actions[key].append(copy.deepcopy(value))

    def next_action_id(self, key: str, prefix: str, separator: str = "-") -> str:
        with self._lock:
            index = len(self.actions.get(key, [])) + 1
        return f"{prefix}{separator}{index:03d}"

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {"calls": copy.deepcopy(self.calls), **copy.deepcopy(self.actions)}

    def reset(self) -> None:
        with self._lock:
            self.calls = []
            self.actions = {key: [] for key in self.action_keys}


def _should_inject_error() -> bool:
    return random.random() < float(os.environ.get("ERROR_RATE", "0"))


class ErrorInjectionMiddleware(BaseHTTPMiddleware):
    """Optionally inject rate limits, server errors, or latency into POST endpoints."""

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if any(path.endswith(suffix) for suffix in EXEMPT_SUFFIXES):
            return await call_next(request)
        if request.headers.get("X-Health-Check") == "1":
            return await call_next(request)
        if request.method != "POST" or not _should_inject_error():
            return await call_next(request)

        error_type = random.choices(
            ["rate_limit", "server_error", "slow"],
            weights=[0.35, 0.35, 0.30],
            k=1,
        )[0]
        if error_type == "rate_limit":
            return JSONResponse(
                status_code=429,
                content={
                    "error": "rate_limit_exceeded",
                    "message": "Too many requests. Please retry after a short delay.",
                    "retry_after_seconds": 2,
                },
                headers={"Retry-After": "2"},
            )
        if error_type == "server_error":
            return JSONResponse(
                status_code=500,
                content={
                    "error": "internal_server_error",
                    "message": "An unexpected error occurred. Please try again.",
                },
            )

        await asyncio.sleep(random.uniform(2.0, 4.0))
        return await call_next(request)


def add_error_injection(app: Any) -> None:
    app.add_middleware(ErrorInjectionMiddleware)
