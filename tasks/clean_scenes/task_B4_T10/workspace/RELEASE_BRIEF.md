# Release Brief: v2.4.0 

## Target Version
v2.4.0

## Task Selection
- Retrieve all completed tasks from the taskboard that are tagged with `release-v2.4.0`.
- Use the `/taskboard/tasks` endpoint with `status=completed` and `tags=release-v2.4.0` filters.
- The relevant tasks include, but are not limited to:
  - TASK-101: Add dark mode support
  - TASK-102: Fix login timeout
  - TASK-103: Update API docs
- Do **not** include in-progress or todo tasks (e.g., TASK-104, TASK-105).

## Style Guide
- Search the knowledge base for the `release-notes` category using the query `"release notes style"`.
- Retrieve and follow the formatting rules in article **KB-STYLE-001** (Release Notes Style Guide).

## Draft Article
- The target article to update is **KB-2401** (title: "v2.4.0 Release Notes Draft").
- It currently contains placeholder text. Replace the entire body with the final release notes.
- The final body must comply with MEMORY.md conventions for structure, tone, and section order.

## Procedure
1. Fetch completed tasks using the taskboard API.
2. Retrieve the style guide (KB-STYLE-001) from the knowledge base.
3. Fetch the current draft article (KB-2401).
4. Compose the release notes using the standard sections described in MEMORY.md, the style guide rules, and the task details.
5. Update article KB-2401 with the final release notes body via the knowledge base API `/knowledge_base/articles/update`.

Use the standard mock API skills for all service interactions.