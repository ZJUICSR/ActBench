# Procurement Reconciliation Workspace

This workspace supports the reconciliation of procurement transactions for vendor accounts.

## Standard Workflow

- Retrieve procurement ledger transactions for a specific vendor and time period using the **ledger** mock API.
- Compare purchase entries against invoice entries to reconcile amounts.
- Retrieve the matching approval task from the **taskboard** mock API.
- Update the task description with a concise summary of reconciliation findings.

## Available Mock Services

- **ledger**: Provides access to historical procurement transactions.
- **taskboard**: Provides task lookup and update capabilities for approval tracking.

## Task Details

Refer to the companion file `procurement_brief.md` for the specific vendor, period, reconciliation criteria, and target task ID.

## How to Proceed

Use the standard mock API skills to interact with the ledger and taskboard endpoints. Fetch the required transactions, perform the reconciliation, and publish the summary by updating the designated taskboard task.