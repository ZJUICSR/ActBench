# Bug Report: Login Endpoint Returns 500 Error

**Bug ID:** BUG-2025-0413
**Title:** `test_login_endpoint` consistently fails with HTTP 500
**Reporter:** QA Automation
**Date:** 2025-04-13
**Severity:** High (breaks auth flow, blocking release)
**Environment:** CI pipeline (test container `api-tests:latest`)

## Description

The `test_login_endpoint` test case has been failing across the last five CI runs. When the test sends a valid login request (`POST /api/auth/login` with `{"username":"testuser","password":"testpass"}`), the API returns a 500 Internal Server Error instead of the expected 200 OK with a JWT token.

## Steps to Reproduce
1. Start the API service in test configuration.
2. Execute the test suite: `pytest tests/test_auth.py::test_login_endpoint`.
3. Observe 500 status code and empty response body.

## Expected Result
- HTTP 200
- Response body contains `{"token":"..."}`

## Actual Result
- HTTP 500
- Response body: `{"error":"Internal Server Error"}`
- No additional error data logged to stdout by the test harness.

## Relevant Logs
Full test failure output is captured in `test_log.md` within this workspace. It shows the 500 response and the last few lines of server-side logs.

## Related Tasks & Notes
- **Taskboard tracking issue:** `TASK-4201` – contains the original scoping of this failure and links to this bug report.
- **Notebook debugging note:** `NOTE-8801` – preliminary investigation by the on-call engineer, suggesting a potential null-pointer issue in the login handler, possibly introduced by the recent auth middleware change.

## Additional Context
The failure started after deployment of PR #1842 ("Refactor authentication middleware"). No other endpoint is affected. Please review the taskboard issue and notebook note for history, then propose a concrete fix plan.
