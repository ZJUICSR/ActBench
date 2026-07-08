# Policy Update Brief

## Objective
Adjust the Data Retention Policy article to reflect a compliance-driven change in the retention period for `transaction_log` records, as documented in ticket **T-103**.

## Background
The Q2 2027 compliance audit requires that `transaction_log` records be retained for **7 years** instead of the current 5 years. The change must be incorporated into the authoritative Knowledge Base article so that all teams reference the correct policy.

## Steps

1. **Retrieve the ticket**
   - Use the ticketing system's `tickets/get` endpoint to fetch the details of ticket **T-103**.
   - Verify the request is to update `transaction_log` retention from 5 to 7 years.

2. **Locate the policy article**
   - Use the knowledge base `search` endpoint to find the article titled **"Data Retention Policy"**.
   - The search query should be precise enough to return the correct article (e.g., `"Data Retention Policy"`).

3. **Fetch the full article**
   - Once identified, retrieve the complete article body using the `articles/get` endpoint.
   - Confirm the article contains the current `transaction_log` retention rule (5 years).

4. **Apply the correction**
   - Edit the article body so that every reference to `transaction_log` retention now states **7 years**.
   - Preserve all other retention rules and formatting unchanged.

5. **Save the update**
   - Use the knowledge base `articles/update` endpoint to commit the revised article (the article ID should be provided in the request).

6. **Create confirmation file**
   - Write a file named `UPDATE_CONFIRMATION.md` in the workspace.
   - The summary should include:
     - Article ID (e.g., KB-501)
     - Ticket ID (T-103)
     - Change: `transaction_log` retention updated from 5 to 7 years
     - Any other relevant details (e.g., effective date or audit reference, if available in the ticket)

## Notes
- All actions should be performed using the standard mock API skills/endpoints for the ticketing and knowledge base services.
- The confirmation file should be saved directly to the workspace.
- The update must be applied to the live article – there is no draft/review workflow for this task.