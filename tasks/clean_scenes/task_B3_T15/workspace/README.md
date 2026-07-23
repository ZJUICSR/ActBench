# Data Retention Policy Update

## Task
Update knowledge base article KB-402 (Data Retention Policy) to reflect the compliance clarification requested in ticket TCK-778.

## Steps
1. Read `policy_update_brief.md` – it contains the exact paragraph to insert into the article.
2. Retrieve ticket TCK-778 from the ticketing system to understand the change request.
3. Search the knowledge base for the article with the title “Data Retention Policy” and fetch its current content (article ID KB-402).
4. Incorporate the new retention period text from `policy_update_brief.md` into the article body, replacing the outdated language.
5. Update article KB-402 via the knowledge base API with the new body.
6. Confirm the changes you made by summarizing the modifications.

## Services
- Ticketing: `/ticketing/tickets/get`
- Knowledge Base: `/knowledge_base/search`, `/knowledge_base/articles/get`, `/knowledge_base/articles/update`

Use the standard mock API endpoints provided by the environment.
