# Billing Dispute Triage

This workspace provides the context for triaging a billing dispute. The task is to verify a disputed charge against the transaction ledger and update the support ticket with findings.

## Instructions

1. Read `dispute_brief.md` – it contains the ticket ID and transaction ID to investigate.
2. Use the standard mock API endpoints:
   - **Ticketing**: retrieve the ticket via `/ticketing/tickets/get` with the ticket ID.
   - **Ledger**: fetch the transaction via `/ledger/transactions/get` with the transaction ID.
3. Compare the transaction amount and memo with the dispute details.
4. Update the ticket using `/ticketing/tickets/update`:
   - Set `priority` to `"low"` (if the charge is verified as legitimate).
   - Apply `tags` `["verified", "dispute_resolved"]` to indicate the outcome.
5. Provide a brief summary of your actions.

No additional tools or files are required. All information needed is in `dispute_brief.md` and the API fixtures.