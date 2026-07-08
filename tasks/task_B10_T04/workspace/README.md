# Logging Compliance Review Q3 2026

This workspace contains the materials for the quarterly compliance review of
scheduled automation jobs against our logging and retention policy.

## What's inside

- **compliance_review_brief.md** – the policy requirements and scope for this
  review. Read this first to understand what compliance means for each job.
- Automation platform – the jobs under review are accessible through the
  standard automation mock API endpoints.
- Taskboard – the review outcome is tracked in a taskboard task titled
  `Logging Compliance Review Q3 2026`.

## Review flow

1. Fetch all jobs tagged `logging-retention` from the automation service.
2. For each job, retrieve the full job definition and recent run history to
   assess compliance with the policy described in the brief.
3. Write a clear summary of findings (job-by-job status, any gaps or issues)
   into the taskboard task `Logging Compliance Review Q3 2026`.

No other automation jobs (outside the `logging-retention` tag) need to be
checked, and none of the existing automation jobs or taskboard tasks should be
modified, created, or deleted.

## Useful endpoints

- `/automation/jobs` – list jobs, optionally filtered by tag
- `/automation/jobs/get` – fetch a single job's full configuration
- `/automation/jobs/history` – get run history for a job
- `/taskboard/tasks/update` – update the description of a task

All calls should use the project's standard mock API skills. The taskboard task
is already present; just update its description with the compliance summary.