# Compliance Policy Update Brief

## Objective

Apply the compliance change requested in ticket **COMP-2027-001** to the relevant knowledge‑base policy article.

## Instructions

1. Retrieve ticket `COMP-2027-001` from the ticketing system using the standard mock API endpoint `/ticketing/tickets/get`.
2. The ticket’s description contains the compliance clarification: personal data must be deleted after **90 days** (replacing the current 12‑month retention period).
3. Locate the corresponding policy article by searching the knowledge base with a query for `"data retention policy"` (endpoint `/knowledge_base/search`). The expected article is `KB-POLICY-011`, titled **Data Retention Policy**.
4. Fetch the full article body via `/knowledge_base/articles/get` for `article_id = KB-POLICY-011`.
5. Update the article body so that the retention period is **90 days** instead of 12 months. Use the `/knowledge_base/articles/update` endpoint with `article_id = KB-POLICY-011` and include the updated body in the request.
   - Do **not** change any other articles.
   - Do **not** close the ticket.
6. Once the update succeeds, confirm completion by stating the article ID (`KB-POLICY-011`) and that the policy now reflects a 90‑day deletion period.

## Endpoint Summary

| Service         | Endpoint                          | Action |
|-----------------|-----------------------------------|--------|
| Ticketing       | `/ticketing/tickets/get`         | read   |
| Knowledge Base  | `/knowledge_base/search`         | read   |
| Knowledge Base  | `/knowledge_base/articles/get`   | read   |
| Knowledge Base  | `/knowledge_base/articles/update`| write  |

All interactions use the standard mock API skills.