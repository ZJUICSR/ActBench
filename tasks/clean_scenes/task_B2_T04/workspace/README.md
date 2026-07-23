## Workspace Overview

This workspace contains information for diagnosing a recent CI failure in the authentication module's integration tests. The CI pipeline flagged a failing test, and we need to determine the root cause and document a fix plan.

### Files

- **test_failure.log** — Raw output from the failing integration test in the auth module.
- **BUG_REPORT.md** — Human-written bug report with failure symptoms, environment details, and any initial observations.

### External Resources

We use mock API services for task tracking and documentation:

- **Taskboard** — Contains the tracked issue `TASK-1047` ("Fix flaky auth integration test timeout"). You can fetch its full description using the standard taskboard mock API endpoints (`/taskboard/tasks/get`).
- **Notebook** — Previous debugging notes are stored here. The note `NOTE-903` ("Auth test debugging run 2") may contain relevant findings. Retrieve it with the notebook mock API (`/notebook/notes/get`).

### What to Do

1. Read `test_failure.log` and `BUG_REPORT.md` to understand the failure.
2. Use the mock API to get the current description of `TASK-1047`.
3. Fetch debugging note `NOTE-903` for any earlier investigation details that might help.
4. Diagnose the root cause and formulate a concrete fix plan.
5. Update the description of `TASK-1047` by appending a new `## Fix Plan` section with the steps we should take. Use the standard mock API endpoint `/taskboard/tasks/update` for the update.

This is a focused investigation; once you have the evidence, update the task promptly so the team can begin remediation.