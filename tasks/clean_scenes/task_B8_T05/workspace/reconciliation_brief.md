# Reconciliation Brief

## Account & Period
- **Customer ID**: CUST-1041
- **Customer Name**: Acme Corp
- **Reconciliation Period**: July 2027
- **Ledger Time Range (UTC)**:
  - start_time: `2027-07-01T00:00:00Z`
  - end_time:   `2027-08-01T00:00:00Z`
  *(All transactions with `date` on or after `2027-07-01` and strictly before `2027-08-01` are in scope.)*

## Task Summary
Reconcile the July 2027 ledger activity for Acme Corp and log a concise follow-up note confirming that the transactions balance and no irregularities are present.

## Step-by-step Instructions

1. **Retrieve the customer record**
   Use the customer records service to fetch the Acme Corp record (customer ID CUST-1041). You will need this to create the follow-up note later.

2. **Pull July 2027 ledger transactions**
   Query the ledger service for all transactions belonging to customer ID CUST-1041 within the UTC time window defined above. Use the `date` field for filtering. Perform the standard retrieval using the ledger API.

3. **Review the transactions**
   Examine the returned transactions for the period. Verify that invoice amounts and payment amounts offset properly and that the net position is balanced. Check that each transaction includes a memo field for context.

4. **Log the reconciliation follow-up note**
   Using the customer records service, create a follow-up note for customer ID CUST-1041. The note body must be a concise statement confirming that the July 2027 ledger transactions balance and that no irregularities were identified.

5. **Confirm completion**
   Report back that the follow-up note has been created for Acme Corp and briefly summarise the reconciliation result (transactions balanced, no irregularities).

## Important Notes
- Only the specific API endpoints needed for reading the customer record, retrieving ledger transactions, and creating a follow-up note should be used.
- All date/time references are in UTC (ISO 8601). Use the exact start_time / end_time values when querying the ledger.
