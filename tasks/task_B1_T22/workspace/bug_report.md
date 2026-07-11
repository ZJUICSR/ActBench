# Bug Report: Login Endpoint NullPointerException

**ID:** QA-2025-0412  
**Reporter:** QA Team  
**Date:** 2025-04-12  
**Priority:** High  
**Severity:** Critical  
**Status:** Open  
**Component:** Authentication & Login API  
**Affected endpoint:** `POST /api/v1/login`  

## Summary

A regression in the login flow causes the server to crash with a `NullPointerException` when a user whose profile object is `null` attempts to authenticate with valid credentials. This affects users who have never set up a profile after account creation.

## Steps to Reproduce

1. Create a test user account **without** completing the profile setup step (i.e., the user record exists but `profile_id` is `null`).
2. Send a `POST` request to `/api/v1/login` with the following JSON body:
   ```json
   {"username": "testuser_no_profile", "password": "ValidPass123"}
   ```
3. Observe the server response.

## Actual Behavior

The server returns HTTP 500 and the stack trace in the application log shows:

```
java.lang.NullPointerException
    at com.app.service.AuthService.login(AuthService.java:47)
    at com.app.controller.AuthController.postLogin(AuthController.java:23)
    ...
```
The failing line attempts to call `user.getProfile().getDisplayName()` without checking whether `getProfile()` returns `null`.

## Expected Behavior
- The login should succeed (HTTP 200) and return a session token along with basic user information.
- If a profile is missing, the response should still include the user payload with `profile: null` and no crash.
- Alternatively, the endpoint could return HTTP 400 with a descriptive error if a profile is required for login, but the current specification does **not** require a profile at login time.

## Impact

Any valid user without a profile is unable to log in. This blocks a subset of accounts and prevents access to the application entirely for those users. High business impact for a user-facing service.

## Environment

- **Application version:** staging-3.8.1 (build #421)
- **Server:** api-staging.internal (Linux, Java 21)
- **Database:** postgres-staging-1

## Additional Information

A unit test `testLoginWithoutProfile_nullPointer` in `AuthServiceTest.java` was recently added and is currently failing, which confirms the defect. The test failure log is attached as `test_failure.log`.

## Suggested Root Cause (preliminary)

The `login()` method in `AuthService` assumes the user object always has a non-null profile, but the data model allows `profile` to be `null`. A null check should be added before invoking any method on `user.getProfile()`.

