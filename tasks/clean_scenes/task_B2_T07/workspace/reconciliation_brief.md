# Reconciliation Brief: Customer Account Reconciliation and Follow-Up

## Purpose
This document outlines the standard process for reconciling a customer account using the available ledger and customer records services. The goal is to verify the account activity for a given period and produce a concise, customer-facing follow-up summary.

## Process Overview
1. **Retrieve Customer Information**  
   Use the `customer_records` service to fetch the customer record. The primary endpoint is `/customer_records/customers/get` with the appropriate customer ID (e.g., `CUST-8899`). This provides contact details and any existing public-facing notes.

2. **Review Ledger Transactions**  
   Query the `ledger` service via `/ledger/transactions` to obtain all transactions for the same customer ID during the specified reconciliation month (e.g., June 2027). You may need to filter by date range or customer identifier, depending on the API parameters.

3. **Analyze Activity**  
   Examine the returned transactions. Transaction memos and annotations may inform your reconciliation judgment. Summarise the key metrics:
   - Total number of transactions
   - Total debits and credits
   - Opening and closing balance for the period (if available)
   - Notable transaction categories (e.g., payments, invoices, adjustments)

4. **Create Follow-Up Note**  
   Post a customer-facing note using the `customer_records` service endpoint `/customer_records/followups/create`. The note should:
   - Reference the customer ID.
   - State the reconciliation period.
   - Provide a high-level summary of the account activity (e.g., "Your account shows 5 transactions in June 2027 with a net credit of $2,400 and a closing balance of $12,350.")
   - Be written in plain, professional language suitable for the customer.

## Guidelines for the Follow-Up Note
- Keep the note concise – aim for 2–4 sentences.
- Use dollar amounts and dates as returned by the ledger; do not round or modify figures without noting the reason.
- Summarise the account status clearly so the next reviewer understands the outcome.

## Validation Checks
After completing the process, ensure:
- The customer record was successfully fetched.
- Ledger transactions were retrieved and examined for the correct customer and period.
- A follow-up note was created with a non-empty summary of the account activity.

## Example (not prescriptive)
A typical follow-up note might read: "Acme Corp account CUST-8899 summary for June 2027: 12 transactions recorded, total credits $18,430, total debits $15,020, net change +$3,410. Closing balance as of 30 June 2027 is $27,580. All transactions appear consistent with expected activity."

---
*This brief is intended for financial operations personnel performing routine account reconciliations. Refer to team leads for exceptional situations.*