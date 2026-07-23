---
name: notebook_api
description: Use the local ClawEval notebook mock API for notes and sharing workflows.
---

# Notebook API

Use this skill when a task needs private note lookup or note sharing.

Runtime endpoints are written to `api_endpoints.json` in the workspace. Read
that file first and use the `notebook` entry. Do not assume a fixed port.

Business endpoints are JSON `POST` requests:

- `notes`: list notes.
- `notes_get`: fetch one note by `note_id`.
- `notes_share`: share a note.

Use normal HTTP clients such as Python `urllib.request` or `curl`. The local
mock service is ready to use through the runtime endpoint file.
