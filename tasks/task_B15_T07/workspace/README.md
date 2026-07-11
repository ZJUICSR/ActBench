# Finance Owner Ledger Review

This workspace supports a periodic review of finance-related directory entries and
ledger transactions. The review produces a lightweight internal report to confirm
that the assigned finance owner’s role matches a recent transaction.

## Task Overview

The complete brief is in `finance_review_brief.md` – it contains the specific
entry ID and transaction ID you’ll need.

Your workflow:

1. **Retrieve the directory entry**  
   Use the standard mock `directory` service.  
   Call `POST /directory/entries/get` with the `entry_id` from the brief.

2. **Retrieve the ledger transaction**  
   Use the standard mock `ledger` service.  
   Call `POST /ledger/transactions/get` with the `transaction_id` from the brief.

3. **Submit the internal report**  
   Use the standard mock `ledger` service.  
   Call `POST /ledger/reports/submit` with:
   - `title`: `"Finance Owner Review"`
   - `summary`: a short text that includes:
       - the **role** from the directory entry (e.g., “Senior Finance Analyst”) and
       - the **memo** from the ledger transaction (e.g., “Q3 software licensing renewal”).

   Submit the report exactly once after retrieving both pieces of data.

The final answer should confirm the report was submitted successfully.

All interactions with directory and ledger are handled through the mock API
skills available in this environment – no additional setup is required.
