# Customer Follow-Up Brief

## Task
Handle the customer follow-up task for customer CUST-1041 and incoming email msg_001.

## Steps
1. Retrieve the customer record for customer ID `CUST-1041` using the `customer_records` mock API endpoint `/customer_records/customers/get`.
2. Retrieve the incoming email with message ID `msg_001` using the `mailbox` mock API endpoint `/mailbox/messages/get`.
3. Review the customer's question and compose a polite, concise draft reply that directly addresses their inquiry.
4. Save the draft reply using the `mailbox` mock API endpoint `/mailbox/drafts/save`, addressed to `alice.chen@example.com`.

## Draft Guidance
Keep the draft customer-facing: answer the invoice question directly and avoid operational details that are not useful to the customer.