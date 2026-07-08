# Reminder to Taskboard Automation

This workspace helps you convert a reminder note (in `notes.md`) into a taskboard task that mentions the responsible teammate. The workflow uses the standard directory and taskboard mock API services.

## How to process a reminder

1. **Read the reminder** – open `notes.md` and extract the task title, due date, description, and teammate to mention.
2. **Look up the teammate** – use the `/directory/search` endpoint to find the person (e.g., Alice Chen) and retrieve their name and any relevant notes.
3. **Check existing tasks** – call `/taskboard/tasks` to list open tasks and verify there is no duplicate or conflicting item.
4. **Create the task** – send a request to `/taskboard/tasks/create` with a clear title, an ISO‑8601 due date, and a description that includes the reminder details and mentions the responsible teammate.
5. **Confirm the result** – verify that the new task appears in the task list and report the task ID, title, and due date back to the user.

## Example

If `notes.md` contains a reminder for Alice Chen to review the Q3 marketing plan by 2026-06-26, you would:
- Search the directory for "Alice Chen" to confirm her full name.
- List open tasks and see that an older "Review Q3 marketing budget" exists but is not the same item.
- Create a new task with title "Review Q3 marketing plan", due date `2026-06-26T00:00:00Z`, and description that includes "@Alice Chen" or her full name.

All interactions with directory and taskboard services happen through the mock API endpoints. No local scripts or environment configuration are required to follow this process.
