"""Mock ledger API service for ClawEval."""

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

app = FastAPI(title="ClawEval Mock Ledger API")
add_error_injection(app)

FIXTURES_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "ledger" / "transactions.json"

_transactions: list[dict[str, Any]] = []
_clock_now = utc_now()
_audit = AuditState(["submitted_reports", "created_payments"], now_fn=lambda: _clock_now)


def _now() -> datetime:
    return _clock_now
_state_lock = RLock()


def _load_fixtures() -> None:
    global _transactions, _clock_now
    _transactions = load_json_fixture("LEDGER_FIXTURES", FIXTURES_PATH)
    _clock_now = mock_now(
        service_name="ledger",
        fixture=_transactions,
        field_names=("date", "posted_at", "created_at", "updated_at", "timestamp"),
    )


_load_fixtures()


class ListTransactionsRequest(BaseModel):
    account: str | None = None
    status: str | None = None
    category: str | None = None


class GetTransactionRequest(BaseModel):
    transaction_id: str


class SubmitReportRequest(BaseModel):
    title: str
    summary: str
    transaction_ids: list[str] = Field(default_factory=list)
    submitted_by: str | None = None


class CreatePaymentRequest(BaseModel):
    payee: str
    amount: float
    currency: str = "USD"
    memo: str | None = None
    requested_by: str | None = None


@app.get("/ledger/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/ledger/transactions")
def list_transactions(req: ListTransactionsRequest | None = None) -> dict[str, Any]:
    req = req or ListTransactionsRequest()
    results = []
    for transaction in _transactions:
        if req.account and transaction.get("account") != req.account:
            continue
        if req.status and transaction.get("status") != req.status:
            continue
        if req.category and transaction.get("category") != req.category:
            continue
        results.append(copy.deepcopy(transaction))
    resp = {"transactions": results, "total": len(results)}
    _audit.log_call("/ledger/transactions", model_to_dict(req), resp)
    return resp


@app.post("/ledger/transactions/get")
def get_transaction(req: GetTransactionRequest) -> dict[str, Any]:
    request_body = model_to_dict(req)
    for transaction in _transactions:
        if transaction["transaction_id"] == req.transaction_id:
            resp = copy.deepcopy(transaction)
            _audit.log_call("/ledger/transactions/get", request_body, resp)
            return resp
    resp = {"error": f"Transaction {req.transaction_id} not found"}
    _audit.log_call("/ledger/transactions/get", request_body, resp)
    return resp


@app.post("/ledger/reports/submit")
def submit_report(req: SubmitReportRequest) -> dict[str, Any]:
    request_body = model_to_dict(req)
    with _state_lock:
        known_ids = {transaction["transaction_id"] for transaction in _transactions}
        missing_ids = [txn_id for txn_id in req.transaction_ids if txn_id not in known_ids]
        if missing_ids:
            resp = {"error": "Unknown transactions", "missing_transaction_ids": missing_ids}
            _audit.log_call("/ledger/reports/submit", request_body, resp)
            return resp
        report = {
            "report_id": _audit.next_action_id("submitted_reports", "RPT"),
            "title": req.title,
            "summary": req.summary,
            "transaction_ids": list(req.transaction_ids),
            "submitted_by": req.submitted_by,
            "timestamp": _now().isoformat(),
        }
        _audit.add_action("submitted_reports", report)
        resp = {"status": "submitted", "report": report}
        _audit.log_call("/ledger/reports/submit", request_body, resp)
        return resp


@app.post("/ledger/payments/create")
def create_payment(req: CreatePaymentRequest) -> dict[str, Any]:
    request_body = model_to_dict(req)
    with _state_lock:
        if not req.payee.strip():
            resp = {"error": "Payee is required"}
            _audit.log_call("/ledger/payments/create", request_body, resp)
            return resp
        if req.amount <= 0:
            resp = {"error": "Payment amount must be positive"}
            _audit.log_call("/ledger/payments/create", request_body, resp)
            return resp
        payment = {
            "payment_id": _audit.next_action_id("created_payments", "PAY"),
            "payee": req.payee,
            "amount": req.amount,
            "currency": req.currency,
            "memo": req.memo,
            "requested_by": req.requested_by,
            "timestamp": _now().isoformat(),
        }
        _audit.add_action("created_payments", payment)
        resp = {"status": "created", "payment": payment}
        _audit.log_call("/ledger/payments/create", request_body, resp)
        return resp


@app.get("/ledger/audit")
def get_audit() -> dict[str, Any]:
    return _audit.snapshot()


@app.post("/ledger/reset")
def reset_state() -> dict[str, str]:
    with _state_lock:
        _audit.reset()
        _load_fixtures()
    return {"status": "reset"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "9117")))
