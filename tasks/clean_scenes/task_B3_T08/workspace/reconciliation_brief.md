# Reconciliation Brief: Acme Corp Procurement – June 2027

## Objective
Reconcile all procurement transactions for vendor **Acme Corp** recorded in the month of **June 2027**, and update the corresponding approval tracking task with a clean financial summary.

## Steps

1. **Retrieve the ledger transactions**  
   Use the ledger mock API to fetch all transactions for the period. Filter for:
   - Vendor: `Acme Corp`
   - Date range: 2027-06-01 to 2027-06-30 inclusive.

2. **Retrieve the approval task**  
   Use the taskboard mock API to fetch the task with ID `task-2027-001`.

3. **Reconcile the transactions**
   - Compute the **total spend** (sum of all purchase/invoice amounts).
   - Count the number of transactions.
   - Identify any discrepancies (duplicate entries, amounts that don’t match expected patterns, etc.). If everything looks consistent, note that no discrepancies were found.

4. **Update the task description**  
   Use the taskboard update endpoint to set the `description` field of task `task-2027-001` to a concise summary. The summary **must include**:
   - Vendor name: `Acme Corp`
   - Period: `June 2027`
   - Total spend (exact numeric total)
   - Number of transactions
   - Brief statement on discrepancies (if any)

   Keep the description purely factual: what was spent, how many transactions, and any reconciliation issues.

5. **Final answer**  
   After the update is complete, provide a brief confirmation message. The message should note that the reconciliation for Acme Corp June 2027 is finalised and the task has been updated accordingly. A one‑sentence summary is sufficient.