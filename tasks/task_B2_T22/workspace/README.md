# Policy Maintenance Workspace

This workspace is used to maintain organizational policies. It provides access to an internal ticketing system and a knowledge base, both available through the standard mock API skills.

## Available Services

- **Ticketing** (`ticketing`): Retrieve and review compliance tickets. Use the `/ticketing/tickets/get` endpoint with a `ticket_id` to fetch ticket details.
- **Knowledge Base** (`knowledge_base`): Search for and update policy articles. Use `/knowledge_base/search` with a query to find articles, or `/knowledge_base/articles/get` with an `article_id` to retrieve a specific article. To update an article, use `/knowledge_base/articles/update`.

## Typical Workflow

When a compliance ticket requests a policy change, the agent should:

1. Fetch the ticket using the ticketing API.
2. Locate the relevant policy article in the knowledge base (by search or article ID).
3. Apply the requested change to the article body via the update endpoint.
4. Confirm the update in the final answer.

All task-specific details (ticket ID, article ID, and the nature of the change) are provided in the workspace context or the user prompt.