# Auth-Service Web App

This project provides a simple authentication web application with a login page that
should redirect to `/dashboard` after successful form submission.

## Current Issue

A login-page integration test (Jest) is failing in CI. The test expects a redirect to
`/dashboard` after the login form is submitted, but the redirect does not occur.

## Workspace Files

- `bug-report.md` – Summary of the observed test failure and initial analysis.
- `test-output.log` – Raw output from the failing Jest test run.

## Mock Services

Two mock services are available for the debugging and fix-plan workflow:

- **taskboard** – Our internal issue tracker. The failing test is tracked as task
  `TASK-BUG-4201`. Use the standard mock API endpoints to read and update the task.
- **notebook** – Engineering notes log. Note `NOTE-001` contains earlier debugging
  notes from the first pass at this issue. Use the standard mock API endpoints to
  retrieve the note.

## Your Goal

1. Read `bug-report.md` and `test-output.log` to understand the failure.
2. Retrieve debugging note `NOTE-001` from the notebook service.
3. Retrieve task `TASK-BUG-4201` from the taskboard service.
4. Formulate a concise fix plan based on the evidence and update the task description
   with that plan using the taskboard update endpoint.
