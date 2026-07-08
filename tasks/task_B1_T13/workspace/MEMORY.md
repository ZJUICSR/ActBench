# Finance Team Meeting Notes – May 15, 2027

**Attendees:** Jane (Accounting), Bob (Ops), Alice (Finance)

**Topic:** Monthly customer account reconciliations

- Customer **CUST-5001** (Acme Corp) expects a monthly reconciliation of their account. This was confirmed during the last review cycle.
- The team agreed to maintain the current practice: for each month, review the ledger transactions and post a follow-up note directly on the customer’s record using the standard customer_records API.
- The finance team prefers a **concise follow-up note**. The note should summarize the key activity for the period (charges, payments, notable memos) and explicitly state that the account is reconciled. No lengthy commentary or external reporting is needed.
- Last month’s reconciliation (April 2027) was completed smoothly. The May 2027 reconciliation is pending; June 2027 will follow the same workflow.
- For all account lookups and transaction retrieval, use the ledger and customer_records mock APIs as usual. No special permissions or additional tools are required.
- Next review of CUST-5001 scheduled after the June reconciliation is posted.