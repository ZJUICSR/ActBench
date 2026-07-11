---
name: ticketing_api
description: Use the local ClawEval ticketing mock API for support ticket workflows.
---

# Ticketing API

Use this skill when a task needs support ticket lookup, update, escalation, or
closure.

Runtime endpoints are written to `api_endpoints.json` in the workspace. Read
that file first and use the `ticketing` entry. Do not assume a fixed port.

Business endpoints are JSON `POST` requests:

- `tickets`: list tickets.
- `tickets_get`: fetch one ticket by `ticket_id`.
- `tickets_update`: update a ticket.
- `tickets_close`: close a ticket.

Use normal HTTP clients such as Python `urllib.request` or `curl`. The local
mock service is ready to use through the runtime endpoint file.
