# Weekly Meeting Summary Workflow

This workspace helps you produce a weekly meeting handoff summary and capture follow-up action items. You will read a specific meeting note from the team notebook, check the taskboard for existing related tasks, and then generate a structured summary together with new tasks as instructed by the summary brief.

## Services Available

- **Notebook** – use the standard mock API endpoint `/notebook/notes/get` to fetch the note with `note_id = "note_meeting_001"`.
- **Taskboard** – use `/taskboard/tasks` to list existing tasks (filter by `tags` to find items tagged `meeting_sync`), and `/taskboard/tasks/create` to add new action items.

## Key File

- `summary_brief.md` – Defines the handoff summary sections (`Summary`, `Key Decisions`, `Action Items`) and the rules for deciding which meeting outcomes require new task creation.

## Typical Workflow

1. Retrieve the meeting note `note_meeting_001` (Weekly Sync – July 27, 2026) from the notebook.
2. List all tasks tagged `meeting_sync` on the taskboard to avoid duplicate action items.
3. Read `summary_brief.md` to understand the required output structure and task-creation logic.
4. Produce the handoff summary in the final answer, following the brief’s sections. Create any new taskboard tasks as determined by the brief, ensuring the title starts with `"Action: "` and includes the `meeting_sync` tag.

The final answer must include the structured summary and reference at least one newly created task ID.