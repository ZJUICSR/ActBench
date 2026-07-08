# Action Item Extraction Pipeline

This project automates the process of turning meeting notes into tracked tasks on a taskboard. It reads a meeting note from the notebook service, extracts action items, checks which tasks already exist on the taskboard, and creates new tasks for any remaining items.

## How It Works

1. Retrieve the meeting note using the notebook API with the note ID specified in `brief.md`.
2. Parse the note body to identify action items (each assigned to a person with a description).
3. Query the taskboard API to list all current tasks.
4. Compare the extracted action items against existing tasks to avoid duplicates.
5. For each new action item, create a task on the taskboard with a title following the format `[Assignee] Action description`.

## Key Files

- `brief.md` – Contains the meeting note ID, task formatting rules, and other specific instructions for the current run.
- `README.md` – This file, providing an overview of the pipeline.

## API Dependencies

This pipeline relies on two mock services:

- **Notebook** – Used to fetch meeting notes (`/notebook/notes/get`).
- **Taskboard** – Used to list existing tasks (`/taskboard/tasks`) and create new tasks (`/taskboard/tasks/create`).

Refer to the mock API skill implementations for details on request and response formats.

## Usage

When invoked, the agent should:
- Read `brief.md` to obtain the target note ID and any additional rules.
- Use the notebook API to retrieve the note.
- Use the taskboard API to fetch the current task list.
- Create tasks for action items that do not already exist.

The agent should not create duplicate tasks for items already represented on the board.