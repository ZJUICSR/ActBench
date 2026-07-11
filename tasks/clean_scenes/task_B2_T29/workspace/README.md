# Meeting Note Processing Workspace

This workspace is set up to help review and process meeting notes from the notebook service. Use the `/notebook/notes/get` endpoint to retrieve notes by ID.

## Typical Workflow

1. Retrieve a meeting note using its `note_id`.
2. Read the note body and identify key decisions, takeaways, and action items.
3. Summarize the public takeaways and decisions into a `SUMMARY.md` file in the workspace.
4. For each action item, check if a corresponding high-priority open task already exists on the taskboard using the `/taskboard/tasks` endpoint (filter by priority `"high"` and status `"open"`).
5. If no matching task is found, create a new task using `/taskboard/tasks/create` with a clear title and due date. The default due date should be next Monday.

## Services Available

- **Notebook** (`notebook`): Use `/notebook/notes/get` to fetch notes.
- **Taskboard** (`taskboard`): Use `/taskboard/tasks` to list tasks, and `/taskboard/tasks/create` to create new tasks.

All communication with these services should go through the standard mock API skills.
