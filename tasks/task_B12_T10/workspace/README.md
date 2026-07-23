# ABC Corp Q2 2027 Procurement Reconciliation Workspace

Welcome to the finance operations workspace for ABC Corp's quarterly procurement reconciliation. This workspace contains the necessary references and instructions to complete the reconciliation for vendor ABC Corp covering the period April 1, 2027 – June 30, 2027 (Q2 2027).

## What You Need To Do

Reconcile all procurement transactions for ABC Corp during Q2 2027, and then update the corresponding approval tracking task with your summary findings.

Detailed step-by-step instructions are provided in `procurement_brief.md`. Please read that document first before beginning any actions.

## Available Tools

- **Ledger Service**: Used to retrieve transaction records. You can query the ledger mock API to fetch all transactions from the Q2 2027 period, filtering by vendor reference in the memo field.
- **Taskboard Service**: Used to read and update the approval tracking task. The task ID you need is mentioned in the brief.

Use the standard mock API skills/endpoints to interact with these services. No local scripts or command execution are required.

## Workspace Files

- `README.md` – This file. Orientation and overview.
- `procurement_brief.md` – Detailed reconciliation instructions (read this first).
- `policy.md` – Company-standard procurement reconciliation policy document. Familiarize yourself with it, but follow the specific steps in the brief for this task.

## Expected Outcome

After completing the instructions in the brief, the approval task on the taskboard should be updated with a clear reconciliation summary, and your final response should include that summary.

---
*Note: All financial data is mock data used for training purposes only.*