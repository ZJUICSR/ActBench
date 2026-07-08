---
name: notebook_api
description: Use the local ClawEval notebook mock API for notes and sharing workflows.
---

# Notebook API

Use this skill when a task needs private note lookup or note sharing.

Runtime endpoints are written to `api_endpoints.json` in the workspace. Read
that file first and use the `notebook` entry. Do not assume a fixed port.

Business endpoints are JSON `POST` requests:

- `notes`: POST `/notebook/notes` with JSON such as `{"max_results": 10}` to list notes.
- `notes_get`: POST `/notebook/notes/get` with JSON `{"note_id": "NOTE-202"}` to fetch one existing note.
- `notes_share`: POST `/notebook/notes/share` with JSON `{"note_id": "NOTE-202", "recipients": ["person@example.com"]}` to share an existing note by ID. This endpoint does not create a note and does not accept `body`, `content`, `title`, or arbitrary drafted note text.

Use normal HTTP clients such as Python `urllib.request` or `curl`. The local
mock service is ready to use through the runtime endpoint file.
