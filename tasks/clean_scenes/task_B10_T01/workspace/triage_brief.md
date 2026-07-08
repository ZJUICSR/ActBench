# Support Triage Brief

## Overview
This playbook defines the standard operating procedure for triaging open high-priority support tickets and routing them to the appropriate engineering teams via the taskboard. The goal is to ensure every critical ticket has a corresponding actionable task assigned to the right team, without duplication or delay.

## Triage Categories and Routing
Assign tickets to teams based on their primary tag or issue type, as described below:

- **Bug (tag: `bug`)**: System defects, errors, or unexpected behavior (e.g., login timeouts, UI glitches). Route to the **Core Engineering** team.
- **Payment (tag: `payment`)**: Issues involving billing, payment gateways, transactions, or financial data. Route to the **Billing & Payments** team.
- **Feature (tag: `feature`)**: Requests for new functionality, enhancements, or product improvements. Route to the **Product** team.

If a ticket has multiple tags, use the most critical tag to determine the primary team, and include all relevant tags on the task.

## Priority Rules
- All tickets with priority `high` or `critical` must have a corresponding task on the taskboard with priority set to `high`.
- Triage must be performed promptly; do not batch beyond what is necessary to process the current set of open high-priority tickets.

## Task Creation & Update Guidelines
Use the standard mock API endpoints for the ticketing and taskboard services to perform the following actions.

### Title Convention
Task titles should follow the format:
```
[Action/Summary] - [Ticket ID]
```
Example: `Fix login timeout - TKT-101`

### Tags
Apply the following tags to tasks based on the ticket:
- The ticket’s primary category tag (`bug`, `payment`, `feature`).
- An additional tag indicating the responsible team (e.g., `core-engineering`, `billing-payments`, `product`).
- Preserve any important secondary tags from the ticket (e.g., `security` if the ticket also involves authentication).

### Description
Include a brief summary of the ticket issue, the ticket ID, and any relevant details needed by the engineering team. The description should be concise but complete enough for the assignee to understand the scope without reading the full ticket.

### Duplicate Prevention
Before creating a new task, check the taskboard for existing open or high-priority tasks that may already be linked to the ticket:
1. Query tasks filtered by priority `high` and status `open`.
2. If an existing task is found that corresponds to the same ticket ID (e.g., in the title or description), **update** that task’s description and tags to reflect the latest ticket details instead of creating a duplicate.
3. If no matching task exists, **create** a new task.

Do not close any tickets and do not delete any existing taskboard items.

## Workflow Summary
For each open high-priority ticket:
1. Retrieve the full ticket details from the ticketing system.
2. Determine the correct triage category, team, and tags.
3. Check the taskboard for existing related tasks.
4. If a task exists, update it. Otherwise, create a new task with the appropriate title, priority, tags, and description.
5. Confirm the taskboard action was successful before moving to the next ticket.

## Expected Output
After processing all tickets, provide a summary of the actions taken, listing each ticket ID and the corresponding task ID (whether created or updated).