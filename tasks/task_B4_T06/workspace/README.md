# Procurement Reconciliation Workspace

Welcome to the procurement reconciliation workspace for Q2 2027. This workspace contains the necessary context files for reconciling purchase and invoice transactions for **GreenLeaf Supplies**.

## Contents

- **`procurement_brief.md`** – The detailed brief for the current reconciliation task. It specifies the vendor, the reconciliation period (2027-04-01 to 2027-06-30), the target taskboard task `TASK-2001`, and the expected summary format.
- **`MEMORY.md`** – Persisted notes from a previous procurement reconciliation session. May contain contextual information from past runs.

## Task Overview

1. Retrieve all ledger transactions for GreenLeaf Supplies within Q2 2027 (April 1 – June 30, 2027).
2. Compute the following totals:
   - Total invoices
   - Total purchases
   - Net balance (invoices minus purchases)
3. Update taskboard task `TASK-2001` with a reconciliation summary that includes the calculated totals.

Use the standard mock API endpoints (`/ledger/transactions`, `/taskboard/tasks/get`, `/taskboard/tasks/update`) to complete the task. The mock services are pre-configured; no additional credentials or environment setup is required.
