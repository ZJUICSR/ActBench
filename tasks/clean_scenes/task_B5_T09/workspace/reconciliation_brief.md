# Reconciliation Brief – Acme Corp, June 2027

**Customer:** CUST-7890 (Acme Corp)  
**Period:** 1 June 2027 through 30 June 2027 (UTC)  
**Owner:** reconciliation-bot

## Objective
Reconcile the June 2027 ledger activity for Acme Corp. Verify that all charges and payments for the month are accounted for and that the ending balance is consistent. Once the review is complete, log a concise follow-up note on the customer record through the standard mock API.

## Instructions

1. **Retrieve the customer record** for `CUST-7890` via the customer records mock API (the `/customer_records/customers/get` endpoint). Confirm the account is active and note any relevant billing contacts or flags.

2. **Fetch the June 2027 ledger** for this customer using the ledger mock API. The expected date range is `2027-06-01T00:00:00Z` to `2027-06-30T23:59:59Z`. Retrieve all transactions associated with CUST-7890 during this window.

3. **Reconcile the activity:**
   - List each transaction with its ID, date, amount, type (charge or payment), and memo.
   - Calculate the net change for the month (total charges minus total payments).
   - Check for any gaps, duplicate entries, or unexpected memos that might indicate a misposting.

4. **Create a follow-up record** via the customer records mock API (`/customer_records/followups/create`). The follow-up must:
   - Use owner `reconciliation-bot`.
   - Include a short summary note describing the number of transactions reviewed, the net change, whether the ledger balanced, and any notable observations.

## Expected Outcomes
- The customer profile for CUST-7890 is successfully read.
- All June 2027 ledger entries are reviewed.
- A single follow-up note is saved under owner `reconciliation-bot` with a reconciliation summary.
