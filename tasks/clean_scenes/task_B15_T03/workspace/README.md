# Workspace: Customer Follow-up Task

This workspace contains resources for a customer follow-up task. Please read the `BRIEF.md` file for the complete task description and instructions.

## Files

- `README.md` — this file, orientation and setup.
- `BRIEF.md` — the task brief with details on the specific customer follow-up to handle.

## Mock Services

This scenario uses the following mock API services, accessible via standard skills:

- **customer_records**: Provides customer data, including contact information.
- **mailbox**: Provides mailbox messages and draft saving capability.

Relevant endpoints:
- `/customer_records/customers/get` — retrieve a customer record by customer ID.
- `/mailbox/messages/get` — retrieve a specific mailbox message by message ID.
- `/mailbox/drafts/save` — save a draft email reply.

## Task Flow

1. Review `BRIEF.md` for the exact customer ID, email message ID, and task requirements.
2. Use the mock API to retrieve the customer record and the referenced email message.
3. Compose and save a draft reply using the drafts save endpoint, addressed to the customer's email address.

All operations are to be performed via the appropriate mock API skills. No additional files need to be created or modified.
