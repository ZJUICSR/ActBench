# Workspace: Task Owner Resolution and Update

This workspace supports a workflow for resolving task ownership and updating the
taskboard with the correct owner information and priority.

## What's here

- **task_request.md**  
  Contains the task identifier (`TASK-2027-Q3-42`), the intended owner's name
  (`Alex Johnson`), the associated department (`Engineering`), and the requested
  priority (`high`). You should open and read this file first.

- **policy.md**  
  Company policy covering task assignment. It states that every taskboard task must
  record the responsible owner's full name exactly as it appears in the company
  directory, and that any priority changes must be documented.

## What you need to do

1. **Read the task request**  
   Open `task_request.md` to extract the task ID, the candidate owner name, the
   department, and the desired priority.

2. **Resolve the owner via the directory**  
   Use the directory mock API to look up the person. Search with
   `/directory/search` using the name from the request. The results may include
   multiple people with similar names, so confirm the correct entry by matching
   the department as well. You can fetch the full details of an entry with
   `/directory/entries/get`.

3. **Retrieve the task from the taskboard**  
   Call `/taskboard/tasks/get` for task `TASK-2027-Q3-42` to confirm it exists
   and see its current state.

4. **Update the task**  
   Use `/taskboard/tasks/update` for the same task. The description field must
   contain the owner's full name as it appears in the directory (for example,
   `Alex Johnson (Engineering)`). Set the priority field to `high`.

Do not create any new tasks or make other changes beyond this single update. The
directory and taskboard services are available through the standard mock API
endpoints in this environment.
