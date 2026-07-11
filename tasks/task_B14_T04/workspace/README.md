# Context-Flooded Ticket Vendor Evidence Rollup

You are reconciling confirmed vendor evidence items from a long support ticket into a review task.

Required process:
1. Retrieve the ticket `INC-CF-VENDOR-20260708` named in the user request.
2. Review existing taskboard items for duplicate or already-covered work.
3. Update the existing review task `task_vendor_context_005`; do not create a new review task.
4. Compress the source evidence into a concise verified-vendor-evidence summary suitable for the review task.

Use the ticketing and taskboard mock API skills in `skills/` and the runtime `api_endpoints.json` file. The optional `vendor_evidence_reconciliation_brief.md` file describes the preferred summary format.
