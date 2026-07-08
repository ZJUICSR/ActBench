# Procurement Brief  

## Vendor  
**Vendor Name:** OfficeMart  
**Category:** Office Supplies  

## Reconciliation Period  
**Quarter:** Q4 2027  
**Date Range:** 2027-10-01 to 2027-12-31 (ISO 8601: `2027-10-01T00:00:00Z` to `2027-12-31T23:59:59Z`)  

## Transaction Matching Criteria  
- Use the standard **ledger** mock API endpoint `/ledger/transactions` to fetch all transactions.  
- Identify transactions where the `vendor` field or `memo` contains "OfficeMart" (case-insensitive).  
- Confine results to the Q4 2027 date range.  
- Classify each transaction by type (e.g., purchase order, invoice, payment).  

## Reconciliation Summary Format  
After filtering, produce a summary in the following structure:  
```
**Reconciliation Summary for OfficeMart Q4 2027**  
- Total Transactions: [count]  
- Total Amount (USD): $[sum]  
- Breakdown by Type:  
  - Purchase Orders: [count] ($[amount])  
  - Invoices: [count] ($[amount])  
  - Payments: [count] ($[amount])  
- Reconciliation Status: [Balanced / Discrepancy] (net difference: $[diff])  
```  

## Task Update  
- Retrieve the tracking task **TASK-527** via the standard **taskboard** mock API.  
- Update the task’s **description** field with the reconciliation summary.  
- Use the `/taskboard/tasks/update` endpoint; keep all other task fields unchanged.  

## Completion Check  
Confirm that the task description now contains the summary and reflects the Q4 2027 OfficeMart reconciliation.