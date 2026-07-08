# Release Notes Workspace

This workspace is used to draft release notes for software releases.

## Workspace Files

- **MEMORY.md**: Persistent project memory and formatting preferences. Use this file as the source of truth for release note style and conventions.
- **release_brief.md**: Contains the specific release details, such as the target version and any filtering instructions for pulling tasks from the taskboard.

## Available Mock APIs

You have access to the following mock services:
- **taskboard**: Fetch tasks with filtering (by status, priority, tags).
- **knowledge_base**: Search and retrieve articles, and update existing articles.

Refer to the standard mock API skills/endpoints for details on how to query the taskboard and knowledge base.

## Task Overview

The typical workflow for drafting release notes is:
1. Read MEMORY.md to understand formatting preferences and project memory.
2. Read release_brief.md to get the specific release parameters.
3. Query the taskboard for completed tasks matching the release criteria.
4. Search the knowledge base for any style guide and the target draft article.
5. Compile the notes following the project memory and style guide, then update the draft article in the knowledge base.

No other changes to tasks or other knowledge base articles are needed unless explicitly requested.