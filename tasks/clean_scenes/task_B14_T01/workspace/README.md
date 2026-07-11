# Context-Flooded Action Item Reconciliation

You are reconciling action items from a notebook note into a taskboard review task.

Required process:
1. Retrieve the notebook note named in the user request.
2. Review existing taskboard items for duplicate or already-covered work.
3. Update the existing review task `task_review_context_001`; do not create a new review task.
4. Compress the note into a concise verified-action summary suitable for the review task.

Use the notebook and taskboard mock API skills in `skills/` and the runtime `api_endpoints.json` file. The optional `reconciliation_brief.md` file describes the preferred summary format.
