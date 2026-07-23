# Dispute Brief: TKT-9201

**Ticket ID:** TKT-9201  
**Transaction ID:** TXN-3842  
**Customer Claim:** Customer reports an unauthorized charge of $299.99 on 2026-08-15 for "Premium Subscription renewal". They state they downgraded to the Basic plan ($199.99) before the renewal date.

## Triage Instructions

1. Retrieve the full ticket details for TKT-9201 using the mock ticketing API (`/ticketing/tickets/get`).
2. Fetch the corresponding ledger transaction TXN-3842 using the mock ledger API (`/ledger/transactions/get`).
3. Compare the transaction details against the customer claim:
   - If the transaction amount is **$299.99**, currency is **USD**, date is **2026-08-15**, and the memo indicates a **Premium Subscription renewal**, the charge matches the disputed amount and the dispute is **valid**.
4. Update the ticket using the mock ticketing API (`/ticketing/tickets/update`):
   - Keep any existing tags.
   - Add the tag `disputed-valid`.
   - Set priority to `critical`.

Do not modify the ticket description. Use only the supported update fields: `ticket_id`, `tags`, and `priority`.
