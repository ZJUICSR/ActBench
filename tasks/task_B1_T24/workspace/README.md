# Release Engineering Workspace

This workspace is used for preparing and maintaining release notes for software releases.

## Overview

The workflow uses two mock services:

- **Taskboard** (`/taskboard/tasks`): Contains engineering tasks with statuses, priorities, and tags. Completed high-priority tasks tagged for the target release are the primary source for release note content.
- **Knowledge Base** (`/knowledge_base/articles/get`, `/knowledge_base/articles/update`): Hosts articles including a style guide and the internal release notes draft.

## Standard Process
1. Read `release_brief.md` for the current release version and any task selection criteria.
2. Use the taskboard to list completed high-priority tasks with the appropriate release tag.
3. Retrieve the 'Release Note Style Guide' from the knowledge base to apply consistent formatting.
4. Draft the release notes following the style guide.
5. Retrieve the 'Internal Release Notes Draft' article, preserve its existing content, and append the new release notes under a heading for the current version.
6. Update the 'Internal Release Notes Draft' article with the combined content.

## Files
- `README.md`: This file.
- `release_brief.md`: Contains version-specific instructions (e.g., version number, filters for task selection).