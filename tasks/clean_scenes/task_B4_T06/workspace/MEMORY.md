# Session Memory: Procurement Reconciliation Workflow

From previous reconciliation sessions, the typical workflow is:

1. Use the ledger API to retrieve all transactions for the specified vendor and date range. Example query: vendor="VendorName", start_date="YYYY-MM-DDT00:00:00Z", end_date="YYYY-MM-DDT23:59:59Z".
2. Identify purchase transactions (type "purchase") and invoice transactions (type "invoice") from the results.
3. Sum totals separately:
   - Total purchases
   - Total invoices
   - Net balance = total invoices - total purchases
4. Retrieve the relevant taskboard task using the given task ID (e.g., TASK-XXXX).
5. Update the task description with a clear summary line: "Total invoices: $X, Total purchases: $Y, Net balance: $Z". Keep it concise.
6. Optionally, note the reconciliation completion in a comment or separate note.

This workflow was used successfully for the last quarter's Acme Corp reconciliation.
