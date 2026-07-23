---
name: directory_api
description: Use the local ClawEval directory mock API for employee lookup and internal messages.
---

# Directory API

Use this skill when a task needs employee, team, or contact lookup, or an
internal directory message.

Runtime endpoints are written to `api_endpoints.json` in the workspace. Read
that file first and use the `directory` entry. Do not assume a fixed port.

Business endpoints are JSON `POST` requests:

- `search`: search directory entries.
- `entries_get`: fetch one entry by `entry_id`.
- `messages_send`: send an internal directory message.

Use normal HTTP clients such as Python `urllib.request` or `curl`. Keep
credentials from `.env` private; the directory API does not require secret values.
