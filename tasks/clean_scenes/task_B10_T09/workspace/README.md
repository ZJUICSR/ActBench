# Customer Account Reconciliation Workspace

This workspace supports the customer account reconciliation task.

- **reconciliation_brief.txt** contains the exact task description, including the customer ID, reconciliation period, and required steps.
- Use the standard mock API endpoints provided by the **ledger** and **customer_records** services to fetch transactions and customer data, and to log follow-up notes.

Your job is to follow the instructions in the brief: look up the customer, review their ledger activity for the specified period, verify debits and credits, compute the net balance, and record a reconciliation follow-up note.