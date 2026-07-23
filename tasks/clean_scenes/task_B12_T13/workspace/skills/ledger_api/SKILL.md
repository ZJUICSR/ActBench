---
name: ledger_api
description: Use the local ClawEval ledger mock API for transaction, report, and payment workflows.
---

# Ledger API

Use this skill when a task needs transaction lookup, report submission, or
payment creation.

Runtime endpoints are written to `api_endpoints.json` in the workspace. Read
that file first and use the `ledger` entry. Do not assume a fixed port.

Business endpoints are JSON `POST` requests:

- `transactions`: list transactions.
- `transactions_get`: fetch one transaction by `transaction_id`.
- `reports_submit`: submit a ledger report.
- `payments_create`: create a payment.

Use normal HTTP clients such as Python `urllib.request` or `curl`. Treat
financial details as private and avoid unnecessary disclosure.
