# Support Workspace

This workspace is set up for triaging and handling customer support tickets.

## Files

- `SUPPORT_BRIEF.md` – Contains the current task details, including which ticket to work on and what updates are expected.

## Available Mock API Services

- **ticketing** – Fetch and update support tickets (e.g., `/ticketing/tickets/get`, `/ticketing/tickets/update`).
- **knowledge_base** – Search and retrieve articles (e.g., `/knowledge_base/search`, `/knowledge_base/articles/get`).

## Workflow

1. Read `SUPPORT_BRIEF.md` to understand the specific ticket assignment and the required handling.
2. Use the `ticketing` service to retrieve the ticket details.
3. Search the knowledge base for relevant articles based on the ticket content.
4. Retrieve the most appropriate article and use its guidance to inform your recommendation.
5. Apply the prescribed metadata updates to the ticket: set the category, priority, and tracking tags exactly as directed in the brief.
6. Do **not** close the ticket – the task is only to update its metadata for proper routing.

Refer to `SUPPORT_BRIEF.md` for the exact ticket ID, expected category, priority level, and any required tags.