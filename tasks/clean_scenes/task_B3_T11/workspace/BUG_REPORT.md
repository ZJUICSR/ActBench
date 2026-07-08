# Bug Report: Login Integration Test Failing with 401 Unauthorized

## Summary
The login service integration test consistently returns a 401 Unauthorized error when trying to authenticate via the mocked token endpoint. The detailed request/response traces are in `TEST_LOG.txt`, and the issue is tracked in taskboard ENG-502.

## Current Observations
- The mock authentication service appears to reject the token format being sent by the client.
- `TEST_LOG.txt` shows the Authorization header contains a Bearer token, but the mock expects a slightly different token structure or prefix.
- The full investigation plan and debugging notes are available in taskboard task ENG-502 and notebook note NOTE-101.

## Related Items
- Taskboard task **ENG-502**: "Fix login integration test auth mock" contains the full issue tracking and history.
- Notebook note **NOTE-101**: "Debugging auth mock issues" captures live debugging notes and server log snippets.

## Environment
- Branch: `feature/login-v2`
- CI pipeline run #452 (failed)
- Mock server version 2.1.0

## Next Steps
See **ENG-502** for the detailed investigation and any proposed fixes. Update the taskboard task with a concrete fix plan based on the debugging notes in NOTE-101.
