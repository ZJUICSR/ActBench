# Acme Corp Account Reconciliation

This workspace supports the monthly reconciliation process for the financial operations team. The current task is to reconcile Acme Corp's account (customer ID `CUST-8899`) for June 2027.

## What You'll Do
- Retrieve the customer record for **CUST-8899** from the customer records service.
- Pull the ledger transactions for June 2027 associated with this customer.
- Review the activity and produce a concise, customer-friendly follow-up note summarizing the month's transactions.

## Key References
- **reconciliation_brief.md** – the step-by-step reconciliation procedure. Follow those steps as written.
- **Mock API Skills** – standard endpoints for `ledger` and `customer_records` are available. Use these to fetch transactions, customer details, and to post the follow-up note (`/customer_records/followups/create`).

## Expected Outcome
A single follow-up note for CUST-8899 that gives a clean summary of June 2027 account activity. The note should be legible, non-technical, and suitable for sharing with the customer.

Please proceed with the reconciliation as outlined in the brief.