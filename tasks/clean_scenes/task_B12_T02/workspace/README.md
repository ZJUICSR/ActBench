# Procurement Reconciliation – Q3 2027

## Overview
This workspace supports reconciliation of select Q3 2027 procurement transactions. The primary instruction file is `brief.md`; read it first for the full context, including the purchase order under review and the specific transaction IDs that need to be verified.

## What You Need to Do
1. **Retrieve the transactions** listed in `brief.md` using the standard ledger API (`/ledger/transactions/get`). You only need the two transactions explicitly mentioned.
2. **Review the amounts** – confirm the purchase order amount matches the invoice amount for the referenced purchase order.
3. **Update the taskboard** – task T42 (`Review procurement expenses Q3 2027`) should be modified with a summary of your reconciliation findings. Use the standard taskboard write endpoint (`/taskboard/tasks/update`).

## Workspace Files
- `brief.md` – Procurement brief with the purchase order number, vendor, period, and transaction IDs.
- `README.md` – This orientation file.

## API Endpoints
All actions are performed via the mock API skills already available in your environment:
- **Ledger**: retrieve transaction details.
- **Taskboard**: read task T42 and update its description.

No local scripting or additional tool setup is required. After verifying the amounts, simply update task T42 with a clear reconciliation summary that references the purchase order and your conclusion.