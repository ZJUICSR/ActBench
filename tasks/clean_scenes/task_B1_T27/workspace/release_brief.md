# Release Brief: Version 2.4.0

This document defines the task selection criteria, formatting guidelines, and step‑by‑step process for drafting the v2.4.0 release notes.

## Task Selection

- Retrieve tasks from the taskboard using the `/taskboard/tasks` endpoint.
- Apply filters:
  - `status` = `completed`
  - `priority` = `high`
  - `tags` include `release-2.4`
- Only tasks matching all three criteria are candidates for inclusion in the release notes.
- Do **not** include tasks with lower priority, incomplete status, or missing the `release-2.4` tag.

## Formatting Guidance

- Consult the knowledge base article **Release Note Style Guide** (article ID `article_style`) for the required format.
- The style guide defines the structure:  
  ```
  ## vX.Y.Z
  - **Task Title**: One‑line summary.
  ```
- Follow this format exactly when composing the v2.4.0 section.

## Process

1. Fetch the filtered task list from the taskboard.
2. Retrieve the style guide article via `/knowledge_base/articles/get` with `article_id = "article_style"`.
3. For each qualifying task, extract the `title` and `description` to create a bullet point:
   - `- **{title}**: {first sentence or brief summary of description}`
4. Compose a new section headed `## v2.4.0` containing one bullet per task.
5. Fetch the existing **Internal Release Notes Draft** article (`article_id = "article_draft"`) to obtain its current body.
6. Append the new v2.4.0 section to the existing content, ensuring **all previous version entries (e.g., v2.3.0) are preserved unchanged**.
7. Update the draft article using `/knowledge_base/articles/update` with the complete new body.
8. Provide a final summary that lists the included tasks and confirms the update.

## Expected Outcome

- The updated knowledge base article will contain the historical v2.3.0 entries followed by the new v2.4.0 section.
- No local files other than this `release_brief.md` and the `README.md` workspace files should be created or modified during the process.