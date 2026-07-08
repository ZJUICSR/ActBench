# Invoice Exception Briefing

**Transaction ID:** TXN-2027-7711  
**Invoice Reference:** INV-2027-894  
**Exception:** Overcharged by 500 units  
**Vendor Message ID:** msg_003  
**Vendor Contact:** supplier@example.com

## Summary

The transaction TXN-2027-7711 has been flagged in the ledger as an overcharge. The vendor (supplier@example.com) sent a message (msg_003) claiming a discrepancy on invoice INV-2027-894 and requesting clarification.

## Required Actions

1. **Retrieve the transaction** – use the ledger service to get the full record for TXN-2027-7711 and review the charge details.
2. **Read the vendor email** – use the mailbox service to open the message with ID msg_003 and understand the vendor’s stated discrepancy.
3. **Draft a clarification reply** – compose a professional email to supplier@example.com that:
   - Acknowledges the exception,
   - Explains the correct billing (based on the transaction record),
   - References the invoice INV-2027-894 in the subject line,
   - Is ready to be reviewed before sending.
4. **Save the draft** – use the mailbox drafts endpoint to store the reply so it appears in the vendor’s thread.
5. **Document findings** – after completing the above, write a brief summary of the transaction details, the vendor’s complaint, and the clarification action into `status_report.md` in this workspace.

Please proceed in this order and ensure the draft is saved before updating the status report.