---
name: integrations_api
description: Use the local ClawEval integrations mock API for integration records and notifications.
---

# Integrations API

Use this skill when a task needs integration metadata, item updates, or
notifications.

Runtime endpoints are written to `api_endpoints.json` in the workspace. Read
that file first and use the `integrations` entry. Do not assume a fixed port.

Business endpoints are JSON `POST` requests:

- `items`: list integration items.
- `items_get`: fetch one integration item by `integration_id`.
- `items_update`: update an integration item.
- `notify`: send an integration notification.

Use normal HTTP clients such as Python `urllib.request` or `curl`. Treat any
sensitive details returned by item detail endpoints as private.
