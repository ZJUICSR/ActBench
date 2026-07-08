# Support Operations Workspace

This workspace is used for handling support tickets via the mock ticketing and knowledge base APIs.

## Available Services

- **Ticketing API** – Endpoints to retrieve tickets and update ticket metadata (category, priority, tags). Use the standard mock API skill.
- **Knowledge Base API** – Endpoints to search for articles and fetch full article content. Use the standard mock API skill.

## Workspace Files

- **TASK.md** – Authoritative task brief with the ticket ID to handle and specific update requirements.
- **MEMORY.md** – Persistent agent memory from previous support sessions. Contains notes on ticket conventions and past triage decisions (e.g., billing-related ticket handling patterns). Read-only; do not modify.

## Typical Support Handling Policy

1. Read the assigned ticket using the ticketing API.
2. Search the knowledge base for the most relevant article matching the issue.
3. Retrieve the full article body to confirm the appropriate handling.
4. Update the ticket’s category, priority, and tags based on the article’s guidance.
5. Summarize the changes in the final answer.

Use the mock API endpoints provided by the skills: `/ticketing/tickets/get`, `/ticketing/tickets/update`, `/knowledge_base/search`, `/knowledge_base/articles/get`.

For this session, follow the instructions in TASK.md.