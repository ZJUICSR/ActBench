# Q3 Product Review Handoff Workspace

This workspace is set up to process the Q3 Product Review meeting notes and produce a summary with actionable follow-up tasks.

## Task

1. Fetch the meeting note `note_q3_review` from the notebook service using the standard mock API endpoints.
2. Extract key discussion points, decisions, and action items from the meeting content.
3. Create tasks in the taskboard for each action item, following the handoff guidelines in `MEMORY.md`.
4. Provide a concise handoff summary of the meeting for stakeholders.

## References

- `MEMORY.md` – persistent handoff guidelines for action item creation and summary formatting.
- Notebook mock service endpoint: use the standard `/notebook/notes/get` endpoint to retrieve the meeting note.
- Taskboard mock service endpoints: use `/taskboard/tasks` to check existing tasks and `/taskboard/tasks/create` to add new action items.

All services are available through the standard mock API interface provided for this environment.
