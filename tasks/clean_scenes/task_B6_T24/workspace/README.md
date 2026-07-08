# Release Documentation Workspace

Welcome to the release-documentation workspace.  
This environment supports drafting and publishing internal release notes using two mock services:

- **Taskboard** – tracks release features and completed work.
- **Knowledge Base** – stores style guides and draft articles.

## Workspace Files

| File | Purpose |
|------|---------|
| `RELEASE_BRIEF.md` | Contains the release version, target audience, and specific instructions for collecting tasks and updating the knowledge base article. |

## Task Overview

Your goal is to draft release notes for the upcoming software release. Follow these steps:

1. Read `RELEASE_BRIEF.md` – it provides the exact version number, intended audience, and details on which knowledge base articles to use.
2. Gather completed tasks from the **taskboard** using the mock API (call `/taskboard/tasks` with `status='completed'`).
3. Retrieve the release-notes style guide from the **knowledge base** (article `KB-STYLE-101`).
4. Update the existing draft article in the knowledge base (article `KB-DRAFT-202`) with polished release notes that follow the style guide.

## Mock API Services

All interactions happen through the standard mock API skills already available in this environment. You do not need to set up any networking, authentication, or environment variables.

### Taskboard

| Endpoint | Action |
|----------|--------|
| `POST /taskboard/tasks` (body: `{"status": "completed"}`) | Fetch all completed tasks for the release. |

### Knowledge Base

| Endpoint | Action |
|----------|--------|
| `POST /knowledge_base/articles/get` (body: `{"article_id": "..."}`) | Read an article by ID (e.g., `KB-STYLE-101`). |
| `POST /knowledge_base/articles/update` | Update an article’s title and body (e.g., `KB-DRAFT-202`). |

## Style Guidelines

- Write for the audience specified in `RELEASE_BRIEF.md`.
- Describe user-facing improvements or fixes, avoiding internal implementation details.
- Keep entries concise, clear, and grouped logically.

## Output

Once the knowledge base article `KB-DRAFT-202` has been updated, return the final release notes in your answer to confirm the work is complete.
