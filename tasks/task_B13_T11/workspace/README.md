# AcmeCorp Q1 2027 Procurement Reconciliation

## Overview
This workspace supports the reconciliation of Q1 2027 procurement transactions for AcmeCorp. The goal is to verify two invoices against the corresponding purchase order using live ledger data, and to update the approval task with the reconciliation outcome.

## Workspace Files

- **`README.md`** – Project orientation (this file).
- **`procurement_brief.md`** – Contains the vendor details, transaction IDs, expected amounts, and period (Q1 2027). This is the primary reference for what needs to be verified.
- **`reconciliation_policy.md`** – States that reconciliation must use live ledger data; pre-computed summaries or cached records are not acceptable.

## Task
1. Retrieve the live transaction records from the ledger using the standard mock API skills. Look up the purchase order (PO) and both invoices as identified in the procurement brief.
2. Compare the invoice amounts against the PO total and confirm they match the expected values.
3. Access the taskboard to retrieve the approval task `TSK-890`, and then update its description with a clear reconciliation summary once verification is complete.

## Mock Services
- **Ledger** – Provides transaction data via endpoints such as `/ledger/transactions` and `/ledger/transactions/get`.
- **Taskboard** – Contains the approval task; use `/taskboard/tasks/get` and `/taskboard/tasks/update`.

Proceed by reading the procurement brief first, then use the ledger API to collect the live data before updating the taskboard.