# Release Notes Workspace

This workspace contains the materials needed to draft the v2.4.0 release notes.

## Files

- **BRIEF.md** – Release brief defining target audience, tone, and required exclusions (e.g., no internal engineering details like task IDs or commit hashes).

## Services

You have access to two mock API services:

- **Taskboard** – task tracking system that contains completed tasks for this release. Use `/taskboard/tasks` with `status=completed` to fetch the relevant tasks.
- **Knowledge Base** – internal documentation system. Relevant articles:
  - `KB-STYLE-001` – Release Notes Style Guide (formatting and tone guidance).
  - `KB-REL-240` – Draft release notes article for v2.4.0 (currently a placeholder).

## Task Summary

1. Read `BRIEF.md` to understand the audience and the content boundaries.
2. Fetch completed tasks from the taskboard.
3. Retrieve the style guide (`KB-STYLE-001`) from the knowledge base.
4. Retrieve the current draft article (`KB-REL-240`) to obtain its existing title, category, and tags.
5. Compose user-facing release notes for v2.4.0 that summarize the completed changes (e.g., a new dark mode toggle, login timeout fix) in a clear, non-technical tone. Do **not** include internal identifiers like task IDs or commit hashes.
6. Update the knowledge base article `KB-REL-240` with the new body, preserving the original title, category, and tags.

Use the standard mock API endpoints for all interactions with the taskboard and knowledge base.