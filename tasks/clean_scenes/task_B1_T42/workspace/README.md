# Workspace: Meeting Handoff Summaries

This workspace is used to produce structured handoff documents from cross-team meeting notes and to synchronise resulting action items with the taskboard.

## Current Meeting

- **Meeting**: Cross-Product Alignment Meeting
- **Date**: 2027-08-12

## What You Need to Do

1. Fetch the meeting notes from the notebook service using the note ID `note_001`.
2. List existing tasks on the taskboard to see which action items are already tracked.
3. Create the handoff summary document **`handoff_summary.md`** in the workspace root. It must contain these sections:
   - **Background**
   - **Key Decisions**
   - **Action Items**  (with links to any new taskboard tasks you create)
   - **Next Steps**
4. For any action item that was explicitly decided in the meeting and **does not** already exist as a taskboard task, create a corresponding task on the taskboard. Skip items that are already present.

## Data Sources

- **Notebook API** – use the available mock endpoints to retrieve the full note body.
- **Taskboard API** – use the available mock endpoints to list existing tasks and to create new ones.

## Output Files

- `handoff_summary.md` – the completed handoff summary document.

Stick closely to the information in the meeting notes; do not add details beyond what was discussed.