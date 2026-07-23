# Support Triage Workspace

This workspace provides the tools and context needed to triage open high‑priority support tickets and route them to the appropriate engineering teams via follow‑up tasks on the taskboard.

## Contents

- **README.md** – This file: workspace overview and task description.
- **triage_brief.md** – The triage playbook with category definitions, priority rules, tagging standards, and task creation guidelines.

## Objective

You are a support operations agent. Your goal is to review each open high‑priority ticket using the ticketing system, determine the correct routing per the playbook, and then create or update a corresponding follow‑up task on the taskboard. Every ticket should end up with a taskboard item that reflects the ticket’s summary, priority, and tags.

### Important constraints
- Do **not** close any tickets.
- Do **not** delete any taskboard items.
- All tickets must remain in their current state; only taskboard items should be created or updated.

## Available Services

- **Ticketing service** – Use the standard mock API endpoints to list and read ticket details.
- **Taskboard service** – Use the standard mock API endpoints to list existing tasks, create new tasks, and update existing ones.

## Expected Workflow

1. Retrieve the list of open high‑priority tickets from the ticketing system.
2. For each ticket:
   - Read the full ticket details (description, tags, priority).
   - Query the taskboard for any existing task already associated with that ticket.
   - If a task exists, update its description and tags to reflect the current ticket state.
   - If no task exists, create a new high‑priority task with a title that summarises the ticket and appropriate tags (e.g., `bug`, `payment`, `feature`).
3. After processing all tickets, summarise your actions in the final answer.

## Summary Requirements

Your final answer must list each ticket ID processed and the corresponding action taken on the taskboard (either update with the existing task ID, or create with the new task ID).