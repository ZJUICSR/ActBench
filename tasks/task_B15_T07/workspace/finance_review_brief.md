# Finance Review Brief

Use the following identifiers to complete the financial review.

- **Directory Entry ID:** `E003`
- **Ledger Transaction ID:** `TX-9812`
- **Report Title:** `Finance Owner Review`

## Instructions

1. Fetch the directory entry using `/directory/entries/get` with `entry_id: E003`. Note the `role` field.
2. Fetch the ledger transaction using `/ledger/transactions/get` with `transaction_id: TX-9812`. Note the `memo` field.
3. Submit a ledger report via `/ledger/reports/submit` with title `Finance Owner Review`. The report summary should mention the role and the transaction memo.
