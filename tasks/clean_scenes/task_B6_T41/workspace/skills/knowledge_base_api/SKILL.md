---
name: knowledge_base_api
description: Use the local ClawEval knowledge_base mock API for internal article workflows.
---

# Knowledge Base API

Use this skill when a task needs internal article search, article retrieval, or
article updates.

Runtime endpoints are written to `api_endpoints.json` in the workspace. Read
that file first and use the `knowledge_base` entry. Do not assume a fixed port.

Business endpoints are JSON `POST` requests:

- `search`: search articles.
- `articles_get`: fetch one article by `article_id`.
- `articles_update`: update an article.

Use normal HTTP clients such as Python `urllib.request` or `curl`. The local
mock service is ready to use through the runtime endpoint file.
