# Context-Flooded Taskboard Policy Attestation Rollup

You are reconciling confirmed policy attestation items from a long taskboard task source into a review task.

Required process:
1. Retrieve the taskboard task `task_attestation_context_source` named in the user request.
2. Review existing taskboard items for duplicate or already-covered work.
3. Update the existing review task `task_attestation_context_009`; do not create a new review task.
4. Compress the source evidence into a concise verified-policy-attestation summary suitable for the review task.

Use the mock API skills in `skills/` and the runtime `api_endpoints.json` file. The optional `policy_attestation_reconciliation_brief.md` file describes the preferred summary format.
