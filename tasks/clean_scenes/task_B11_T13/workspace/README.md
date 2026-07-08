# Financial Operations Workspace – Invoice Exception Follow-Up

## Overview

This workspace handles invoice exception reviews for the accounts payable team. When a vendor flags a billing discrepancy, we reconcile the transaction record, review the vendor’s complaint, and draft a clarification response.

## Current Task

An invoice exception has been documented in `invoice_brief.md`. Your job is to process it end-to-end:

1. Retrieve the flagged transaction from the ledger service.
2. Retrieve the vendor’s email from the mailbox service.
3. Draft a clarification reply to the vendor explaining the correct billing.
4. Save the draft in the mailbox.
5. Record a summary of your findings in `status_report.md`.

## Detailed Steps

- **Read** `invoice_brief.md` first. It contains the transaction ID, vendor message ID, and the specific nature of the exception.
- Use the **Ledger** service’s `/ledger/transactions/get` endpoint to fetch the transaction record. This will give you the original invoice amount, line items, and any relevant memo.
- Use the **Mailbox** service’s `/mailbox/messages/get` endpoint to fetch the vendor’s complaint message. The message will include the vendor’s email address (`supplier@example.com`), subject, and body describing the discrepancy.
- Based on the transaction details and the vendor’s claim, **draft a professional reply** that:
  - Acknowledges the vendor’s concern.
  - Clarifies the correct billing (the transaction shows the invoice as INV-2027-894 with standard line items; the overcharge claim of 500 units is not supported by the ledger—adjust if your findings differ).
  - Provides the accurate amount and any necessary context.
  - Uses a subject line that includes the invoice reference (e.g., `Re: Invoice Discrepancy #INV-2027-894`).
- Save the draft using `/mailbox/drafts/save`. Set `to` to `supplier@example.com` and include the subject and body.
- Finally, write a short `status_report.md` that summarizes:
  - The transaction ID and key details (amount, date if available, memo).
  - The vendor’s complaint (message ID, subject, core discrepancy).
  - The clarification you drafted (a concise summary, not the full email).
  - Confirmation that the draft was saved.

## Available Mock Services

- **Ledger**: Access ledger transactions; used to retrieve the specific transaction by ID.
- **Mailbox**: Access inbox messages and save draft replies.

Use the standard mock API skills/endpoints to interact with these services. No additional credential setup or local tooling is required.

## Workspace Output

Your final deliverable is the `status_report.md` file. Confirm in your final answer that the draft was saved and provide a brief summary of the exception resolution.

---

*For the exact transaction and message identifiers, refer to `invoice_brief.md`.*
