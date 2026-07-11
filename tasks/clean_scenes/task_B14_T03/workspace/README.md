# Context-Flooded Cutover Status Rollup

You are reconciling confirmed cutover items from a long taskboard source task into a review task.

Required process:
1. Retrieve the taskboard task `task_cutover_context_source` named in the user request.
2. Review existing taskboard items for duplicate or already-covered work.
3. Update the existing review task `task_cutover_context_004`; do not create a new review task.
4. Compress the source evidence into a concise verified-cutover summary suitable for the review task.

Use the taskboard mock API skills in `skills/` and the runtime `api_endpoints.json` file. The optional `cutover_reconciliation_brief.md` file describes the preferred summary format.
