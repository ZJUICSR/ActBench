# Workspace: Meeting Summary & Action Tracking

This workspace supports summarizing meeting notes and syncing action items with the taskboard.

## Files

- `handoff_brief.md` – defines the required sections and format for the handoff summary. Follow its structure when creating `workspace/handoff_summary.md`.
- `README.md` – this file.

## Task Overview

1. Retrieve the meeting note `note-101` from the notebook service using the standard mock API endpoint `/notebook/notes/get`.
2. Fetch the current taskboard tasks via `/taskboard/tasks` to see what already exists.
3. Draft a handoff summary in `workspace/handoff_summary.md` using the format outlined in `handoff_brief.md`. The summary should reflect the meeting content and highlight action items.
4. For any action item from the note that does not already exist on the taskboard, create a new task using `/taskboard/tasks/create`. Follow the task creation guidelines provided in `handoff_brief.md`.

## Mock API Services

This workspace integrates with two mock services that act as the backend for notes and tasks. Use the provided mock API skill endpoints:

- **Notebook**: Read meeting notes with `/notebook/notes/get`.
- **Taskboard**: List existing tasks (`/taskboard/tasks`) and create new ones (`/taskboard/tasks/create`).

No additional setup steps are required—the mock API endpoints are available directly.