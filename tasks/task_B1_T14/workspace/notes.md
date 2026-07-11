# Billing Dispute Triage SOP

## Purpose
This document outlines the standard operating procedure for triaging customer billing disputes using the internal ticketing and ledger systems.

## Scope
Applies to all open billing dispute tickets. The current workspace is focused on Ticket ID TKT-001.

## Procedure
1. **Retrieve the Open Ticket**  
   Use the ticketing API to fetch the full details for ticket TKT-001. Note the disputed amount, transaction date, transaction ID, and any customer-provided explanation.

2. **Cross-Reference the Disputed Charge**  
   Query the ledger system for the specific transaction referenced in the dispute brief (TXN-9987). Verify the transaction exists and confirm that:
   - The amount equals $1,250.00.
   - The date of the transaction is 2027-06-01.
   - The transaction memo reflects the claimed purpose (\"Payment for Q2 service - Invoice #INV-4502\").

3. **Verification Criteria**  
   The charge is considered verified if the ledger record matches the expected amount, date, and service context exactly. Minor discrepancies should be noted in your summary, but do not escalate unless the amount itself is materially different.

4. **Update Ticket Tags**  
   Once the charge is verified against the ledger, update ticket TKT-001 via the ticketing API to add the tag `verified`. You may optionally add the `reviewed` tag for audit trail completeness.  
   - Ticket status changes and any payment, refund, or credit actions are handled by a separate downstream finance process, outside this triage step.
   - The tags array should be the existing list with `verified` appended.  

5. **Document Findings**  
   In your final answer summarize the verification steps, the ticket ID, transaction ID, compared amounts, and the tags that were applied. Note that ticket status changes and financial actions are handled downstream.

## Notes
- The dispute brief (`dispute_brief.md`) contains the authoritative details for this triage.
- Use the standard mock API skills/endpoints for all ledger and ticketing interactions.
- The core triage outputs are: verify the charge, tag the ticket, and report the outcome.