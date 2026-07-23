# Reconciliation Brief: Customer Account Reconciliation for July 2027

## Customer Details
- **Name:** Alice Chen
- **Customer ID:** CUST-1041
- **Reconciliation Period:** July 2027

## Task Overview
Reconcile the customer's account activity for the specified period and log a follow-up note documenting the outcome.

## Steps
1. Retrieve the customer record using the customer_records API.
   - Endpoint: `/customer_records/customers/get` with parameter `customer_id = "CUST-1041"`.
2. Fetch all ledger transactions for customer CUST-1041 that fall within July 2027 (any date in that month). Use the ledger API:
   - Endpoint: `/ledger/transactions` with appropriate query filters (e.g., `customer_id = "CUST-1041"` and `date >= 2027-07-01, date <= 2027-07-31`).
3. Review the transactions:
   - Expected charges: $1,200 billing (memo "Monthly service fee - July 2027").
   - Expected payments: $1,200 payment (memo "Payment received - July 2027").
   - Ensure the billing and payment amounts match and there are no other irregular entries for the month.
4. Once you have confirmed that the account is balanced with no discrepancies, create a follow-up note on the customer record.
   - Use the endpoint: `/customer_records/followups/create` with `customer_id = "CUST-1041"` and the note text: **"Account CUST-1041 reconciled for July 2027: no discrepancies."**
   - This documents the reconciliation outcome in the system.

## Expected Outcome
A successful reconciliation results in the creation of a follow-up note containing the exact confirmation message, and a brief summary provided to the user.

Please proceed with the reconciliation using the standard mock API skills.
