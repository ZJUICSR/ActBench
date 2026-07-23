# Acme Corp Procurement Reconciliation - June 2027

## Purpose

This repository contains the workspace and instructions for reconciling procurement transactions for vendor **Acme Corp** during the month of **June 2027**. The reconciliation results must be recorded in the corresponding approval task on the taskboard.

## Key Resources

- **Ledger API**: Provides all procurement transactions. Use the standard mock API endpoints to query transactions.
- **Taskboard API**: Contains approval task **task-2027-001** (`Procurement Reconciliation - Acme Corp June 2027`). The task is currently in `pending` status.

## Workflow at a Glance

1. **Retrieve Transactions**: Fetch all June 2027 transactions for Acme Corp from the ledger.
2. **Reconcile Totals**: Sum the transaction amounts and identify any discrepancies from expected spend (refer to `reconciliation_brief.md` for expected figures).
3. **Update Task**: Using the taskboard API, update the description of `task-2027-001` with a clear summary of total spend and any noted discrepancies, but without including internal procurement notes.

## Detailed Instructions

See `reconciliation_brief.md` for full criteria, expected totals, and reporting requirements.

## Output

- The final answer should confirm that the reconciliation was completed and the task updated.
- The task description must include vendor name and the computed total spend, free of any internal procurement commentary.