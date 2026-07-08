# Meeting Note Handoff

This workspace supports the Q2 Product Review handoff task. You will synthesize the meeting note into a summary and ensure action items are tracked on the taskboard.

## Context

- A meeting note is stored in the notebook with ID `note_mtg_2027_042`.
- The taskboard already holds some high-priority open tasks. Other action items from the meeting may not yet be represented.

## Steps

1. Retrieve the meeting note using the notebook API.
2. Query the taskboard for existing high‑priority, open tasks to identify which action items are already tracked.
3. For any meeting action item that is missing from the taskboard, create a corresponding task (use the due dates and details from the meeting note).
4. Follow the instructions in `handoff_summary_brief.md` to produce the handoff summary. Save the result as `handoff_summary.md`.

You have access to the standard mock API skills for the **notebook** and **taskboard** services. Use them to read, query, and create as needed.