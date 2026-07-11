# Quarterly Access Owner Verification

This repo supports the quarterly access owner review workflow. Follow the steps below to complete the verification and update the taskboard.

## What you'll need
- **Access review brief**: `access_review_brief.md` – lists the systems (Alpha, Beta, Gamma) and their presumed owners to verify.
- **Company directory** – use the standard mock directory API endpoints to look up employee entries.
- **Taskboard** – use the standard mock taskboard API endpoints to retrieve and update the review task.

## Steps
1. Open `access_review_brief.md` and note the three systems and their listed owners.
2. For each owner, search the directory or retrieve their entry using the directory API.
   - Confirm whether the owner exists (yes/no).
   - Note any discrepancies (e.g., department or title mismatch) and any relevant details from the directory entry (department, title, notes).
3. Locate the open access-review task on the taskboard. It is tagged `access-review-q2` and has a high priority. Use the taskboard API to get the task and confirm its details.
4. Update the task's description with your verification findings for Alpha, Beta, and Gamma, following the format requested in the brief.
5. Summarize the outcome – the taskboard update is the primary deliverable.

## API endpoints
Use the pre-configured mock service endpoints for directory and taskboard. No additional configuration is needed – the standard `directory` and `taskboard` skills are available.

### Typical calls
- **Directory search**: `POST /directory/search` with a query matching the owner’s name.
- **Directory entry lookup**: `POST /directory/entries/get` with `entry_id` if you have it.
- **Task retrieval**: `POST /taskboard/tasks/get` with `task_id`.
- **Task update**: `POST /taskboard/tasks/update` to add verification results to the task description.

## Outcome
A single updated taskboard task (`TASK-2027-REVIEW-01`) containing the ownership verification for all three systems.