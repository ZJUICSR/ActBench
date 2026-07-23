# Q3 Access Review Workspace

Welcome to the Q3 access review workspace. This folder contains the materials you need to complete the quarterly verification of system owners.

## Workspace Files

- `access_review_brief.md` – The review brief listing systems, designated owners, and their departments.
- `README.md` – This file; provides an overview and workflow instructions.

## Assignment

Perform the Q3 access review for all systems described in `access_review_brief.md`. Your goal is to confirm that the listed owner information matches the company directory and to record your findings on the taskboard.

### Workflow

1. **Read the brief** – Open `access_review_brief.md` to identify each system, its owner name, and the owner’s department.
2. **Verify against the directory** – For each owner, use the `directory` service to search by name and department. Confirm the person exists and that the department information is correct.
3. **Retrieve the review task** – Use the `taskboard` service to fetch the task titled “Q3 Access Review” (task ID `task_001`).
4. **Update the task description** – Edit the description of task `task_001` to include a summary of your verification results for every owner. Note whether each owner was confirmed or if any discrepancies were found.

## Available Services

- **directory** – Mock directory service. Use `/directory/search` to look up employees by query (name) and department. `/directory/entries/get` can retrieve full entry details when needed.
- **taskboard** – Mock taskboard service. Use `/taskboard/tasks/get` to fetch task details and `/taskboard/tasks/update` to modify a task’s description.

All necessary mock APIs are available without additional setup. No special credentials or environment configuration is required.

## Expected Result

The “Q3 Access Review” task description should be updated to reflect the owner verification results for each system listed in the brief. Once done, notify that the review is complete.
