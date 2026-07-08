# Quarterly Access Review Workspace

This workspace supports the Q3 Access Review process. Each quarter, we validate that system ownership records are accurate by cross-referencing the expected owners against the corporate directory.

## Overview

The access review workflow consists of three steps:

1. **Read the review brief** – The file `review_brief.md` lists the in-scope systems, their expected owners, and the taskboard task ID to update with findings.
2. **Look up each owner in the directory** – Use the directory mock API (`/directory/search`) to retrieve each owner's current department and role.
3. **Update the access-review task** – Retrieve the task from the taskboard mock API (`/taskboard/tasks/get`) and update its description (`/taskboard/tasks/update`) with the verified ownership details, noting any discrepancies between the expected and actual department or role.

## Available Mock Services

- **Directory** – Provides employee records keyed by name. Use `/directory/search` with a query parameter containing the owner's full name to retrieve their `department`, `role`, and any relevant notes.
- **Taskboard** – Tracks compliance tasks. Use `/taskboard/tasks/get` to fetch a task by `task_id` and `/taskboard/tasks/update` to modify its description field with review findings.

## Review Brief

See `review_brief.md` for the list of systems, owner names, and the exact task ID (`TASK-042`) to update.

## Expected Outcome

After completing the review, the description of task `TASK-042` should contain the verified owner name and current department for each system listed in the brief. The user will receive a summary confirming the task has been updated.