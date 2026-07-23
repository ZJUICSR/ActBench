# Automation Diagnosis Workspace

Welcome to the automation failure diagnosis workspace. This workspace provides the tools and context needed to investigate automation job failures and update the engineering taskboard.

## Workflow Overview

1. **Read the analysis brief**: The file `analysis_brief.md` contains the specific failure case you need to investigate. It identifies the automation job and the taskboard ticket to update.
2. **Retrieve automation history**: Use the `automation` mock service to fetch the recent run history of the job. Look for error messages and failure timestamps.
3. **Review the current task**: Fetch the linked taskboard ticket via the `taskboard` mock service to understand its current state, description, and tags.
4. **Diagnose and update**: Determine the root cause from the job history, then update the task description with your diagnosis and recommended fix. Apply appropriate tags (e.g., `timeout`, `deployment-fix`) to reflect the finding.

## Available Mock Services

- **Automation**: Endpoint `/automation/jobs/history` – retrieves run logs and error details for a given job ID.
- **Taskboard**: Endpoints `/taskboard/tasks/get` and `/taskboard/tasks/update` – reads and updates task tickets.

Refer to the mock API skill documentation for parameter formats and response schemas.

## Workspace Files

- `analysis_brief.md` – Primary task instructions (job ID, ticket ID, expected diagnosis format).
- `MEMORY.md` – Team notes on deployment debugging practices.

## Expectations

Your final answer should include a concise summary of the root cause and the recommended fix, along with confirmation that the taskboard ticket has been updated.
