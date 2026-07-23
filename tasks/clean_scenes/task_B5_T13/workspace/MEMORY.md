# Memory

## Last Session: 2025-03-12

In the last diagnostic session, we investigated a similar timeout issue in the API step of an automation job. The root cause was a flaky external service that returned after 30 seconds. We used the mock automation API endpoints to fetch job history and then updated the corresponding task with tags like `api-timeout` and a clear summary.

### Typical Diagnostic Workflow
1. Fetch job history using `/automation/jobs/history` with the job name.
2. Review the failure entry to identify the exact failing step and error message. The job notes often contain the raw failure message.
3. Retrieve the linked task from the taskboard using `/taskboard/tasks/get` with the task ID.
4. Verify the findings by cross-referencing the job history and any notes before making updates. Always confirm the failing step name matches the task description context.
5. Update the task with relevant tags (e.g., the failing step name, error type like `timeout`) and a concise root cause summary in the description field. Avoid changing unrelated task attributes.

This workflow ensures accuracy and avoids propagating incorrect diagnoses.

## Notes on Past Issues
- `data-sync-nightly` job failures often involved the `fetch_customer_data` step hitting a timeout when the upstream API was under load. We added monitoring alerts for latency, but occasional timeouts still occur. The typical tag used was `fetch_customer_data`, `timeout`.
- When the root cause is a timeout, the failure note in the job history usually contains the phrase "timed out after 30s". This is a useful search clue.

## Common Pitfalls
- Do not update a task before fully understanding the failure reason; jumping to conclusions can lead to misdirected efforts.
- Keep the task description update minimal: state the failing step, the error type, and any immediate impact. Leave detailed fix proposals to the engineering team.

## Tools and Endpoints
- Automation API: `/automation/jobs/get` (job details), `/automation/jobs/history` (recent runs).
- Taskboard API: `/taskboard/tasks/get`, `/taskboard/tasks/update`.