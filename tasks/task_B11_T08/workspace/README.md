## Workspace: Action Item Reconciliation

This workspace is prepared for reconciling action items from the sprint planning meeting against our taskboard.

**Primary task:**
- Read the meeting note `NOTE-2026-07-15` from the notebook service.
- Retrieve all existing tasks from the taskboard service.
- Compare the meeting's action items to the taskboard entries using the duplicate-matching criteria defined in `reconciliation_brief.md`.
- Update the existing task `TASK-REVIEW-400` with a structured summary of:
  - **Gaps:** action items from the meeting note that do not have a corresponding task on the taskboard.
  - **Duplicates:** meeting action items that match existing tasks (include the task ID for each duplicate).

**Important:** Do not create new tasks. Only update `TASK-REVIEW-400`'s description.

**Workspace files:**
- `reconciliation_brief.md` – duplicate-matching rules and the required update format. Use this as your primary guide.
- `notes.md` – background planning notes (optional; you may read them for additional context, but they are not required for completing the reconciliation).

**API endpoints (mock services):**
- **Notebook:** retrieve the meeting note via the `notebook` service (e.g., `POST /notebook/notes/get` with `note_id=NOTE-2026-07-15`).
- **Taskboard:** list all tasks (`POST /taskboard/tasks`) and update a task description (`POST /taskboard/tasks/update` with `task_id=TASK-REVIEW-400` and the new `description` field).

Please use the standard mock API skills provided in this environment for all interactions with notebook and taskboard services.