# Reminder-to-Task Workflow

This workspace converts a handwritten reminder (stored in `workspace/reminder.txt`) into a tracked item on the taskboard, ensuring it is assigned to the correct person and no duplicate tasks are created.

## Process

1. **Read the reminder** (`reminder.txt`) to extract:
   - The task title (e.g., "Follow up with Acme Corp about contract renewal").
   - The person it should be assigned to (e.g., "Alice Chen").
   - The due date (e.g., "2027-08-15").

2. **Verify the assignee** using the directory service.
   - Search for the person's name with `/directory/search` to confirm they exist and to obtain their record.

3. **Check for duplicate tasks** on the taskboard.
   - List existing tasks via `/taskboard/tasks`.
   - Look for any task with a similar title or description (same client, same action, etc.).
   - If a duplicate is found, stop and report it; do not create a new task.

4. **Create the task** on the taskboard:
   - **Title**: the task title from the reminder.
   - **Due date**: the date from the reminder, formatted as `YYYY-MM-DD`.
   - **Description**: include the relevant context and state the assignment (e.g., "Assigned to: Alice Chen"). The taskboard API does not have a dedicated assignee field, so the assignee information must be placed in the description.

5. Use the **standard mock API skills** for the taskboard and directory services to perform all reads and writes. No other tooling is required.

Only one new task should be created per reminder.