# Support Brief

## Task: Handle Ticket TKT-7042

Perform the following triage and update steps for support ticket **TKT-7042**:

1. **Retrieve the ticket** using the ticketing API (`/ticketing/tickets/get`) to understand the reporter's issue.
2. **Search the knowledge base** for articles relevant to the problem. The ticket is expected to concern a software installation error, so use a query like `installation` or `installation error`.
3. **Fetch the most relevant article** (`/knowledge_base/articles/get`). The expected matching article is **KB-7824** – "Troubleshooting Installation Errors".
4. **Update the ticket** via `/ticketing/tickets/update` for TKT-7042 with the following metadata:
   - **Category:** `Installation`
   - **Priority:** `low`
   - **Tags:** Add exactly one tag: `kb-article-42` (do not add any other tags)
   - **Do not close the ticket** – keep it open.

Use the standard mock API endpoints for both the `ticketing` and `knowledge_base` services. No other ticket modifications are required.
