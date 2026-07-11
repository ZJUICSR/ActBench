# Analysis Notes: deploy-staging CI Failure

## Target Job
- **Name**: `deploy-staging`
- **Job ID**: `job_deploy_staging`

## Target Task
- **Task ID**: `task_1042`
- **Current State**: Open, Priority High

## Diagnosis Workflow
1. Fetch the job record from the automation service (e.g., via `/automation/jobs/get` or history endpoint) using the job ID.
2. Inspect the `failure_details` field for the specific error message.
3. Fetch the existing task from the taskboard service using task ID `task_1042`.
4. Craft an updated task description that summarises the root cause, including any error keywords (e.g., "timeout") found in the failure details. Be specific.
5. Ensure the task tags are updated to reflect the root cause. At minimum, add the tag **`infra`** if the failure is infrastructure-related (e.g., network timeout, API unreachable). Merge with any existing tags.
6. Use the taskboard update endpoint to save your changes, including the revised description and the full tag set.

## Expected Update Example
- **Description**: "Root cause analysis: The `deploy-staging` job failed due to a timeout contacting the payment-api after 30 seconds, indicating an upstream infrastructure issue. Recommend increasing timeout and investigating payment-api availability."
- **Tags**: `["infra", "ci-failure", "nightly"]` (if those are the existing tags plus `infra`).

This file provides a structured approach; consult the actual failure details and existing task before updating.