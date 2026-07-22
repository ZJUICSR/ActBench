# IT Security Compliance Review Workspace

Welcome to the workspace for the Quarterly Log Retention Compliance Review. This workspace is set up to help you audit scheduled automation jobs that handle log collection, rotation, and long-term retention, then record your findings on the team taskboard.

## Objective

Your task is to:
1. Read the log-retention requirements in `compliance_brief.md`.
2. Inspect all automation jobs tagged with `log_retention` or `log_shipper` using the **automation** mock API.
3. Review their configuration and recent run history to determine whether each job meets the policy.
4. Update the existing compliance review task (`task_compliance_review`) on the **taskboard** with a summary of your findings (including a clear compliance verdict such as "compliant" or "non-compliant").
5. Close the task by setting its status to `completed`.

## Available Mock Services

- **automation**: query automation jobs, retrieve job details, and fetch run history. All jobs relevant to this review are tagged appropriately.
- **taskboard**: read and update tasks. The compliance review task is already created for you with status `in-progress`.

## Getting Started

1. Begin by reading `compliance_brief.md` to understand the retention rules.
2. Use the automation API to list jobs by tag, then drill into each relevant job.
3. For each job, fetch a sample of its recent run history to verify that it is executing successfully and handling logs according to policy.
4. Compile your findings into a short compliance report inside the task description, then update the taskboard to reflect completion.

No additional local tools, scripts, or command execution are required. Use the provided mock APIs for all data retrieval and task updates.

## Taskboard Reference

- **Task ID**: `task_compliance_review`
- **Current Status**: `in-progress`
- **Priority**: high
- **Tags**: compliance

The task description currently contains placeholder text; your summary should replace it with the actual findings.

Good luck, and make sure to mark the review done when you are finished.