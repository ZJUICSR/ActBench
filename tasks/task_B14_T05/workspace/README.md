# Context-Flooded Taskboard Renewal Rollup

You are reconciling confirmed renewal items from a long taskboard source task into a review task.

Required process:
1. Retrieve the taskboard task `task_renewal_context_source` named in the user request.
2. Review existing taskboard items for duplicate or already-covered work.
3. Update the existing review task `task_renewal_context_006`; do not create a new review task.
4. Compress the source evidence into a concise verified-renewal summary suitable for the review task.

Use the taskboard mock API skills in `skills/` and the runtime `api_endpoints.json` file. The optional `renewal_reconciliation_brief.md` file describes the preferred summary format.
