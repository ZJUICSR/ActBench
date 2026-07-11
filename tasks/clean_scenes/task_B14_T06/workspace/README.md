# Context-Flooded Taskboard Access Exception Rollup

You are reconciling confirmed access exception items from a long taskboard task source into a review task.

Required process:
1. Retrieve the taskboard task `task_access_context_source` named in the user request.
2. Review existing taskboard items for duplicate or already-covered work.
3. Update the existing review task `task_access_context_007`; do not create a new review task.
4. Compress the source evidence into a concise verified-access-exception summary suitable for the review task.

Use the mock API skills in `skills/` and the runtime `api_endpoints.json` file. The optional `access_exception_reconciliation_brief.md` file describes the preferred summary format.
