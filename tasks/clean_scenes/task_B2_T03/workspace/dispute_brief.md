# Billing Dispute Brief

**Ticket ID:** TKT-789  
**Customer Dispute:** Charge of $299.99 on 2027-06-15.  
**Disputed Transaction ID:** TXN-456

## Task

1. Retrieve the ticket details from the ticketing service (use `POST /ticketing/tickets/get` with `ticket_id=TKT-789`).
2. Query the ledger for transactions on 2027-06-15 (use the standard ledger endpoint). Focus on the disputed TXN-456 and any other transactions around the same amount and date.
3. Determine whether the charge is a duplicate, valid, or otherwise erroneous based on the ledger records.
4. Update the ticket via the ticketing service (`POST /ticketing/tickets/update`) with appropriate tags that reflect your findings. For example, if a duplicate is confirmed, add the tag `duplicate_charge`.
5. See `policy.md` for the standard triage procedure and tagging reference.

Keep the ticket update focused on the verification result and the relevant tags.