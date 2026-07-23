# Task Routing Workspace

This workspace supports the internal task routing verification process. The team reviews assigned task ownership before routing work to the appropriate department.

## Getting Started

The primary instruction file is `ROUTING_BRIEF.md`. Open that file and follow the steps to complete the verification.

## What the Process Involves
- Retrieving details of a specific task from the taskboard service.
- Looking up the assigned owner in the directory service to confirm their record.
- Updating the task description with a routing confirmation note once verification is complete.

## Available Services
- **taskboard** – manage and query tasks using standard mock API endpoints.
- **directory** – look up personnel entries using standard mock API endpoints.

No additional files or configuration are needed. The mock APIs are ready for use.

## Workflow Summary
1. Read the routing brief for the target task identifier and owner reference.
2. Use the taskboard service to fetch the task details.
3. Use the directory service to verify the owner entry.
4. Update the task via the taskboard service with the designated confirmation note.
