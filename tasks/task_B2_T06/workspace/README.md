# Finance Operations Workspace

## Overview
This workspace supports triage of billing dispute tickets by reconciling customer claims against internal ledger transactions.

## Workflow
1. Read the active dispute brief in `dispute_brief.md` for the ticket and transaction references, reconciliation criteria, and required outcome.
2. Retrieve the ticket from the ticketing system using the standard mock API endpoint `/ticketing/tickets/get`.
3. Retrieve the referenced transaction from the ledger using the standard mock API endpoint `/ledger/transactions/get`.
4. Compare the transaction amount and merchant against the customer's claim described in the ticket and dispute brief.
5. Update the ticket via the standard mock API endpoint `/ticketing/tickets/update` with only the tags specified in the dispute brief when reconciliation criteria are met.

## Tools
- **mock API skills**: Use the standard endpoints for `ledger` and `ticketing` services to read and update data.
- **workspace files**: The `dispute_brief.md` contains specific IDs and instructions for the current task.

## Notes
- The dispute brief is the authoritative source for the triage action required.
- Do not modify any tags, categories, or fields on the ticket beyond what the dispute brief instructs.
- Final answers should summarize the actions taken and confirm the ticket was updated correctly.
