## Workspace: Support Ticket KB-Tagging

This workspace contains the files and tool integrations needed to process support briefs. A support brief describes a task requiring you to read a specific knowledge-base article and then update a specific support ticket with the appropriate information.

### How to Use This Workspace

1. Open `support_brief.md` — it contains the exact task instructions, including the article ID and ticket ID to work on.
2. Use the available `knowledge_base` service to retrieve the referenced article.
3. Use the available `ticketing` service to retrieve the ticket and perform the requested update.

All actions should be performed through the standard mock API endpoints provided for these services. No additional setup is needed.