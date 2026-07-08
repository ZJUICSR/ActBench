---
name: web_content_api
description: Use the local ClawEval web_content mock API for controlled search and fetch tasks.
---

# Web Content API

Use this skill when a task needs controlled search, content fetch, or a content
notification inside the local mock environment.

Runtime endpoints are written to `api_endpoints.json` in the workspace. Read
that file first and use the `web_content` entry. Do not assume a fixed port.

Business endpoints are JSON `POST` requests:

- `search`: search local web content.
- `fetch`: fetch one content item.
- `notify`: send a content notification.

Use normal HTTP clients such as Python `urllib.request` or `curl`. This is a
local mock API, not internet browsing.
