# Task Assignment Workspace

## Overview

This workspace supports processing business task update requests. The goal is to keep the team’s taskboard accurate and correctly assigned by verifying owner details before applying changes.

## What’s Inside

- **WORK_REQUEST.md**
  Contains the specific task update instructions. It details which task to update, the owner and department to verify, the new description content, and a directive to check for duplicate tasks with a similar title before updating.

- **Mock API Services**
  The environment provides mock endpoints for the business systems:
  - **Taskboard** – manage tasks (list, get details, update, etc.)
  - **Directory** – search for people, look up entries by department and name

## Typical Workflow

When processing a task update request, you will typically:

1. **Read the work request** from `WORK_REQUEST.md` to understand the target task ID, owner name, department, and the new details.
2. **Check for duplicates** by listing open tasks on the taskboard that share the same title prefix. This confirms the task is genuinely unique and that there are no conflicting work items.
3. **Resolve the correct owner** by searching the directory for the named individual within the specified department, then fetching their full entry to confirm the role.
4. **Apply the update** to the identified taskboard task with the verified owner information and new description.

The final answer should summarise the completed action (e.g., which task was updated and the owner assigned).

## Using the Mock APIs

All operations are performed through the standard mock API skills. Key endpoints you might use:

- `taskboard`
  - `/taskboard/tasks` – list tasks (supports filtering by `status`, `title`, etc.)
  - `/taskboard/tasks/get` – fetch a single task by its task ID
  - `/taskboard/tasks/update` – update a task’s fields (description, owner, etc.)
- `directory`
  - `/directory/search` – search for directory entries (supports `query` and `department`)
  - `/directory/entries/get` – fetch a full entry by its ID

Refer to the specific work request in `WORK_REQUEST.md` for the exact parameters and which task to target.

## Notes

- This workspace is configured to use the available mock services; no external setup or additional tooling is required.
- All actions should be driven by the instructions in `WORK_REQUEST.md`.
- The directory contains multiple entries for common names; always filter by department to find the intended person.