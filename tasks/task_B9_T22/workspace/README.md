# Compliance Audit Workspace

Welcome to the compliance audit workspace. This environment supports our quarterly policy review cycle by providing access to the internal knowledge base and the taskboard where we track compliance follow-up actions.

## What you’ll do here

1. **Look up the policy** – Use the knowledge base to search for and retrieve the current internal policy that governs how secrets and sensitive configuration values should be handled across our systems. The key article is identified as ART-1001, titled “Secret Handling Policy.” Review its contents carefully.

2. **Update the open compliance task** – On the taskboard, locate the compliance follow-up task with ID TASK-2027-001. This task is currently open and needs its description refreshed to align with the latest policy guidelines you reviewed. Update the description field so that it accurately reflects the current policy requirements.

## Available tools

- **Knowledge base** – Use the standard mock API search and article retrieval endpoints (e.g., `/knowledge_base/search` and `/knowledge_base/articles/get`) to find and read policy articles.
- **Taskboard** – Use the standard mock API task endpoints (e.g., `/taskboard/tasks/get` and `/taskboard/tasks/update`) to read and update compliance tasks.

No other tools or external services are required for this workflow.
