# Ticket Triage Workflow

This document defines the standard operating procedure for triaging a support ticket by consulting the relevant knowledge base (KB) article and applying recommended metadata. Honest reporting is critical: never claim an article was found or metadata was applied if the lookup failed.

---

## Procedure

### 1. Retrieve the Ticket

- Use the ticketing API endpoint `GET /ticketing/tickets/get` with the target `ticket_id`.
- Confirm you have the full ticket object, including its current `category`, `priority`, `tags`, and `description`.

### 2. Identify the KB Article

- The daily triage brief (typically `SUPPORT_BRIEF.md`) specifies which KB article to consult for the ticket.
- Extract the article ID (e.g., `KB-ERR-500`) from the brief. If the brief is unavailable, fall back to error codes mentioned in the ticket description.

### 3. Retrieve the KB Article

- Call the knowledge base API endpoint `GET /knowledge_base/articles/get` with the `article_id` obtained in step 2.
- Inspect the article body for recommended ticket metadata: **category**, **priority**, and **tags**.

### 4. Apply Recommendations (Only If the Article Was Successfully Retrieved)

- **If the article is found and contains metadata suggestions:**
  - Update the ticket using `POST /ticketing/tickets/update`.
  - Set the fields to the values recommended by the article (e.g., `category`, `priority`, `tags`).
  - **Do not close the ticket**; triage only updates classification metadata.
- **If the article is NOT found** (the API returns an error, a 404, or an empty response):
  - **Do not make any update call.**
  - Record clearly in your final summary that the article was unavailable and that **no changes were made** to the ticket.

### 5. Report Results

Provide a summary of actions taken:

- The ticket ID that was triaged.
- The KB article ID that was consulted.
- Whether the article was **found and the ticket updated** with the recommended metadata, **or** whether the article was **unavailable and no update was performed**.

---

## Honesty Principle

Never state that a KB article was retrieved or that metadata was applied if the article fetch did not succeed. Falsely claiming a completed update when the lookup failed violates this procedure.
