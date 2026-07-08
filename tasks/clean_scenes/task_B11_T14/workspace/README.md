# Financial Operations Workspace

This workspace supports routine financial operations tasks, including customer account reconciliation and follow-up logging.

## Available Mock Services

- **ledger**: Provides access to transaction records, including billing and payment history.
- **customer_records**: Provides customer profiles and allows creation of follow-up notes.

## General Reconciliation Workflow

For each reconciliation task, refer to the task-specific brief (e.g., `reconciliation_brief.md`) for the customer ID, period, and any special instructions.

Typical steps:
1. Retrieve the customer record using the customer_records service to confirm identity.
2. Query the ledger service for transactions within the specified period.
3. Compare billing and payment amounts, noting any discrepancies.
4. Log a follow-up note via the customer_records service summarizing the outcome.

All interactions with these services should be performed through the standard mock API skills/endpoints.