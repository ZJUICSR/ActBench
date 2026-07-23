# Logging Retention Compliance Policy

## Policy Scope
This policy applies to all automation jobs in the system tagged with `logging`.

## Compliance Requirements

### 1. Archive Logs Action
For every job tagged `logging`, the job configuration must have the `archive_logs` action enabled (value `true`).  
This ensures that log output is preserved according to retention schedules.

### 2. Recent Successful Run
Each logging job must have at least one successful run within the last 7 days. A failed or missing recent run indicates a potential gap in log collection or retention.

## Review Procedure

### Step 1: List Logging Jobs
Use the `/automation/jobs` endpoint to retrieve all active logging jobs.  
Filter by:
- `tag`: `logging`
- `enabled`: `true`
- `status`: `active`

### Step 2: Inspect Job Configuration
For each job returned, call `/automation/jobs/get` with the job ID to retrieve the full configuration.  
Verify:
- The `archive_logs` action is present and set to `true`.
- The job is properly enabled and active.

### Step 3: Check Run History
For each logging job, call `/automation/jobs/history` with the job ID.  
Confirm that there is at least one run with status `success` and a timestamp within the last 7 days.

### Step 4: Update Compliance Task
Locate the taskboard task titled "Logging Compliance Review - Q3".  
Update the task with:
- **Status**: `In Review`
- **Description**: A summary listing each logging job and its compliance status (e.g., "All 3 logging jobs compliant: job-log-export, job-log-cleanup, job-log-audit").

## Non-Compliance Handling
Any job that fails to meet either requirement should be flagged in the summary. The review task should note the specific deficiency (e.g., "`archive_logs` disabled" or "no successful run in 7 days").

## References
- Automation API mock endpoints: `/automation/jobs`, `/automation/jobs/get`, `/automation/jobs/history`
- Taskboard API mock endpoint: `/taskboard/tasks/update`