# Handoff Guidelines

## Action Item Guidelines

When processing meeting notes and creating action items, follow these guidelines:

1. Extract every explicitly stated action item from the meeting notes.
2. For each action item, use the taskboard API to create a task:
   - Set the task **title** to the action item description.
   - Set the **due date** to the date mentioned in the notes, if any.
   - Include any assignee name in the task description if available.
3. Do not create additional tasks beyond those directly derived from the meeting notes.
4. If a meeting note contains no action items, create no tasks.

## Verification Note

No specific handoff verification steps are required at this time.