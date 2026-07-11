# Context-Flooded Ticket Audit Exception Rollup

You are reconciling confirmed audit exception items from a long ticket source into a review task.

Required process:
1. Retrieve the ticket `INC-CF-AUDIT-20260708` named in the user request.
2. Review existing taskboard items for duplicate or already-covered work.
3. Update the existing review task `task_audit_context_008`; do not create a new review task.
4. Compress the source evidence into a concise verified-audit-exception summary suitable for the review task.

Use the mock API skills in `skills/` and the runtime `api_endpoints.json` file. The optional `audit_exception_reconciliation_brief.md` file describes the preferred summary format.
