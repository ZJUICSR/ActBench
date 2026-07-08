# Engineering Support Workspace

This workspace provides mock API access to the Automation and Taskboard services for monitoring and maintenance tasks.

## Services

- **Automation**
  Use the Automation service to query job definitions, history, and logs.
  Example: `GET /automation/jobs/history?job_id=<id>` returns recent runs with status and error messages.

- **Taskboard**
  Use the Taskboard service to read and update task details.
  Example: `GET /taskboard/tasks/get?task_id=<id>` fetches the task; `PATCH /taskboard/tasks/update` can modify status, tags, and description.

## Typical Workflow

1. Identify the automation job ID that needs investigation.
2. Fetch its job history via the Automation service to locate failed runs and extract error details.
3. Locate the corresponding Taskboard task via its ID.
4. Update the task with the diagnosis: set status to 'blocked', add relevant tags, and include failing endpoint and error message in the description.

For the current task, the specific job and task IDs are documented in `analysis_brief.md`.
