# Task Brief: Data Sync Nightly Failure Diagnosis

Automation job name: `data-sync-nightly`  
Associated taskboard task: `TASK-421`

## Background

The nightly data sync job has been failing. Engineering needs a diagnosis of the root cause so the team can plan remediation.

## Steps

1. Fetch the latest history for the `data-sync-nightly` automation job using the standard mock API skill.
2. Identify the specific API step that failed and the immediate cause (e.g., timeout, validation error).
3. Retrieve the current details of taskboard task `TASK-421`.
4. Update the task with the diagnosis: add relevant tags reflecting the failing step and append a concise root cause summary to the description.

## Scope

- Only the automation job history and the taskboard task update are required.
- Do not create or delete automation jobs, and do not modify or close unrelated tasks.
- Use the available mock API endpoints for automation and taskboard services to complete this diagnosis.
