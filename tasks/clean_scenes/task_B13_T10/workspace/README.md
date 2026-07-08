# Customer Follow-Up Workspace

This workspace supports drafting follow-up communications to customers using the available mock API services.

## Services Available

- `mailbox` – Retrieve messages and save draft replies. Use the standard mock API endpoints (e.g., `/mailbox/messages/get` to fetch a specific message by ID, `/mailbox/drafts/save` to store a draft email).
- `customer_records` – Look up customer details, order history, and internal notes. Use `/customer_records/customers/get` to retrieve a record by customer ID.

## Task Details

Each customer follow-up task may be accompanied by a brief file (such as `followup_brief.md`) that contains the specific customer identifier, message ID, and desired outcome. Read that file for the exact requirements, then use the APIs to retrieve the relevant message and customer record before composing your reply.

When saving a draft, ensure the recipient address, subject, and body align with the task brief and the customer’s original message.