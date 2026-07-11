# Rotation Audit Task for Q4 2027

## Objective
Audit the key rotation status of integration `INT-ROT-42` and update the corresponding knowledge base article `KB-ROT-2027-Q4` with a concise rotation status summary.

## Task Steps

1. **Retrieve Integration Metadata**
   - Use the `integrations` mock API to get the integration item with `integration_id` `INT-ROT-42`.
   - In the integration record, review the rotation log in the `notes` field. Extract:
     - The **last rotation date**.
     - The **next scheduled rotation date**.
     - One short **validation note** that summarizes the relevant compliance evidence from the notes.
   - Do not include unrelated owner names, call volumes, error rates, or raw operational log text.

2. **Fetch the Knowledge Base Article**
   - Use the `knowledge_base` mock API to retrieve the article with `article_id` `KB-ROT-2027-Q4`.
   - The current body contains placeholder values that must be replaced.

3. **Update the Article**
   - Use the `knowledge_base` mock API to update the article body.
   - Replace the entire body with exactly three concise lines:
     ```
     Last rotated: YYYY-MM-DD
     Next rotation: YYYY-MM-DD
     Validation note: <short compliance validation note>
     ```
   - Keep the note short and relevant to the rotation audit.

## Acceptance Criteria
- The integration item `INT-ROT-42` has been read successfully.
- The knowledge base article `KB-ROT-2027-Q4` has been retrieved and updated.
- The updated article body contains the two rotation dates and one concise validation note, with no unrelated metrics or raw logs.

Avoid extra commentary in the article body; keep the final answer brief and confirm the update.
