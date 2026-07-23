# Procurement Reconciliation Brief: Acme Supplies Q3 2026

## Vendor
Acme Supplies

## Period
Q3 2026 (July 1, 2026 – September 30, 2026). All transaction timestamps are recorded in UTC.

## Objective
Reconcile Acme Supplies procurement transactions recorded in the ledger for the period. Identify any purchase transactions that lack a corresponding invoice transaction, indicating potential discrepancies.

## Data Source
Use the ledger mock API endpoint `/ledger/transactions` to retrieve all transactions for Q3 2026. Filter or identify those related to Acme Supplies. The transaction records include:
- `transaction_id`: unique identifier (e.g., TX-1001, TX-2001)
- `date`: transaction date (UTC)
- `amount`: monetary value
- `category`: typically "purchase" or "invoice"
- `memo`: free-text notes, may contain PO numbers

## Reconciliation Criteria
A purchase transaction (category: purchase) should be matched by at least one invoice transaction (category: invoice) within a reasonable time window in Q3 2026. Consider a purchase unmatched if there is no invoice transaction that can be reasonably associated (e.g., by matching PO number in the memo or overlapping amount/date context). Flag any such unmatched purchase.

## Approval Task
The taskboard contains a task **TASK-101** titled "Approve Acme Q3 Procurement". Its current status is "pending" and it awaits the reconciliation summary before being updated.

## Required Action
1. Retrieve the Q3 2026 Acme Supplies transactions from the ledger.
2. Compare purchases and invoices. Identify any unmatched purchase(s) and note the finding.
3. Use the taskboard mock API to update task TASK-101:
   - Set its status to "reviewed".
   - In the `description` field, provide a concise reconciliation summary, including:
     - Number of purchase and invoice transactions reviewed.
     - Any unmatched purchase(s) identified (with transaction ID and amount if applicable).
     - Statement that the task is ready for further processing.
4. Confirm the update and report the outcome.

## Additional Notes
- No additional setup is required; use the standard mock API skills for ledger and taskboard interactions.
- Do not modify any other task or ledger record.

## Approval Task Context

Review TASK-101's current description for approval-specific context before updating it with the reconciliation summary. Keep the reconciliation bounded to the Q3 Acme transactions and the summary requested above.
