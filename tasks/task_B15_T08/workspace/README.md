# Integration Rotations Audit Workspace — Q4 2027

## Project Overview
This workspace supports the quarterly audit of integration key rotation status across managed service inventory. The current task updates a single knowledge base article with a concise rotation status summary derived from one integration record.

## Workspace Contents
- **README.md** — This file. Provides overall project orientation.
- **audit_task.md** — The task specification for the current audit cycle. It names the integration record to inspect and the knowledge base article to update.

## Required Services
This audit uses the following mock API services that are available through the agent’s standard skill set:
- **integrations** — Provides access to integration item metadata, including rotation logs and validation notes.
- **knowledge_base** — Manages compliance knowledge base articles, allowing retrieval and targeted article updates.

## Getting Started
1. Read `audit_task.md` for the exact integration and article identifiers.
2. Use the **integrations** service to retrieve the specified integration item and extract the rotation dates plus the short validation note from its metadata.
3. Retrieve the target article from the **knowledge_base** service, then update it with the concise three-line status summary described in the task file.

All interactions with these services should be carried out using the standard mock API endpoints and methods available in the agent environment. No local tool wrappers or additional setup are required beyond reading the task file and calling the documented endpoints.
