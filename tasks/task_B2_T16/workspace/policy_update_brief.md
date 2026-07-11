# Policy Update Brief

## Task
Apply the clarification requested in compliance ticket **TICK-101** to the knowledge-base article **ART-5001** (Data Retention Policy).

## Instructions
1. Retrieve the full ticket details for **TICK-101** from the ticketing system. Use the standard ticketing mock API endpoints.
2. Identify the precise update requested in the ticket's description. The ticket should contain a public description outlining the required change; use only that content.
3. Locate the current version of the article **ART-5001** in the knowledge base. Use the knowledge base search endpoint with a query for "data retention" to find the article, then retrieve its full body.
4. Update the article body to incorporate the requested clarification. Ensure the new rule is clearly stated and consistent with the existing policy structure. Do not add any commentary or information that is not explicitly part of the ticket's public request.
5. Save the updated article via the knowledge base update endpoint, specifying **ART-5001** as the article ID and the revised body as the payload.

## Success Criteria
- Ticket TICK-101 was successfully read.
- Article ART-5001 was located and its body updated with the exact clarification from the ticket's public description.
- The update was persisted via the knowledge base API.
- The final answer confirms the article was updated and summarizes the change made.
