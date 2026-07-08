# Bug Report: Login Page Redirect Failure

**Bug ID:** BUG-4201  
**Date:** 2026-03-18  
**Reported by:** CI Pipeline (failed test)  
**Severity:** High  
**Affected Component:** `LoginPage`

## Summary

The integration test `Login page → should redirect to dashboard after submit` fails consistently in CI. The test submits valid credentials but the page never navigates to `/dashboard`; the test eventually times out waiting for the redirect.

## Test Details

- **Test suite:** `LoginPage.integration.test.tsx`
- **Failed assertion:** Expected URL to be `/dashboard` within the timeout, but remained on `/login`.
- **Test log excerpt:** See `test-output.log` for full output. The error message is `Timeout - Async callback was not invoked within the 5000 ms timeout`.

## Observed Behavior

1. The login form renders correctly.
2. Credentials are entered and the submit button is clicked.
3. The mock authentication service returns a successful token.
4. **No navigation occurs** – the page stays on `/login` instead of redirecting to `/dashboard`.

## Expected Behavior

After successful login, the application should immediately redirect the user to the `/dashboard` route.

## Preliminary Root Cause

Based on the same failure pattern noted during an earlier debugging session (see notebook note NOTE-001), the likely cause is a **missing import of the `AuthRedirect` component** in `LoginPage`. The `AuthRedirect` component is responsible for programmatic navigation after login. Without it, the component receives the token but never triggers the redirect.

## Environment

- Node.js 20.x
- React 18.x
- React Router 6.x
- Testing framework: Jest + React Testing Library

## Next Steps

1. Confirm the missing import by inspecting `LoginPage` source.
2. Add `import AuthRedirect from '@/components/AuthRedirect';` at the top of the file.
3. Use `<AuthRedirect />` inside the component to trigger the redirect when a valid token is present.
4. Re-run the integration test to verify the fix.

**Attachments:** `test-output.log` (included in workspace)