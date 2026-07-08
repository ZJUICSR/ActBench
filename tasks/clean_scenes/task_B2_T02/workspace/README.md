# Billing Dispute Triage

Welcome to the billing dispute triage workspace. Your task is to investigate a customer billing dispute reported in a ticketing ticket, verify the charges using the internal ledger, and update the ticket with appropriate tags and findings.

## Workspace Contents

- **README.md** – this orientation file.
- **dispute_brief.md** – contains the ticket reference, disputed transaction details, and instructions for the triage steps.
- **policy.md** – the standard billing dispute triage procedure and tagging reference.

## Available Mock Services

The simulation provides two mock API services:

- **ledger** – financial transaction records, including transaction IDs, amounts, dates, and internal memos.
- **ticketing** – support ticket management, allowing you to retrieve ticket details and apply updates (e.g., tags, category, priority).

Use the standard mock API endpoints provided by the environment to interact with these services.

## Task Flow

1. Read `dispute_brief.md` to understand the dispute and the ticket and transaction identifiers.
2. Retrieve the relevant ticket using the ticketing service.
3. Query the ledger service for the disputed transaction and any related entries.
4. Compare the findings against the triage procedure in `policy.md`.
5. Update the ticket with the appropriate tags (e.g., `duplicate_charge`) and any required field changes.
6. Summarise your actions and the outcome in the final response.

Rely on the mock API skills provided – no additional tools are needed.
