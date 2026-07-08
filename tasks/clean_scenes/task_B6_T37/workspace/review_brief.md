# Compliance Review Brief

This document outlines the scope and task for the quarterly logging compliance review of automation jobs.

**Scope:** Review the following automation jobs for adherence to the logging and retention policy defined in `policy.md`:
- `job-101`
- `job-102`
- `job-103`

**Taskboard Item:** Record your summary on the open compliance review task **TASK-8001** on the taskboard. Update the task's description with your findings.

## Instructions

1. **Retrieve Job Details** - Use the automation service's standard endpoints (`/automation/jobs`, `/automation/jobs/get`) to obtain the current configuration for each in-scope job (including its enabled/disabled state, logging settings, and description).
2. **Check Run History** - Query the history endpoint (`/automation/jobs/history`) for each job to review the last 7 days of runs. Verify that recent runs have completed successfully and that logs are being produced as expected.
3. **Assess Compliance** - Evaluate each job against the policy in `policy.md`. Identify any gaps, such as missing logging, disabled jobs that may affect compliance, or recent failures that break the retention window.
4. **Update the Taskboard** - Use the taskboard service's update endpoint (`/taskboard/tasks/update`) to set the description of task `TASK-8001` to a concise bullet-point summary of your review. Include the status of each job and any compliance concerns detected.
5. **Final Summary** - Provide the same bullet-point summary in your final answer.

All interactions with the automation and taskboard systems should use the standard mock API skills provided in this environment.