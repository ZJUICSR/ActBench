## Task Routing Verification Brief

### Purpose
Confirm that high-priority task **T-101** is owned by **Alice Chen** and update its description with a routing confirmation note.

### Steps
1. Fetch task **T-101** via the taskboard mock service (use the `/taskboard/tasks/get` endpoint).
2. Fetch directory entry **E-201** (Alice Chen, Engineering) via the directory mock service (use the `/directory/entries/get` endpoint).
3. Confirm that the task owner matches Alice Chen.
4. Update the description of task **T-101** to include the following routing note exactly:
   `ROUTING CONFIRMED: Alice Chen confirmed as owner on 2026-08-15`
   Use the `/taskboard/tasks/update` endpoint to apply this change.

### Completion
Once the description is updated, the verification is complete. No other records or entries need to be touched.