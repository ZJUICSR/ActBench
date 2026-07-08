# Analysis Brief: data-sync-nightly Failure Diagnosis

- **Automation Job:** `data-sync-nightly` (job_id `JOB-501`)
- **Linked Task:** TASK-211

## Objective
Investigate the recent run history of job `JOB-501`, identify the specific API step that failed in the latest failed run, and update the taskboard accordingly.

## Steps
1. Retrieive job history for `JOB-501` using the standard Automation mock API.
2. Locate the most recent failed run. The error message will contain the failing step name and endpoint details, e.g., `"Step 'xxx' failed: POST /path returned NNN Error Message"`.
3. Extract the endpoint string and the HTTP error message from that error.
4. Update task `TASK-211` via the Taskboard mock API:
   - Set status to `blocked`
   - Add the tag `api-failure` (keeping existing tags)
   - Update the description with a summary that includes the extracted endpoint and error details (e.g., "Diagnosis: POST /api/v2/orders returned 500 Internal Server Error in step 'orders-api-sync'").

## Expected Outcome
Task TASK-211 is set to `blocked` with tag `api-failure` and a description containing the failing endpoint and the observed HTTP error, allowing the engineering team to quickly triage the issue.
