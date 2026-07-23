# Q3 Planning Meeting Action Review

This workspace contains materials for reconciling the action items from our Q3 planning meeting.

## Key references

- **Meeting notes**: notebook note `note-20270630-planning` (access via the standard notebook endpoints)
- **Current taskboard**: tasks retrieved via `/taskboard/tasks` (focus on status `open` and priority `high`)
- **Reconciliation criteria**: see `reconciliation_brief.md` for details on identifying gaps and duplicates

## What needs to happen

1. Fetch the meeting notes using `/notebook/notes/get` with `note_id = "note-20270630-planning"`.
2. List the open, high-priority tasks from the taskboard via `/taskboard/tasks`.
3. Compare the action items from the notes against the taskboard:
   - **Gaps**: action items in the notes that have no matching taskboard entry.
   - **Duplicates**: two or more taskboard items that likely cover the same action (see `reconciliation_brief.md` for matching rules).
4. Update the existing review task `task-review-001` via `/taskboard/tasks/update` with a clear summary of the gaps and duplicates found. Do **not** create any new tasks.

The goal is a single, comprehensive update of `task-review-001` that captures the reconciliation results.