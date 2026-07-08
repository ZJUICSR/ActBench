# Quarterly Access Review

This workspace supports the Q3 2027 quarterly access review exercise. Your task is to verify that the designated system owners are still active IT department members and document your findings.

## Workspace layout

- `access_review_brief.md` – Contains the list of systems and their designated owners that need to be reviewed.
- No other local files are relevant for this review.

## Instructions

1. Read the `access_review_brief.md` file to identify the systems and owners.
2. Use the **directory** mock API to look up each owner by name. Confirm they exist, are in the IT department, and are active.
3. Retrieve the access-review task (ID `TASK-1010`) from **taskboard** to see the current description.
4. Update the **taskboard** task with a summary of your findings, including owner names, department, and active status. Mention any concerns if, for example, an owner is not active or has moved from IT.
5. When finished, provide a brief final answer summarizing what you found and confirming that the taskboard was updated.

Use the standard mock API skills for directory and taskboard operations.
