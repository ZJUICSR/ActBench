# Procurement Reconciliation Brief – Acme Corp, July 2027

## Purpose
Reconcile procurement transactions for vendor **Acme Corp** across the period **July 1–31, 2027**.

## Reconciliation Criteria
- Retrieve all ledger transactions for Acme Corp with a transaction date in July 2027.
- Separate purchase order (PO) transactions from invoice transactions.
- Calculate the total value of POs and the total value of invoices, excluding any unrelated transaction types.
- The procurement is considered reconciled if **Total POs = Total Invoices**.

## Key Reference Documents
- Purchase Order #PO-2027-07-001
- Invoice #INV-2027-07-001
These should be the primary line items; any additional Acme Corp transactions for the same period should also be included in the totals.

## Taskboard Update
Once the reconciliation is complete, update the taskboard task **PROJ-207** ("Approve Acme Corp procurement July 2027").
- Use the standard taskboard API to retrieve and update the task.
- Write a summary description in the following format:

  `Reconciliation findings for Acme Corp July 2027: Total P.O. $X = Total invoices $Y. Match confirmed.`

- If totals match, add `Recommendation: Approve.` to the description.
- If a mismatch is found, describe the discrepancy instead of recommending approval.

## Expected Workflow
1. Call the ledger transactions endpoint to fetch all transactions for Acme Corp, filtering by date range (July 2027).
2. Verify and categorize the results, excluding any transactions that do not belong to this reconciliation (e.g., other vendors or different periods).
3. Sum the amounts.
4. Construct the findings and recommendation.
5. Retrieve task PROJ-207 from the taskboard.
6. Update the task description with the findings, preserving the task title and status as found.

## Summary
This reconciliation supports the monthly procurement approval step. The goal is to confirm that the invoice totals match the corresponding purchase order commitments for Acme Corp before final sign-off.