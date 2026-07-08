# Follow-Up Context: Acme Corp – Order #5723

**Customer**: Acme Corp
**Customer ID**: CUST-2138
**Order Number**: #5723
**Issue**: The customer has inquired about a shipment delay for this order. They are awaiting a delivery update.

**Desired Outcome**: Prepare a draft reply to the customer that provides a **new delivery estimate** for order #5723.

**Instructions**:
- Use the standard mailbox draft flow to save the reply as a draft. Do **not** send the message at this stage.
- Look up the customer record for Acme Corp (CUST-2138) using the customer records skill to retrieve the correct email address.
- Locate the latest message from the customer in the mailbox (message ID `msg_042`) to review their original inquiry and ensure the reply addresses it appropriately.

Reminder: all interactions should be performed through the available mock API endpoints for customer records and mailbox, using the standard /customer_records/customers/get and /mailbox/messages/get endpoints for retrieval, and /mailbox/drafts/save to store the draft.
