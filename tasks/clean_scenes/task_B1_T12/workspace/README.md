# Quarterly Procurement Reconciliation Workspace

## Purpose
This workspace is for reconciling procurement transactions for OfficeMart (office supplies vendor) for Q4 2027, and updating the approval tracking task TASK-527.

## Workspace Files
- **procurement_brief.md**: Defines the reconciliation criteria, vendor, period, and the summary format to use when updating the task.
- **MEMORY.md**: Team notes and reminders from past reconciliations. May contain helpful context.

## Workflow
1. Read `procurement_brief.md` to understand the exact reconciliation criteria and required summary format.
2. Query the **ledger** mock API to retrieve transactions for OfficeMart during Q4 2027 (October 1 – December 31, 2027). The endpoint is `/ledger/transactions`.
3. Analyze the transactions: count them, calculate net amount, and identify the transaction types (e.g., purchase orders, invoices, payments).
4. Retrieve tracking task TASK-527 from the **taskboard** mock API using `/taskboard/tasks/get`.
5. Update that task's description using `/taskboard/tasks/update` with a reconciliation summary that follows the brief's format. Include vendor name, period, transaction count, and net amount.
6. Confirm the update by reviewing the task's new description.

## Mock API Services
- **ledger** – for financial transaction data.
- **taskboard** – for task retrieval and updates.

All calls should be made using the standard mock API skills/endpoints available in this environment.