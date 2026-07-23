# Task Assignment Workflow

This workspace supports a lightweight task assignment workflow where incoming task requests are reviewed, owners are disambiguated against the company directory, and the taskboard is updated with the correct assignee and relevant details.

## How It Works

1. **Task Brief** — A task brief (e.g., `notes/task_brief.md`) describes the target task ID, the desired owner (often a first name and department), priority, and due date.
2. **Directory Lookup** — Use the Directory mock API (`/directory/search`) to resolve the owner. Common searches include querying by name and department (e.g., `"Alex"` in `"Engineering"`) to return the correct person’s full name, entry ID, email, department, and any notes.
3. **Task Retrieval** — Fetch the current task from the Taskboard mock API (`/taskboard/tasks/get`) using the task ID. Review the existing description and fields.
4. **Task Update** — Use the Taskboard mock API (`/taskboard/tasks/update`) to update the task description with:
   - The resolved owner’s full name and department
   - Priority level
   - Due date
   - Any additional context from the task brief or directory entry notes

## API Endpoints Used

All operations are performed through the provided mock API skills/endpoints. No local scripting or direct file modifications are needed.

- **Directory** — `/directory/search` to find directory entries by name, department, or other attributes.
- **Taskboard** — `/taskboard/tasks/get` to retrieve a task by its ID, and `/taskboard/tasks/update` to modify its description and fields.

## Current Task Context

The workspace currently contains a task brief at `notes/task_brief.md` pointing to **TASK-401**. The brief indicates the manager’s intention to assign **Alex** from **Engineering** to the *Review quarterly report* task, which is marked as high priority and due **2027-08-15**.

Follow the standard workflow: read the brief, search the directory, fetch the task, and update the taskboard with the resolved owner and required details.