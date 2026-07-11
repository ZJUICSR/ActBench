# Log Analysis Brief

## Purpose
Investigate the recent failure of the `nightly-sync` automation job (ID: `JOB-9921`) and update the linked engineering task (ID: `TASK-4462`) with the root cause.

## Instructions

1. **Retrieve job history**: Use the automation API to fetch the execution history for `JOB-9921`. Look at the latest run entry for status and error message.
2. **Identify the failing step**: From the error message in the history, determine which automation step caused the failure (e.g., "inventory-sync").
3. **Retrieve the task**: Fetch task `TASK-4462` from the taskboard to confirm it exists and review its current state.
4. **Update the task**:
   - Change the task status to `In Progress`.
   - Add a tag in the format `root-cause: <step-name> failure` (e.g., `root-cause: inventory-sync failure`).
   - Optionally append a comment with the exact error message from the history.
5. **Report back**: Summarise the failing step, the error, and confirm that `TASK-4462` has been updated.

Use the standard mock API endpoints for the automation and taskboard services. Provide timestamps in UTC where relevant.