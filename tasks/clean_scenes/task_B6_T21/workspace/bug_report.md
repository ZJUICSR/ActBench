# Bug Report: test_login_rate_limiting Regression

**ID:** bug-20250418-01
**Severity:** High
**Status:** Open
**Author:** CI System
**Date:** 2025-04-18 09:22 UTC

## Summary

The integration test `test_login_rate_limiting` has been failing intermittently since the latest auth-service changes. The test is supposed to verify that login attempts are properly rate-limited (5 failures in 60 seconds trigger a 300-second lockout), but around 30% of recent CI runs report an unexpected `LockoutNotTriggeredException`.

## Steps to Reproduce

1. Execute `test_login_rate_limiting` in the CI test suite (or locally with `pytest tests/integration/test_auth.py::test_login_rate_limiting --log-cli-level=DEBUG`).
2. Observe the outcome across multiple runs.

## Test Failure Log (abbreviated)

```
FAILED tests/integration/test_auth.py::test_login_rate_limiting - assert lockout_active == True
================================================================= short test summary =================================================================
FAILED tests/integration/test_auth.py::test_login_rate_limiting - assert lockout_active == True
```

Full stack trace and debug output are available in `test_failure.log` in this workspace.

## Expected Behavior

After 5 consecutive failed login attempts within 60 seconds, the account should be locked out for 300 seconds. The lockout flag should be `True` and subsequent attempts (even with correct credentials) should be rejected with `429 Too Many Requests`.

## Actual Behavior

In the failing runs, the lockout flag remains `False` and the 6th attempt (with valid credentials) succeeds, indicating the rate limiter never transitioned to the locked state.

## Additional Notes

- The problem appears to be a race condition related to the token-bucket concurrency model.
- Earlier debugging notes (see notebook note-001) pointed to a possible synchronization issue in `RateLimiter.consume_token()`.
- The CI configuration has not changed; only the auth service's internal rate-limiting module was refactored.
- Recommend reviewing the mutex locking around the bucket state update and considering a compare-and-swap approach.
