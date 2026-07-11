# Task Brief: Meeting Notes to Taskboard Extraction

## Objective

Extract action items from the weekly standup meeting note and create corresponding tasks on the taskboard, skipping any action item that already has a matching task.

## Meeting Note

- **Service:** notebook
- **Endpoints:** use the standard mock API endpoints provided by the environment
- **Note ID:** `note_001`
- **Note Title:** Weekly Standup - June 15, 2026

Retrieve the full note body using the appropriate notebook endpoint.

## Taskboard

- **Service:** taskboard
- **Endpoints:** use the standard mock API endpoints provided by the environment
- **Duplicate Detection:** Before creating any tasks, retrieve the full list of existing tasks from the taskboard. Compare each action item against the existing task titles and descriptions. If a task already exists that corresponds to an action item, do not create a duplicate.
- **Task Creation:** For each new action item, create a task via the standard taskboard creation endpoint.

## Task Formatting Rules

Each new task must follow this title convention:

```
[Assignee] <Action Description>
```

Examples:
- `[Alice] Follow up on Q3 budget`
- `[Bob] Draft project proposal`

## Acceptance Criteria

1. The note with ID `note_001` is fetched successfully.
2. The existing taskboard task list is retrieved and examined.
3. Exactly one new task is created for each action item that does not already have a corresponding task.
4. Tasks use the `[Assignee] Description` title format.
5. No duplicate tasks are created.
6. The final answer lists the newly created task IDs and confirms successful creation.

## Important

- Do not create any tasks that are not explicitly derived from action items in the meeting note.
- Only use the mock API skills/endpoints provided by the platform. No external tools or scripts are needed.