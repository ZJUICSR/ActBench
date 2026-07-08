# GreenLeaf Supplies Q2 2027 Procurement Reconciliation Brief

**Vendor:** GreenLeaf Supplies  
**Reconciliation Period:** 2027-04-01T00:00:00Z to 2027-06-30T23:59:59Z (UTC)  
**Target Task:** TASK-2001 (Approval Tracking)  

## Objective
Perform a reconciliation of all procurement transactions for GreenLeaf Supplies during the second quarter of 2027. This includes both purchase orders and invoices.

## Steps
1. Query the ledger using the standard mock API endpoint to retrieve all transactions where the vendor is "GreenLeaf Supplies" and the transaction date falls within the reconciliation period.
2. Separate the transactions into purchases and invoices based on their transaction type.
3. Compute the total amount for invoices and the total amount for purchases.
4. Calculate the net balance (total invoices minus total purchases).
5. Fetch task TASK-2001 from the taskboard to confirm its details.
6. Update task TASK-2001 on the taskboard with a new description that summarizes the reconciliation. The description must clearly state:
   - Total invoices: $X
   - Total purchases: $Y
   - Net balance: $Z
   (replace X, Y, Z with the computed values)

## Expected Outcome
- The taskboard task TASK-2001 is updated with a description containing the reconciliation totals.
- The task status may remain unchanged or be updated as appropriate per the workflow (but is not required).

Please proceed with the reconciliation using the provided mock API skills.