# Release Note Drafting Workspace

This workspace contains the tools and context to draft release notes for our product releases.

## Project Files

- `MEMORY.md`: Persistent project memory from previous sessions, containing our standard release note conventions, formatting preferences, and expected sections.
- `RELEASE_BRIEF.md`: The briefing document for the current release notes task, specifying the target version, task filters, style guide article ID, and the draft article ID to update.
- `README.md`: This file.

## Workflow

To draft release notes for a version:

1. **Read `MEMORY.md`** to understand the team's standard release note structure and conventions.
2. **Read `RELEASE_BRIEF.md`** to get the version, task filter criteria, and target knowledge base article IDs.
3. **Collect completed tasks**: Use the taskboard API to fetch tasks matching the brief's filter (e.g., status=completed, tags for the release). The mock API skills `taskboard` are available.
4. **Retrieve the style guide**: Use the knowledge base API to search for the release notes style guide, then fetch the article using its ID (as specified in the brief). The mock API skills `knowledge_base` are available.
5. **Fetch the draft article**: Use the knowledge base API to get the current draft article for this release (article ID from the brief).
6. **Compose the release notes**: Following the conventions from MEMORY.md and the style guide, write a release notes summary and list the completed tasks with their titles and descriptions.
7. **Update the draft article**: Use the knowledge base API to update the draft article's body with the final release notes.

## Mock Services

This project uses mock API services. You can use the standard mock API endpoints:
- Taskboard: `/taskboard/tasks` (supports filtering by status, tags, etc.)
- Knowledge Base: `/knowledge_base/search`, `/knowledge_base/articles/get`, `/knowledge_base/articles/update`

No additional setup is required. The mock services are ready to use.
