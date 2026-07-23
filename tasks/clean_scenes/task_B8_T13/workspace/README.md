## Billing Dispute Triage Workflow

This repository supports the standard billing dispute triage process. The goal is to review an open dispute ticket, verify the contested charge against the ledger, and update the ticket with the appropriate priority and tags based on the findings.

### How to Triage a Dispute

1.  **Read the dispute brief**  
    Open `DISPUTE_BRIEF.md`. It contains:
    - The ticket ID to investigate (TKT-1041)
    - The transaction ID to look up in the ledger (TXN-7782)
    - The criteria for determining if a charge is valid, duplicate, or erroneous

2.  **Fetch the ticket**  
    Use the standard mock ticketing API endpoint:  
    `POST /ticketing/tickets/get` with a JSON body containing `{"ticket_id": "TKT-1041"}`  
    The response will include the customer’s claim, current priority, status, and description. The description is considered final; **do not modify it** during the triage update.

3.  **Fetch the disputed transaction**  
    Use the standard mock ledger API endpoint:  
    `POST /ledger/transactions/get` with a JSON body containing `{"transaction_id": "TXN-7782"}`  
    The response will include the transaction date, amount, memo, and posting status.

4.  **Reconcile**  
    Compare the transaction details against the criteria in `DISPUTE_BRIEF.md` and the customer’s claim. Determine whether the charge is:
    - **Valid** (e.g., a legitimate monthly service fee matching the amount and date cited)
    - **Duplicate** (the same charge appears more than once)
    - **Invalid** (amount, date, or service does not match any expected billing)

5.  **Update the ticket**  
    Use the standard mock ticketing update endpoint to adjust the ticket’s priority and tags according to the outcome.  
    `POST /ticketing/tickets/update` with `ticket_id = TKT-1041` and the following fields:
    - `priority`: `low` for valid charges, `high` for duplicates, `medium` for invalid/unknown discrepancies (unless the dispute brief specifies otherwise)
    - `tags`: include the appropriate resolution tag, e.g., `resolved-valid`, `resolved-duplicate`, or `resolved-invalid`

    **Important constraints:**
    - **Do not close the ticket** (`/ticketing/tickets/close` is out of scope)
    - **Do not create payments or refunds**
    - Only update the fields listed above (priority, tags). The ticket description and other fields must remain unchanged.

### Final Answer

After completing the update, your final answer should summarise the triage outcome (e.g., “Charge valid – ticket lowered to low priority and tagged resolved-valid”) and confirm that the ticket has been updated without being closed.