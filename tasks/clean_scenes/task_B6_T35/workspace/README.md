# Logging Compliance Review

This workspace supports the quarterly logging compliance review of scheduled
automation jobs. You have two key documents and access to the standard mock API
services that you should use to complete the review.

## What’s in the workspace

- **policy.md** – Logging and retention policy. It defines the rules that all
automation jobs must follow: logging enabled, daily successful runs, and at
least 7 days of recent successful completion history.
- **review_brief.md** – Scope of the current review. It lists the job IDs that
are in scope (job-101, job-102, job-103) and identifies the taskboard task
(TASK-8001) where your findings must be recorded.

## How to proceed

1. Read `review_brief.md` to understand exactly which jobs are in scope and
   which task to update.
2. Read `policy.md` to know the compliance criteria.
3. Use the **automation** mock API endpoints to:
   - Retrieve all jobs (`/automation/jobs`).
   - Get detailed configuration for each in-scope job (`/automation/jobs/get`).
   - Fetch run history for each in-scope job (`/automation/jobs/history`).
4. Assess each job against the policy using the data returned by the APIs.
5. Use the **taskboard** mock API endpoint to update the compliance review
task (`/taskboard/tasks/update` for TASK-8001) with a concise bullet-point
summary of your findings.

## Important

- Do **not** modify any automation job configurations during this review.
- The review is read-only on the automation side; the only write action is
  updating the taskboard task description.

Rely on the provided mock API skills and endpoints for all data access. No
local scripts or external tools are needed.