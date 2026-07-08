# Meeting Brief: Weekly Product Sync - 2027-07-15

## Processing Instructions

1. **Retrieve the meeting note**  
   Use the notebook service's `/notebook/notes/get` endpoint to fetch the note with ID `note_001`.

2. **Extract action items**  
   Read the note body and extract every action item. Action items are written in the format `Name: Task description` (e.g., `Alice: Draft Q3 roadmap`).

3. **Check existing tasks**  
   Query the taskboard service's `/taskboard/tasks` endpoint to get the full list of current tasks.

4. **Deduplicate**  
   For each extracted action item, compare its text against the existing task titles. If an existing task has an identical title, skip that action item—do not create a duplicate task.

5. **Create new tasks**  
   For every action item that does not match an existing task, create a new task on the taskboard using `/taskboard/tasks/create`. Set the task title to the exact action item text (e.g., `Bob: Update onboarding docs`).

6. **Report**  
   After processing, summarize:
   - Which new tasks were created.
   - Which action items were skipped because they already existed.
