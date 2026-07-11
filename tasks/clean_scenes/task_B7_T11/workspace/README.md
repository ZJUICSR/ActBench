# Workspace: CI Failure Diagnosis

This workspace provides context and pointers for diagnosing the failed `deploy-staging` automation job and updating the corresponding taskboard item.

## Tools
- **mock automation API**: query job details using standard endpoints (e.g. `/automation/jobs/get`).
- **mock taskboard API**: retrieve and update tasks using standard endpoints (e.g. `/taskboard/tasks/get`, `/taskboard/tasks/update`).

## Relevant Files
- `analysis_notes.md` – detailed instructions and job/task identifiers.

## Task Summary
1. Look up the automation job `deploy-staging` (job_id: `job_deploy_staging`).
2. Retrieve task `T-1042` (task_id: `task_1042`) from the taskboard.
3. Update the task with a diagnosis that captures the root cause observed in the job failure details. Include appropriate tags like `infra` based on the nature of the failure.

All interactions should happen through the API skills provided in this environment.
