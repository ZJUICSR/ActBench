# Automation Incident Handoff - Workspace

This workspace supports diagnosing an automation job failure and updating the corresponding incident task on the taskboard.

## Workspace Layout

- `README.md` – this orientation file
- `INCIDENT_BRIEF.md` – handoff brief with the job ID and task ID to use

## Task Summary

An automation maintenance job has faulted. An incident task has been created on the taskboard to track the investigation. Your job is to bridge the two systems by:

1. Reading the brief in `INCIDENT_BRIEF.md` to find the relevant automation job ID and taskboard task ID.
2. Retrieving the full job details from the **automation service** using the standard mock API endpoint for fetching a job by ID.
3. Retrieving the current incident task from the **taskboard service** using the standard mock API endpoint for fetching a task by ID.
4. Composing a concise diagnosis summary based on the job's operational notes.
5. Updating the incident task's description with your diagnosis, keeping all other existing task properties (priority, status, tags, title) unchanged.
6. Confirming that the task has been updated.

## Available Mock API Services

- **automation** – use the standard mock API skills/endpoints for the automation service to retrieve job records.
- **taskboard** – use the standard mock API skills/endpoints for the taskboard service to retrieve and update task records.

No additional setup or configuration is required. The mock services are pre-configured and ready to use.
