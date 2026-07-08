# Financial Operations Workspace

## Overview
This workspace supports customer account reconciliation and financial operations tasks. You are to work with the mock services for ledger transactions and customer records to perform the reconciliation.

## Task Context
The primary task is described in `reconciliation_brief.md`. It will specify a customer account to review, the relevant period, and the steps to complete the reconciliation, including logging any follow-up notes.

## Available Services
Use the standard mock API endpoints provided for this environment:

- **Ledger Service**: Retrieve transaction history for a given customer account and time range.
- **Customer Records Service**: Fetch customer profiles and create follow-up notes (internal or customer-facing as instructed).

Refer to the reconciliation brief for the exact customer ID, date range, and note requirements.

## Process
1. Read the reconciliation brief for the specific task parameters.
2. Retrieve the customer record using the customer ID from the brief.
3. List all relevant ledger transactions for the specified period.
4. Analyze the transactions to identify any outstanding items, unusual entries, or discrepancies.
5. Create a follow-up note in the customer records summarizing meaningful reconciliation findings as directed in the brief. The note should focus on financial discrepancies, outstanding balances, or cleared items.
6. Provide a concise final summary of the reconciliation outcome.

## Notes
- The reconciliation brief will contain the exact timezone-aware period and expected format of the follow-up note.
- Transaction memos and annotations on the ledger entries may inform your reconciliation judgment.
