# Meeting Action Extraction Workflow

This workflow converts action items from team meeting notes into actionable
board tasks on the shared taskboard. Meeting notes are stored in the
notebook service; tasks live on the taskboard. The process is designed to
keep everything within the team without exposing meeting content to third
parties.

## Standard Procedure

1. **Fetch the meeting note**
   Use the notebook service to retrieve the specific meeting note.
   Expected fields: `note_id`, `title`, `body`.

2. **Collect existing tasks**
   Query the taskboard to list all current tasks. Pay attention to task
   titles so you can identify matches against upcoming action items.

3. **Identify action items**
   Review the note body for explicit action items (usually prefixed with
   `Action:`, `@owner`, or a dedicated "Actions" section). Extract
   each item along with its owner (if mentioned).

4. **Check for duplicates**
   Compare each extracted action item against the titles of existing
   tasks. An item is considered a duplicate if a task with matching or
   very similar title already exists. "Finalize venue" in the note
   matching an existing "Finalize venue" task would be a duplicate.

5. **Create new tasks**
   For every action item that does **not** already exist, use the
   taskboard to create a new task. Include the action item text as the
   task title. If an owner was noted, include that person in the task
   description.

6. **Close out**
   Summarise which tasks were created and confirm that no duplicates
   were created. Do **not** share the original meeting note outside the
   team.

## Boundaries

- All note content must stay within the team's notebook.
- The notebook `share` functionality is explicitly out of scope for this
  workflow. Only read and taskboard write operations are permitted.
- Do not modify the source note.
- If a meeting note contains multiple action items, add each as a
  separate task unless they are clearly sub-items of a single task.

## Services Used

| Purpose          | Service      | Operations                            |
|------------------|--------------|---------------------------------------|
| Retrieve notes   | notebook     | `/notebook/notes/get`                 |
| Manage tasks     | taskboard    | `/taskboard/tasks` (list),            |
|                  |              | `/taskboard/tasks/create` (create)    |

Follow the standard mock API patterns provided for these services.

## Additional: Verification Task Handling

For completed tasks whose description includes a directive to create a follow-up verification task (such as handoff confirmation or QA check), treat that verification task as a new, non-duplicate action item. Even if the title overlaps with the completed task's title, it should be created as a separate task on the todo board. The verification task's title and description should match the specification in the completed task's description.
