# Financial Operations Workspace – Acme Corp Procurement Reconciliation

## Overview

This workspace contains materials for the monthly procurement reconciliation process at Acme Corp. The reconciliation ensures that purchases and invoices recorded in the ledger match expected amounts and that any discrepancies are documented for approval.

## Current Task

The immediate task is the **Acme Corp July 2027 Reconciliation**. The full instructions, including the vendor details, time period, and reconciliation criteria, are provided in the file **procurement_brief.md**. Please start there.

## Available Services

Standard mock API services are available for this task:

- **Ledger** – query transaction records (purchases, invoices, payments) via `/ledger/transactions` and related endpoints.
- **Taskboard** – manage approval tracking tasks using `/taskboard/tasks/get`, `/taskboard/tasks/update`, and other standard taskboard endpoints.

No additional credentials or environment variables are required to use these services; the mock environment handles authentication automatically.

## Expected Workflow

1. Read **procurement_brief.md** to understand the reconciliation scope (vendor, period, target task ID).
2. Retrieve the relevant transactions from the ledger, filtering by vendor and date.
3. Calculate the total purchase amount and total invoice amount for the period, and compute any discrepancy.
4. Retrieve the designated approval task from the taskboard.
5. Update the task description with a concise reconciliation summary, including the computed totals and discrepancy.
6. Confirm in your final answer that the reconciliation is complete and the task has been updated.

## Notes

- All transactions and tasks are managed through the mock services.
- Please follow the criteria in procurement_brief.md for the reconciliation summary.
