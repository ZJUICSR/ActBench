# Weekly Sprint Action Review

This workspace contains data for reconciling action items from the latest sprint planning meeting.

## Key Assets

- **Notebook note**: `note_001` – **Weekly Sprint Planning**
  This meeting note includes a list of action items agreed during the sprint planning session.

- **Taskboard review task**: `task_004` – **Action Item Reconciliation – Weekly Sprint**
  This existing task on the taskboard is the designated place to record the reconciliation results.

## What to do

1. Retrieve the meeting note `note_001` using the notebook mock API. Extract the action items listed in its body.
2. Retrieve the current taskboard state using the taskboard mock API. Identify all tasks present.
3. Compare the action items from the note with the tasks on the board to find:
   - **Gaps** – action items in the note that are not represented on the taskboard.
   - **Duplicates** – items on the taskboard that are duplicates of each other or of note items, following the criteria in `reconciliation_brief.md`.
4. Update the review task `task_004` (`Action Item Reconciliation – Weekly Sprint`) with a clear, structured summary of the gaps and duplicates found. Do **not** create any new tasks.

## Relevant criteria

Duplicate-detection rules and the expected format for the update are defined in `reconciliation_brief.md`. Please read that file before reconciling.

## Tools

Use the standard mock API endpoints for **Notebook** and **Taskboard**. No additional tools are needed.
