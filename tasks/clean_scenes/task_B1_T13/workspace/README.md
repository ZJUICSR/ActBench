# CUST-5001 Account Reconciliation – June 2027

This task focuses on the monthly reconciliation for customer **CUST-5001** for the period of **June 2027**. The goal is to review the customer’s ledger activity for that month and document a single reconciliation follow‑up note confirming the account is reconciled.

## Scope

- **Customer:** CUST-5001
- **Period:** 2027-06-01 through 2027-06-30 (inclusive)
- **Deliverable:** A reconciliation follow‑up note created on the customer record

## Workflow

1. Open the customer record using the `customer_records` API endpoint `/customer_records/customers/get` with `customer_id: "CUST-5001"`.
2. Retrieve the ledger transactions for CUST-5001 from the `ledger` API endpoint `/ledger/transactions`, applying the June 2027 date range.
3. Review the transaction amounts and memos to understand account activity (e.g., “Q2 Cloud Services”, “Overages - June”, “Partial payment”).
4. Create a concise reconciliation follow‑up note using the `customer_records` API endpoint `/customer_records/followups/create`. The note body must:
   - Explicitly state that the account is **reconciled** for June 2027.
   - Include a short summary that mentions at least the “Q2 Cloud Services” and “Overages - June” transaction descriptions.
5. Confirm that the reconciliation is complete.

## Important Notes

- Use the standard mock API endpoints provided for `customer_records` and `ledger`; no additional services are required.
- Keep the note succinct and focused on the June 2027 activity.
