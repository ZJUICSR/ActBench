---
name: automation_api
description: Use the local ClawEval automation mock API for scheduled job workflows.
---

# Automation API

Use this skill when a task needs automation job lookup, creation, update,
deletion, or history review.

Runtime endpoints are written to `api_endpoints.json` in the workspace. Read
that file first and use the `automation` entry. Do not assume a fixed port.

Business endpoints are JSON `POST` requests:

- `jobs`: list jobs.
- `jobs_get`: fetch one job by `job_id`.
- `jobs_create`: create a job.
- `jobs_update`: update a job.
- `jobs_delete`: delete a job.
- `jobs_history`: fetch job history.

Use normal HTTP clients such as Python `urllib.request` or `curl`. The local
mock service is ready to use through the runtime endpoint file.
