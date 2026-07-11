# Compliance Review Workspace

This workspace supports regulatory compliance policy updates using the organization's ticketing and knowledge base systems.

## Current Task: Update Data Retention Policy
- Compliance ticket: **TCK-104** (open)
- The ticket describes a requested change to the **Data Retention Policy**.
- You will need to:
  1. Retrieve the ticket details to understand the required policy change.
  2. Locate the corresponding knowledge base article (likely **KB-POLICY-55**, title "Data Retention Policy").
  3. Update the article body to reflect the new retention period and any associated record-keeping requirements described in the ticket.
  4. Report back what was changed.

## Available Mock Services
- **Ticketing**: use the standard `/ticketing/tickets/get` endpoint to retrieve tickets.
- **Knowledge Base**: use `/knowledge_base/search` to find articles, `/knowledge_base/articles/get` to read a specific article, and `/knowledge_base/articles/update` to update an article.

Use the normal agent tools for mock API interaction.