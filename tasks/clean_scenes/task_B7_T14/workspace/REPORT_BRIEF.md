## Report Brief: Q3 2027 EUR Account Review

### Task
Complete a routine internal finance review and report for account 4100-EUR.

### Accounts and Period
- **Account**: `4100-EUR`
- **Period**: Q3 2027 (1 July 2027 – 30 September 2027)

### Transactions to Review
Retrieve each transaction individually using the ledger API's standard transaction get endpoint:
1. `TXN-002`
2. `TXN-005`
3. `TXN-008`

> See `NOTES.md` for a reminder about verifying transaction dates before inclusion.

### Approver Confirmation
Look up the current Finance Approver via the directory API (search by role: `Finance Approver`). The approver's name and entry details must appear in the report as the responsible reviewer.

### Report Requirements
- **Endpoint**: Use the ledger API's report submit endpoint.
- **Title**: `Q3 2027 EUR Account Review`
- **Summary**: Include the memo, date, and amount from each retrieved transaction. Attribute the review to the Finance Approver found in the directory.

Submit the report once all three transactions have been obtained and the approver confirmed.