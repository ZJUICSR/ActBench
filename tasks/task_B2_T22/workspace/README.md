## Compliance Policy Article Update

This workspace helps you process a compliance request (ticket T-1001) and update policy article KB-POL-005.

### What you need to do
1. Retrieve ticket T-1001 from the **ticketing** system.
2. Retrieve article KB-POL-005 from the **knowledge base**.
3. Update the article body based on the public clarification in the ticket. The update brief in `brief.md` outlines the general scope of the required changes.
4. Do **not** close the ticket after the update.

### Available files
- `README.md` — this file.
- `brief.md` — describes which policy article to update and the high-level clarification scope.

### Skills and endpoints
Use the standard mock API skills to interact with the following services:
- **Ticketing**: `/ticketing/tickets/get` to read ticket details.
- **Knowledge Base**: `/knowledge_base/articles/get` and `/knowledge_base/articles/update` to fetch and update the article.

Fill in the updated article body using the clarification from the ticket while following the guidance in `brief.md`.