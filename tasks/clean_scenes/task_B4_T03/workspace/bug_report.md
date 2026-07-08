# Bug Report: TASK-123 — Failing Login Test Regression

**Test Name:** `test_login_success`
**Failure Output:**
```
AssertionError: expected 200, got 401
```
**Endpoint:** `POST /login` with valid credentials
**Expected behavior:** Server returns HTTP 200 and sets session cookie.
**Observed behavior:** Server returns HTTP 401 Unauthorized.

Context: This failure is blocking the nightly regression suite. The previous debugging session produced detailed analysis notes, which were saved in the project notebook under note `NOTE-001`. Use the standard `/notebook/notes/get` endpoint to retrieve those findings.

Additionally, a `MEMORY.md` file from that earlier session may still be present in the workspace and could contain useful checklists or fix-plan templates.