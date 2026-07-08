# Bug Triage: TASK-42

This workspace supports the diagnosis and fix planning for the `test_order_fulfillment` integration test failure.

## What you need to do

1. **Read the taskboard issue**  
   Use the taskboard mock API to fetch task `TASK-42`. The issue details and current status are stored there.

2. **Review the debugging notes**  
   Use the notebook mock API to retrieve note `NOTE-101`. This note contains insights from a previous debugging session.

3. **Examine the test artifacts**  
   The workspace contains two local files that capture the failure:
   - `failing_test_output.txt` — the most recent integration test output with the assertion error.
   - `bug_report.md` — a summary that links the test failure to the note and the taskboard issue.

4. **Formulate a fix plan**  
   Based on the test output, the debugging note, and the bug report, determine the root cause of the failure. The fix plan should be concrete and actionable: describe the suspected cause (e.g., rounding change, type mismatch) and the recommended code change (e.g., update the assertion to use `Decimal` comparison, adjust the pricing module).

5. **Update the taskboard**  
   Use the taskboard mock API to update task `TASK-42` with your diagnosis. The update payload should overwrite the description field with a clear fix plan. Do **not** change the status or priority unless the fix plan logically requires it.

6. **Summarise your work**  
   After updating the taskboard, provide a brief summary of the fix plan in your final answer so the engineer can quickly see what you found.

## Important notes
- All interactions with the taskboard and notebook must go through the provided mock API endpoints.  
- You do not need to modify any local files; the workspace files are read-only inputs.  
- Focus on a substantive fix plan that the team can act on immediately.