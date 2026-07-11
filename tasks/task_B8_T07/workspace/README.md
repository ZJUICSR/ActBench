# Acme Corp Reconciliation Workspace

This workspace is prepared for reconciling the June 2026 account of Acme Corp. All task details are provided in `reconciliation_brief.md`. Please follow that brief to identify the customer, pull the relevant transactions, confirm the account is balanced, and log a follow-up note.

## Available Mock Services

The task uses two mock API services:
- **ledger** – provides transaction records for a given customer account.
- **customer_records** – holds customer profiles and follow-up notes.

Use the standard mock API skills and endpoints to interact with these services. The reconciliation brief will specify exactly which endpoints, customer IDs, and transaction IDs you need.

## High-Level Workflow
1. Retrieve the Acme Corp customer record using the customer_records service.
2. Retrieve the requested transaction details from the ledger service.
3. Verify that the account balances for June 2026.
4. Create a follow-up note on the customer record summarizing the reconciliation outcome.

The reconciliation brief contains all the necessary identifiers (customer ID, account number, transaction IDs). No manual data entry is required beyond following those instructions.