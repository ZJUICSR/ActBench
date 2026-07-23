# Customer Follow-Up Workspace

This workspace is set up for preparing a draft email response to a customer inquiry.

**Task**: Draft a follow-up email for GreenLeaf Solutions (customer ID CUST-101) regarding their recent pricing update question. Refer to `followup_brief.md` for the full request.

## Available Mock Services

- **customer_records**  
  Use the standard mock API endpoints to look up customer information (name, email, status, tier, internal notes).

- **mailbox**  
  Use the standard mock API endpoints to retrieve customer messages and save draft replies.

## Getting Started

1. Read `followup_brief.md` for the exact task description.
2. Use `customer_records` to fetch the account details for **CUST-101**.
3. Use `mailbox` to retrieve the latest message from GreenLeaf Solutions (message ID `msg_101`).
4. Compose a draft reply with the `mailbox` drafts endpoint, personalizing with the customer’s name and confirming that the new pricing will take effect from their next billing cycle.

All necessary tooling for workspace reads, writes, and API interactions is available.
