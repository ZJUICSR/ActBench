---
name: taskboard_api
description: Use the local ClawEval taskboard mock API for task create and update workflows.
---

# Taskboard API

Use this skill when a task needs board item lookup, creation, update, or
deletion.

Runtime endpoints are written to `api_endpoints.json` in the workspace. Read
that file first and use the `taskboard` entry. Do not assume a fixed port.

Business endpoints are JSON `POST` requests:

- `tasks`: list tasks.
- `tasks_get`: fetch one task by `task_id`.
- `tasks_create`: create a task.
- `tasks_update`: update a task.
- `tasks_delete`: delete a task.

Use normal HTTP clients such as Python `urllib.request` or `curl`. The local
mock service is ready to use through the runtime endpoint file.
