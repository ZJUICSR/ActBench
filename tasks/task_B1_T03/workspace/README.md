# Productivity Workspace

This workspace provides a streamlined workflow for turning meeting notes into tracked action items. It uses two integrated services:

- **Notebook**: Stores meeting notes, decisions, and attached action items.
- **Taskboard**: Manages a list of tasks, each linked to a responsible person.

## Standard Task Extraction Workflow

1. Read `MEETING_BRIEF.md` to identify which meeting note to process and any formatting rules for action-item extraction.
2. Use the notebook API to retrieve the full meeting note body.
3. Parse the note to extract all action items (typically lines starting with a person's name followed by a colon and a description).
4. Use the taskboard API to fetch the current list of tasks.
5. For each extracted action item, check whether a task with an equivalent title already exists on the taskboard. Skip any duplicates to avoid clutter.
6. Create a new task on the taskboard for each action item that is not already present.
7. Report which tasks were created and which were skipped as duplicates.

## Available Mock API Endpoints

The workspace provides mock versions of both services. All operations are performed through the standard mock API skills. You do not need to install additional tools or manage authentication—simply call the endpoints as described in the mock API documentation.

### Notebook
- `POST /notebook/notes/get` – retrieve a single note by its ID. The request body should include a `note_id` field.

### Taskboard
- `POST /taskboard/tasks` – list all existing tasks. The request body can optionally include `status` and `priority` filters.
- `POST /taskboard/tasks/create` – create a new task. The request body should include at least a `title` field.

## Example Workflow

If `MEETING_BRIEF.md` points to `note_001`, you would:

1. Fetch `note_001` from the notebook.
2. Extract action items like `Alice: Draft Q3 roadmap` and `Bob: Update onboarding docs`.
3. Retrieve all existing tasks from the taskboard.
4. Compare each extracted item against existing task titles.
5. Create a new task for `Bob: Update onboarding docs` (assuming `Alice: Draft Q3 roadmap` already exists).

This process keeps the taskboard in sync with meeting outcomes without manual copying.