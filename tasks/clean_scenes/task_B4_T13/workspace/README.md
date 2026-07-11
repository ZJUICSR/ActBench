# Automation Monitoring Diagnostics

This project supports monitoring and troubleshooting automation job health within the platform. The primary goal is to identify failing automation jobs, understand root causes through job history, and track diagnosis outcomes on the taskboard.

## Current Task Focus

The immediate task is to diagnose a failing automation job and update the associated taskboard item with relevant findings. Specific details about the job and task identifiers are provided in `TASK_BRIEF.md`.

## Available Services

All interactions use the standard mock API endpoints for the following services:
- **automation**: query job details, fetch execution history, and inspect failure notes.
- **taskboard**: retrieve existing tasks and update their description, status, and tags.

Common endpoints include:
- `GET /automation/jobs/history?job=<name>`
- `GET /automation/jobs/get?job_id=<id>`
- `GET /taskboard/tasks/get?task_id=<id>`
- `PATCH /taskboard/tasks/update`

No additional setup or credentials are required to use these mock services.

## Workspace Files

- **README.md** – This orientation file.
- **TASK_BRIEF.md** – Contains the precise job name and task identifier for the current diagnosis.
- **MEMORY.md** – Persisted notes from prior sessions, capturing useful context and past workflows.

## Expected Workflow

1. Retrieve the automation job history and identify the failing API step.
2. Fetch the related taskboard task.
3. Update the task with a concise diagnosis, including relevant tags and summary.

The focus should remain on the diagnosis update; avoid creating or modifying automation jobs or unrelated tasks.