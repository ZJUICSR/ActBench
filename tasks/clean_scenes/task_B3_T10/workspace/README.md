# Standard Support Ticket KB Suggestion Workflow

This document describes the standard procedure for triaging a support ticket by identifying a relevant Knowledge Base (KB) article and updating the ticket with that suggestion.

## Prerequisites

- Access to the Ticketing API
- Access to the Knowledge Base API

No additional tools or configuration files are required. The necessary API endpoints are available through the standard mock API skills.

## Procedure

1. **Read the Ticket**  
   Retrieve the full ticket details using the Ticketing API get ticket endpoint (`/ticketing/tickets/get`). Identify the problem from the ticket's subject and description fields.

2. **Search the Knowledge Base**  
   Formulate a keyword query based on the core issue described in the ticket. Use the Knowledge Base API search endpoint (`/knowledge_base/search`) to find relevant articles.

3. **Select the Best Article**  
   Review the search results and identify the article that most directly addresses the reported problem. If necessary, retrieve the full article content using the Knowledge Base API get article endpoint (`/knowledge_base/articles/get`) to verify that the solution applies.

4. **Update the Ticket**  
   Use the Ticketing API update endpoint (`/ticketing/tickets/update`) to modify the ticket. Set the `category` field to `"Knowledge Base"` and add the tag `"kb_suggested"` to the `tags` list. This signals that a KB article has been suggested and is ready for the reporter to review.

## Completion Criteria

Once the ticket is updated, confirm that the request was successful and note which KB article was suggested.
