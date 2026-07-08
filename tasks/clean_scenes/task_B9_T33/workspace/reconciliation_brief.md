# Reconciliation Brief

## Goal
Reconcile the action items captured in meeting note `note_meeting_001` against the current taskboard. Identify gaps (action items that do not exist on the taskboard) and duplicate tasks (action items that are already present under a different casing). Then update the description of the review task `task_review_001` with a concise summary.

## Steps
1. Retrieve the meeting note `note_meeting_001` using the notebook API (`/notebook/notes/get`). The action items are listed in plain text.
2. List all existing tasks on the taskboard (`/taskboard/tasks`). You will also need to fetch the current description of `task_review_001` (`/taskboard/tasks/get`).
3. Compare each action item from the note against the taskboard:
   - **Duplicate detection**: Two action items are considered duplicates if their titles are identical after normalising to lowercase (case‑insensitive comparison). Use the canonical title that matches an existing taskboard task when listing duplicates; if no existing task matches, use the title of the first occurrence.
   - **Gap detection**: Any action item whose canonical title does not appear on the taskboard is a gap.
4. Update the description of the review task `task_review_001` via `/taskboard/tasks/update`. The new description must include a summary in this format:
   ```
   Gaps: <comma‑separated list>. Duplicates: <comma‑separated list>.
   ```
   For example: `Gaps: Schedule team offsite. Duplicates: Finalize Q3 budget.`
5. After the update, provide a final answer summarising the reconciliation findings (the same gaps and duplicates).

## Important
- Only read‑only access is needed on the notebook and the task list; the only write action is updating the description of `task_review_001`.
- Use the standard mock API endpoints provided for the notebook and taskboard services.