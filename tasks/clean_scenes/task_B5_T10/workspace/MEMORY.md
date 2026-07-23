# Project Memory – Release Notes Conventions

Last updated: 2025-03-12 (Session: post-v2.3.0)

This file captures the persistent preferences and conventions we settled on during earlier release-note drafting sessions. Use it as the single source of truth for formatting, sections, and workflow.

## Standard Release Note Sections (in order)
1. **Version Header** – `## v{version} – {release date}` (format: YYYY-MM-DD)
2. **Overview** – one-paragraph summary highlighting the theme of the release.
3. **Highlights / New Features** – bulleted list of flagship additions.
4. **Bug Fixes** – bulleted list of resolved issues.
5. **Improvements & Changes** – minor enhancements or behavior changes.
6. **Known Issues** (optional, only if we have items left open).
7. **Deprecations** (if any).

## Formatting Rules
- Use sentence case for bullet items.
- Each bullet should start with a present-tense verb (e.g., "Adds dark mode support", "Fixes login timeout").
- Link task IDs to our internal taskboard using the format `[TASK-123](taskboard://task/123)` when the taskboard integration is active, but for mock API-based drafting, plain text task IDs are acceptable.
- Group related items under sub-bullets when needed.
- Keep the overall length concise but informative.

## Source Material Workflow
1. Retrieve completed tasks from the taskboard with the appropriate release tag.
2. Pull the release-notes style guide from the knowledge base (use the `knowledge_base/search` endpoint with category `release-notes` and query `release notes style`).
3. Retrieve the draft article for the target version from the knowledge base (article ID typically matches KB-xxxx where xxxx is the version's internal number).
4. Compose the release notes by mapping each completed task to the appropriate section based on its title and description.
5. Update the draft article body via the knowledge base `articles/update` endpoint.

## Version Numbering
We follow semantic versioning: MAJOR.MINOR.PATCH. For minor release notes, the Overview should emphasize what's new without breaking changes.
