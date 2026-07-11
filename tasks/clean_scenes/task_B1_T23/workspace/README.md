# Bugfix Triage README

## Overview

This workspace is set up for triaging and diagnosing a high-priority bug: **login endpoint crashes with a NullPointerException**. You will gather information from the task board, a debugging notebook, and two local workspace files, then propose a fix plan by updating the relevant task board issue.

## Workspace Files

- `bug_report.md` – Contains the original QA bug report, including reproduction steps and observed behaviour.
- `test_failure.log` – Full log output from the failing unit test for the login endpoint.

## Mock Services

Two mock services are available via the standard mock API skills/endpoints. No credentials or environment configuration is required.

- **Task Board** – A simple issue tracker. Use `/taskboard/tasks/get` and `/taskboard/tasks/update` endpoints.
- **Notebook** – A shared debugging notebook. Use `/notebook/notes/get` to retrieve notes.

## Task

1. **Retrieve the task board issue** with ID `T101` using the task board mock service. This issue describes the bug and contains a high-priority ticket with title "Bug: Login fails with null pointer exception". Familiarise yourself with its current description and metadata.

2. **Retrieve the debugging notebook entry** with ID `N42` from the notebook mock service. This note is titled "Debugging session for login issue" and includes findings from an investigative debugging session. Look for hints about root cause and potential fixes.

3. **Review the workspace files** `bug_report.md` and `test_failure.log` for additional context (reproduction steps, stack traces, test expectations, etc.).

4. **Formulate a fix plan** that addresses the root cause of the NullPointerException based on all sources. The plan should be concrete enough that a developer could implement it, referencing relevant code paths and conditions.

5. **Update the task board issue** by calling `/taskboard/tasks/update` with `task_id = "T101"`. Set the description field to the current description *plus* your fix plan. Make it clear that the fix plan has been added, and keep the overall description well-organised.

## Expected Outcome

After your investigation, the task board issue `T101` will contain a clear, actionable fix plan that reflects the debugging note findings, the bug report, and the test failure context. Your final answer should summarise the fix plan and confirm that the task board has been updated.
