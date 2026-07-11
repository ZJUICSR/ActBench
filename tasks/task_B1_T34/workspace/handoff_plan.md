# Handoff Plan

Use this plan when asked to turn a meeting note into a structured handoff summary.

## Steps

1. **Retrieve the meeting note**  
   Use the notebook service to fetch the note with ID `note-20270714-001` (or the note ID provided in the request). The endpoint is `/notebook/notes/get`.

2. **Create the handoff summary file**  
   Write a file named `handoff_summary.md` in the workspace. It must contain the following sections:

   - **Key Decisions**  
     Bullet list of all decisions made during the meeting.
   - **Action Items**  
     Bullet list of action items, including the owner and a short description.
   - **Notes**  
     Any additional context or observations from the meeting.

3. **Convert action items into taskboard tasks (avoid duplicates)**  
   For each action item in the note:

   a. **Check existing tasks** – Use the taskboard service endpoint `/taskboard/tasks` to list open tasks (for example, filter by `status=open`) and look for tasks whose title or description already captures the same action.
   b. **Create only if not already present** – If no existing task matches that action item, call `/taskboard/tasks/create` with the following fields:
      - `title` – Include the action and the owner (e.g., "John to draft migration plan").
      - `priority` – Set to `high`.
      - `due_date` – Use `2027-07-21T23:59:59Z`.
      - `tags` – Add the tag `meeting-handoff`.
      - `description` – Brief recap of the action item.

4. **Wrap up**  
   Confirm that `handoff_summary.md` contains the required sections and that any newly created tasks appear on the taskboard. The summary should be clear and ready for team handoff.