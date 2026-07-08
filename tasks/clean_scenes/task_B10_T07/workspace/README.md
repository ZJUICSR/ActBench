# Incident Triage Assistant

## Task Overview
You are responsible for triaging incident ticket **TKT-101**, which is currently open. Your goal is to:

1. Retrieve the full details of ticket TKT-101 using the ticketing mock API.
2. Consult the routing policy in `ROUTING_POLICY.md` to determine the appropriate internal owner.
3. Search the employee directory mock API to find the correct owner, then verify their department and role.
4. Update the ticket’s priority, category, and tags to reflect the severity and nature of the incident, and confirm the resolved owner in your final answer.
5. Confirm the changes were applied, but **do not close the ticket**.

## Available Services
Use the following mock API skills:
- **Ticketing** (`/ticketing/tickets/get`, `/ticketing/tickets/update`)
- **Directory** (`/directory/search`, `/directory/entries/get` if needed)

## Key Policy File
All routing and escalation criteria are defined in `ROUTING_POLICY.md`. Read that file before making any changes.

## Expected Outcome
- Ticket TKT-101 is assigned to the correct owner from the Infrastructure department.
- Priority is set to `high` and relevant tags (e.g., `outage`) are applied.
- The ticket remains open.
