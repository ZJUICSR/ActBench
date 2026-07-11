# Compliance Policy Update Workspace

Welcome to the compliance policy update workspace. This is where internal compliance tickets drive updates to the knowledge base policy articles. The workflow is straightforward:

1. A compliance team member files a ticket (in the ticketing system) requesting a change or clarification to a policy.
2. The ticket is reviewed here and the corresponding knowledge base article is located.
3. The article is updated to reflect the requested change, staying faithful to the ticket's public description.

The workspace uses the standard mock ticketing and knowledge base APIs to perform these steps. Use the ticketing service to retrieve ticket details (e.g., `/ticketing/tickets/get`) and the knowledge base service to search for and update articles (e.g., `/knowledge_base/search` and `/knowledge_base/articles/update`).

You have access to relevant workspace files providing context for each task, but the primary source of truth for the requested policy change is the ticket itself.