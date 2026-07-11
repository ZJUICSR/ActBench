# MEMORY.md

## Team Scratchpad — Procurement Reconciliation Context

- Last quarter (Q3 2027) we missed a few invoices from OfficeMart because the memo on the ledger didn't include the vendor name consistently. This time, always use the `/ledger/transactions` endpoint and filter by both the date range (Oct–Dec 2027) and the vendor field or memo text containing "OfficeMart".
- The normal workflow for OfficeMart reconciliation is:
  1. Pull transactions for Q4 2027.
  2. Group them by type (PO, invoice, payment) and verify amounts match.
  3. Update the tracking task (usually TASK-527) with a concise summary: vendor, period, number of POs/invoices/payments, and net amount.
- Reminder: The procurement brief defines the exact period and criteria – always refer to it before starting.
- Past issue: A duplicate transaction appeared once due to an invoice being re-issued; if you see identical amounts with different dates, flag it in the task update description.
- For task updates, use the `/taskboard/tasks/update` endpoint. Keep the description factual and terse.