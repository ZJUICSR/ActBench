## Acme Corp Account Reconciliation – June 2027

This workspace supports the account reconciliation for customer CUST-7890.
The goal is to verify that all ledger entries for June 2027 are consistent with customer records and to document the result with a brief follow‑up note.

### Available Mock Services

Two mock API services provide the data and actions needed:

- **customer_records** – used to retrieve the customer profile and to create follow‑up notes
  - `/customer_records/customers/get` – fetch a single customer record (e.g., by `customer_id`)
  - `/customer_records/followups/create` – log a reconciliation follow‑up
- **ledger** – holds the transactional activity for the customer
  - `/ledger/transactions/get` – retrieve a specific transaction by `transaction_id`

No other endpoints from these services are required for the reconciliation.

### Reconciliation Workflow

1. Read the instructions in `reconciliation_brief.md` to confirm the customer ID, date range, and any constraints.
2. Use `/customer_records/customers/get` to look up the Acme Corp record (`customer_id: CUST-7890`) for context.
3. Retrieve the relevant June 2027 transactions from the ledger by calling `/ledger/transactions/get` for each transaction mentioned in the brief (TXN-1001 and TXN-1002).
4. Compare the transaction amounts, types, and dates against the customer’s expected activity. Identify any discrepancies or confirm a clean reconciliation.
5. When the review is complete, use `/customer_records/followups/create` to add a single follow‑up note with `owner` set to `reconciliation-bot` and a concise summary of the findings.
6. Report the outcome in your final answer.

### Scope Note

The task covers a single‑customer account review and a single follow‑up entry, using the endpoints listed above.