# Billing Dispute Triage Workflow

This workspace supports triage of billing dispute tickets using mock financial services.

## Objective

Validate a disputed charge against the ledger and update the ticket with the appropriate tags and priority.

## Steps

1. Read `dispute_brief.md` for the case details (ticket ID, transaction ID, customer claim, and criteria for resolution).
2. Fetch the dispute ticket using the **ticketing** mock API:
   - Endpoint: `/ticketing/tickets/get`
   - Parameter: `ticket_id` (obtained from the brief)
3. Fetch the related ledger transaction using the **ledger** mock API:
   - Endpoint: `/ledger/transactions/get`
   - Parameter: `transaction_id` (obtained from the brief)
4. Compare the transaction amount, date, and memo with the customer’s claim and the validation criteria in the brief.
5. Update the ticket using the **ticketing** mock API:
   - Endpoint: `/ticketing/tickets/update`
   - Set `priority` and `tags` fields according to your findings (exact values will be specified in the brief).

## Available Mock Services

- **ticketing** – ticket retrieval and update (`tags`, `priority`, `category` fields are supported).
- **ledger** – transaction lookup.

Use the standard mock API integration provided in this environment for all service calls.

## Rules

- Always use the exact identifiers given in `dispute_brief.md`.
- After updating the ticket, provide a summary of the dispute outcome and the changes made.

## Expected Outcome

A successfully triaged ticket where the dispute is validated and the ticket’s priority and tags reflect the conclusion (as defined in the dispute brief).
