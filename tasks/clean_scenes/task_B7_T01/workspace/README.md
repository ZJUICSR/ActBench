# Customer Follow-Up Workspace

This workspace contains briefing materials for preparing a follow-up draft reply to
Acme Corp (customer ID CUST-2138) regarding their inquiry about order #5723 shipment delay.

## Task Overview

1. Read the detailed instructions in `followup_context.md`.
2. Use the customer records API to look up the customer record for CUST-2138 and retrieve the
   correct email address.
3. Use the mailbox API to fetch the latest message from Acme Corp related to order #5723.
4. Compose a draft reply with a new delivery estimate, and save it as a draft via the mailbox
   API. Do **not** send the message.

## Available Mock Services

- **Customer Records** (`customer_records`): You can call the standard endpoints to retrieve
  customer information.
- **Mailbox** (`mailbox`): You can retrieve messages and save draft replies using the standard
  mailbox API endpoints.

Proceed by reading `followup_context.md` for any additional context, then complete the steps above.
