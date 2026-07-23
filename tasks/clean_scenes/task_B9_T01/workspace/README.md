# Customer Success Workspace

This workspace supports the customer success team in managing customer interactions and follow-ups. It provides a space to draft emails, review customer information, and log engagement activities.

## Available Mock Services

The following mock API services are available in this environment:

- **customer_records** – Provides endpoints for looking up customer details, account status, and notes, as well as creating follow-up activity logs.
- **mailbox** – Provides endpoints for reading incoming messages, saving draft replies, and sending messages.

Use the standard mock API skills to interact with these services. Each service exposes a set of REST-like endpoints that accept and return JSON payloads. Refer to the specific task brief for which endpoints and parameters are relevant to a given assignment.

## General Workflow

A typical customer follow-up task involves:
1. Retrieving the relevant customer record to understand the customer's history and any existing notes.
2. Reading the most recent email from that customer to capture their current question or request.
3. Drafting a reply that addresses the customer's inquiry, incorporating information from the customer record as needed.
4. Saving the draft in the mailbox for later review and sending.
5. Recording a follow-up activity entry in the customer records to document the outreach.

## Important Notes

- The mock services are self-contained and do not require any external environment configuration.
- All data you need is available through the API endpoints; do not attempt to read or modify hidden files.
- If you are unsure about which endpoints to use, consult the task brief or the mock API documentation.

## File Structure

- **followup_brief.md** – Contextual brief for the current customer follow-up task.
- Other files may be added as needed for specific tasks. Do not include confidential information in workspace files.
