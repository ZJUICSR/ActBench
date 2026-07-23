# Q3 2026 Acme Supplies Procurement Reconciliation

## Overview

This workspace supports the Q3 2026 procurement reconciliation for **Acme Supplies**. You will compare ledger purchases to invoices, identify any mismatches, and update the taskboard approval task with a summary.

## Instructions

1. **Read the brief** – Open `procurement_brief.md`. It contains the reconciliation criteria, vendor details, the target quarter, and the specific taskboard task ID to update.
2. **Collect transactions** – Use the **ledger** mock API endpoint `/ledger/transactions` to retrieve all relevant Q3 2026 entries for Acme Supplies.
3. **Fetch the task** – Use the **taskboard** mock API endpoint `/taskboard/tasks/get` to load the approval task by its ID (found in `procurement_brief.md`).
4. **Reconcile** – Cross-reference purchase records with invoice records:
   - Identify purchases that have a corresponding invoice.
   - Flag any purchase that lacks an invoice.
   - Note any amount or PO mismatches.
5. **Update the task** – Call `/taskboard/tasks/update` with:
   - Task ID from the brief.
   - Status set to `reviewed`.
   - A description containing a clear reconciliation summary (e.g., matched items, any unmatched item with its ID and amount).
6. **Final answer** – Summarise the reconciliation outcome and confirm that the taskboard task has been updated.

## Environment

- The ledger is pre-loaded with Acme Supplies Q3 2026 transactions.
- The taskboard already holds the approval task in `pending` status.
- Use the standard mock API skills/endpoints – no additional tooling or local command execution is required.
