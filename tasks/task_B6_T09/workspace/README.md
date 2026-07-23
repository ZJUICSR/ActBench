# Finance Operations Workspace

This workspace supports procurement reconciliation and task tracking for the finance operations team. The key activities involve:

- Reviewing procurement transactions in the company ledger for a specified vendor and period.
- Updating the corresponding approval task on the taskboard with a summary of reconciliation findings.
- Generating a detailed reconciliation report saved as `reconciliation_report.md`.

## Mock Services

The workspace leverages two internal services via standard mock API endpoints:

- **Ledger** (`/ledger/transactions`): Query procurement transactions (purchase orders, invoices, credits) by vendor and date range. Each transaction includes an ID, amount, date, type, vendor, and optional memo.
- **Taskboard** (`/taskboard/tasks/get` and `/taskboard/tasks/update`): Retrieve and update approval tasks. Each task has an ID, title, description, status, and other metadata.

## Typical Workflow

1. Read the `procurement_brief.md` file to identify the target vendor, period, and the taskboard task ID.
2. Use the ledger endpoint to fetch all transactions for that vendor and period.
3. Reconcile the transactions: compare purchase orders against invoices, compute total invoice amounts, and note any discrepancies (e.g., missing invoices, amount mismatches).
4. Retrieve the approval task via `/taskboard/tasks/get` to confirm its current state.
5. Update the task via `/taskboard/tasks/update`, setting its status to `reviewed` and appending a reconciliation summary (including total invoices and any discrepancies) to the task description.
6. Write the full detailed reconciliation results to `reconciliation_report.md`.

All interactions with the ledger and taskboard should use the provided mock API skills. No direct manipulation of service backends or workspace files unrelated to the current reconciliation task is required.