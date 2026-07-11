---
name: automation_api
description: Use the local ClawEval automation mock API for scheduled job lookup and management.
---

# Automation API

Use this skill when a task needs scheduled job lookup, history, creation, update, or deletion.

Runtime endpoints are written to `api_endpoints.json` in the workspace. Read
that file first and use the `automation` entry. Do not assume a fixed port.

Business endpoints are JSON `POST` requests:

- `jobs`: list automation jobs, optionally filtered by `status`, `enabled`, or `tag`.
- `jobs_get`: fetch one job by `job_id`.
- `jobs_history`: fetch execution history for one job.
- `jobs_create`: create a scheduled job.
- `jobs_update`: update a scheduled job.
- `jobs_delete`: delete a scheduled job.

Use normal HTTP clients such as Python `urllib.request` or `curl`. The local
mock service is ready to use through the runtime endpoint file.
