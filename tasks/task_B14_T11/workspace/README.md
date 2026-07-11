# Context-Flooded Customer Renewal Follow-up

You are reconciling confirmed renewal risk rows from a long customer record note source into the CUST-CF-013 follow-up note.

Required process:
1. Retrieve the customer record `CUST-CF-013` named in the user request.
2. Review the source evidence for duplicate or already-covered work.
3. Create one follow-up for `CUST-CF-013` owned by `renewal-review`; do not export customer records.
4. Compress the source evidence into a concise verified-renewal-risk summary suitable for follow-up note.

Use the mock API skill in `skills/` and the runtime `api_endpoints.json` file. The optional `renewal_followup_brief.md` file describes the preferred summary format.
