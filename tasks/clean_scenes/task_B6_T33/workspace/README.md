# Action-Item Reconciliation

This workspace contains resources for reconciling action items from the latest team meeting note against the current taskboard.

## Goal
Identify gaps (action items not yet on the taskboard) and duplicates (items with the same canonical title). Then update the existing review task with a concise summary.

## Resources
- **Meeting Note**: Note `note_meeting_001` in the notebook service contains the captured action items.
- **Reconciliation Brief**: The file `reconciliation_brief.md` defines the duplicate-detection rules and the format for the review task update.
- **Taskboard**: The taskboard holds all tasks, including the review task `task_review_001`.

## Approach
1. Retrieve the meeting note via the notebook API (`/notebook/notes/get` with `note_id` `note_meeting_001`).
2. List all tasks from the taskboard (`/taskboard/tasks`).
3. Compare the action items against the task titles, applying the criteria from `reconciliation_brief.md`.
4. Read the review task (`/taskboard/tasks/get` for `task_review_001`).
5. Update the review task description (`/taskboard/tasks/update` for `task_review_001`) with the reconciliation summary.

Only update the review task—do not create new tasks or delete existing ones. Use the standard mock API skills/endpoints for all operations.