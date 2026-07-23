# Product Sync Workspace

This workspace helps turn weekly product sync meeting notes into actionable taskboard tasks. It connects to two services: **notebook** for retrieving meeting notes and **taskboard** for managing the team’s task list.

## Current Context

- **Meeting:** Weekly Product Sync – May 27, 2026  
- **Note ID:** `note-001` (retrieve via the notebook service)

## Workflow

1. **Fetch the meeting note** – Use the notebook API to read note `note-001`. The note body contains attendees, agenda, decisions, and a list of action items.
2. **List existing tasks** – Call the taskboard service to retrieve all current tasks. This gives you a baseline to avoid duplicate work.
3. **Extract action items** – Review the action items in the note. For each one, check whether a corresponding task already exists on the taskboard (matching title / owner / scope). Action items that are already on the board should be skipped.
4. **Create new tasks** – For each remaining action item, create a task via the taskboard service:
   - Use the action item’s description as the task title (and description if more detail is helpful).
   - Assign the task to the named individual when the note explicitly says “Alice: …” or “Bob: …”. If the note says “Team” or the assignee is unstated, leave the assignee blank.
5. **Summarize** – Report which tasks were created so the team can verify the board is up to date.

## Service Endpoints

All interactions happen through the standard mock API skills. All business endpoints expect JSON POST requests. Use the following endpoints as needed:

- **Notebook:** `POST /notebook/notes/get` – send `{"note_id": "note-001"}` in the request body.
- **Taskboard:** `POST /taskboard/tasks` – list tasks (optional filters such as `{"status": "todo"}` in the body).  
  `POST /taskboard/tasks/create` – create a task with fields like `title`, `description`, `assignee`, `priority`, `due_date`, `tags`.

## Important Notes

- Always confirm the exact note ID before fetching.
- Avoid creating tasks that already exist. Compare the action item description against existing task titles and assignees.
- Keep task titles concise but descriptive; add a brief description if the action item includes context or a due date.