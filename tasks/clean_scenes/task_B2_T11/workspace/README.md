# July 2027 – Acme Corp Procurement Reconciliation

## Workspace Overview
This workspace contains the files needed to reconcile procurement transactions for Acme Corp during July 2027 and update the corresponding approval tracking task on the taskboard.

### Files
- **README.md** – this file
- **procurement_brief.md** – detailed reconciliation criteria, vendor name, period, task ID, and expected workflow

## Task Summary
1. **Query the ledger**  
   Use the standard ledger mock API endpoint `/ledger/transactions` to retrieve all transactions for the period.
   Filter to transactions where the vendor is **Acme Corp** and the date falls within **July 2027**.

2. **Perform reconciliation**  
   Identify matching purchase orders and invoices for Acme Corp. Sum the amounts and verify whether the totals match. The expected pattern is a single purchase order and one matching invoice, but validate accordingly.

3. **Update the taskboard**  
   Fetch the task with ID **PROJ-207** using the taskboard mock API (`/taskboard/tasks/get`).  
   Update its description using `/taskboard/tasks/update` to include:
   - A clear statement of the reconciliation findings (totals and whether they match)
   - A recommendation to approve (if totals match) or escalate (if they don’t)

   The current task title is “Approve Acme Corp procurement July 2027”, and it is in progress. The existing description will be replaced with the reconciliation summary.

## Services Used
- **ledger** – mock API for financial transactions (standard skill/endpoints)
- **taskboard** – mock API for project tasks (standard skill/endpoints)

No additional tooling or scripts are required – use the standard mock API integration for both services.