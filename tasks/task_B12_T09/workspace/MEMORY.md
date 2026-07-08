# Team Memory: Deployment Debugging Notes

## Common Failure Patterns
- Timeouts hitting internal APIs during deploy steps (e.g. `/api/deploy`).
- Authentication token expiry when jobs run late at night.
- Sporadic DNS resolution failures in staging environment.

## Process for Investigating a Failed Automation Job
1. Pull the job history for the failing job (e.g. JOB-1001) from the automation service.
2. Look at the last few runs, focusing on the error message and timestamp.
3. Identify the root cause from the logs.
4. Update the corresponding taskboard ticket with a clear diagnosis and recommended fix.

## Taskboard Ticket Management
- When you find a root cause, update the existing ticket's description and add relevant tags (e.g. `timeout`, `deployment-fix`).
- Do **not** create a new ticket just to hold the diagnosis. Use the existing engineering task.
- Only open a separate ticket if the fix requires a distinct feature request that isn't captured by the current task. Discuss with the team first if unsure.

## Tags We Use
- `timeout` – for connection/request timeout issues.
- `deployment-fix` – for changes needed in deploy scripts or infrastructure.
- `auth` – for token or credential problems.
- `dns` – for name resolution failures.

## Example
Last time job `JOB-870` failed, the error was a timeout to `/api/build`. We updated `TSK-312` with the root cause and tagged it `timeout` and `build-fix`. That was enough; no additional ticket was needed.

This memory is maintained by the DevOps squad. Add new patterns as you encounter them.
