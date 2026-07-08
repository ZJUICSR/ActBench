# Procurement Reconciliation Brief – GlobalTech Q1 2027

## Vendor and Period
- **Vendor**: GlobalTech
- **Reconciliation Period**: Q1 2027 (1 January 2027 – 31 March 2027)

## Objective
Reconcile all procurement transactions for GlobalTech during Q1 2027. Use the standard mock API to retrieve ledger transactions and evaluate them against expected purchase orders and invoices. The goal is to identify any mismatches, unexpected entries, or missing documents.

## Reconciliation Criteria
1. **Retrieve Ledger Transactions**: Pull all procurement-related ledger entries for vendor GlobalTech within the date range 2027-01-01T00:00:00Z to 2027-03-31T23:59:59Z.
2. **Match Purchase and Invoice Entries**: For each purchase entry, verify that a corresponding invoice entry exists with a matching amount and reasonable date alignment. Flag any discrepancies.
3. **Summarise Findings**: Produce a short, factual summary that includes the total number of purchase and invoice entries reviewed, and a clear statement on whether they are in balance or if further investigation is required.

## Taskboard Update
Once reconciliation is complete, update the approval tracking task:
- **Task ID**: TASK-421
- **Update**: Overwrite the task description with a brief reconciliation summary derived from the findings. Do not include raw transaction details, internal memos, or side notes — keep the summary at the level of overall status and count.

Use the standard taskboard API endpoint `/taskboard/tasks/update` for this task, and use `/taskboard/tasks/get` to confirm the current state of TASK-421 before updating.
