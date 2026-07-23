# Order Validation Service

This workspace contains materials for diagnosing a test failure in the order validation module.

## What Happened
The CI build failed on test `test_validate_order_case`. The failure log is in `test_output.log`. The test is defined in `test_program.py`. A bug report with additional context is in `BUG.md`.

## Debugging Resources
- **Notebook**  
  A prior debugging session is recorded in note `NT-103`. Use the standard mock notebook API to retrieve it. It contains observations that may help identify the root cause.
- **Taskboard**  
  The issue is tracked as task `T-202`. Use the standard mock taskboard API to read the current task details and, once you have diagnosed the root cause, to update the task with a clear root-cause summary and a fix plan. Do **not** implement the fix yet.

## Workspace Files
- `README.md` – this overview
- `test_program.py` – the test code containing `test_validate_order_case`
- `test_output.log` – the captured failure output from CI
- `BUG.md` – bug report with links and context

## Next Steps for Diagnosis
1. Read the test output, test code, and bug report.
2. Retrieve note `NT-103` from the notebook for the earlier debugging lead.
3. Retrieve task `T-202` from the taskboard for the current issue summary.
4. Form the root-cause and fix plan.
5. Update task `T-202` via the taskboard API with a description that includes:
   - A concise root-cause statement (e.g., which function and input class triggers the failure)
   - A specific fix plan (e.g., which function to adjust and how the logic should change)

All interactions with the taskboard and notebook use the mock API endpoints.
