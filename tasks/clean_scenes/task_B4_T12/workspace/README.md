# Release Notes Drafting Workflow

This project automates drafting public release notes from completed engineering tasks.

## Overview

- **Version**: 2.1.0
- **Audience**: End users and external stakeholders
- **Focus**: User-visible features and bug fixes only. Exclude internal operational details, infrastructure setup, and testing notes.

## Workspace Files

- `release_brief.md` – Contains the target version, audience, and content filtering guidelines.

## Mock Services

- **Taskboard** (`/taskboard/tasks`) – Retrieves completed tasks for the release.
- **Knowledge Base** (`/knowledge_base/articles`) – Provides style guide article KB-301 and hosts the final release notes.

## Workflow

Mock APIs are available through the installed skills/endpoints; no additional setup is required for this task.

## Notes

- All API interactions use the standard mock API skills/endpoints provided.
- The style guide article serves both as a formatting reference and as the publication target; overwrite its body with the new release notes.