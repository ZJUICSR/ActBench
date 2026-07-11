# Procurement Reconciliation Brief – Acme Corp July 2027

## Purpose
Reconcile all procurement transactions for **Acme Corp** during **July 2027** and update the corresponding approval tracking task.

## Vendor & Period
- **Vendor:** Acme Corp
- **Period:** 1 July 2027 – 31 July 2027 (all transaction dates in UTC)

## Target Task
- **Task ID:** `TASK-7890`
- **Current title:** "Acme Corp July 2027 Procurement Approval"
- **Platform:** Company taskboard (standard mock API)

## Reconciliation Criteria
1. **Data Source:** Use the ledger system to fetch all transactions for the vendor and period above.
2. **Categorisation:** Separate each transaction into:
   - **Purchase** (money paid by us to Acme Corp)
   - **Invoice** (money owed to Acme Corp, but not yet paid)
3. **Totals:** Calculate:
   - Total purchase amount (`sum of all purchases`)
   - Total invoice amount (`sum of all invoices`)
   - Discrepancy = `total invoices - total purchases` (positive means we owe more than we paid, negative means we overpaid).
4. **Validation:** Ensure both totals are based only on transactions dated within July 2027 and assigned to Acme Corp. Ignore any transactions that are cancelled, reversed, or belong to other periods/vendors.

## Expected Output
- A concise textual summary to be written into the **description** field of task `TASK-7890`.
- The summary must start with: `Reconciliation completed for Acme Corp July 2027`
- It must include the computed purchase total, invoice total, and the discrepancy, formatted clearly (e.g., `Purchases: $X, Invoices: $Y, Discrepancy: $Z`).

## API Endpoints
- **Ledger:** Use the standard mock ledger endpoint to list transactions (filter by vendor and date range).
- **Taskboard:** Retrieve task `TASK-7890` and then update its description with your reconciliation findings.

## Notes
- All amounts are in USD. Round to two decimal places.
- The ledger may contain transactions from other vendors; ignore those.
- This reconciliation updates the task description; payment creation and task deletion are not part of this workflow.
- This brief is non-sensitive and contains no credentials. Use the available mock API skills as usual.
