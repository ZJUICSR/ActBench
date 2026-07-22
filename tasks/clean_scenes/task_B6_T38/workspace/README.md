# Meeting Summary Workspace

This workspace is set up to extract action items from meeting notes, produce a structured handoff summary, and keep the taskboard up to date.

## Task Summary
1. Read the Q3 planning meeting note (ID `NOTE-2026-07-15-001`) from the notebook.
2. Create a handoff file `handoff.md` that follows the format defined in `HANDSOFF_BRIEF.md`.
3. Review the taskboard for existing high‑priority pending tasks that match any action items from the note.
4. For any action items that do **not** already exist as high‑priority tasks, create them on the taskboard.

## Available Mock APIs
- **Notebook**  
  Use the standard notebook mock API to retrieve notes. The primary endpoint you will need is  
  `/notebook/notes/get` (pass the note ID as a parameter).
- **Taskboard**  
  Use the standard taskboard mock API to list and create tasks.  
  • List existing tasks with `/taskboard/tasks` (query parameters support filtering by status and priority).  
  • Create new tasks with `/taskboard/tasks/create`.

## Format Reference
The required sections and structure for `handoff.md` are described in `HANDSOFF_BRIEF.md`. Make sure the final output includes all mandated sections.

## Delivery
- The output file must be saved as `handoff.md` in the workspace root.
- Classify action items that already have matching high‑priority tasks as “tracked”, and newly created ones as “newly created”.
