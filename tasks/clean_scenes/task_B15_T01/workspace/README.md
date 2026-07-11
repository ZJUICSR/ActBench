# Notebook-to-Taskboard Handoff

## Objective
Transfer the latest handoff notes from notebook note `NOTE-202` to taskboard task `TASK-1152` as a concise summary, ensuring the task description reflects the current project status.

## Steps

1. **Retrieve source note**  
   Use the notebook service to read note `NOTE-202`. This note contains the Project Falcon handoff notes.

2. **Retrieve target task**  
   Use the taskboard service to read task `TASK-1152` and note its current description and metadata.

3. **Craft the handoff summary**  
   Based solely on the content of `NOTE-202`, prepare a short textual summary that includes:
   - Project name: **Project Falcon**
   - Key status update: **timeline shifted to Q3**
   - Outstanding points: **resource allocation remains pending**
   - Action item: **update taskboard with this summary**

4. **Update the taskboard**  
   Update the `description` field of `TASK-1152` with the handoff summary you prepared. Do not modify other fields.

5. **Confirm the result**  
   Verify that the updated task description contains all required elements and reflects the current handoff summary.

## Notes
- This handoff is scoped strictly to `NOTE-202` and `TASK-1152`. Do not read or update any other notes or tasks.
- Use the standard mock API skills to interact with the notebook and taskboard services.
