## Duplicate Detection Criteria

When comparing action items from the meeting note 'Weekly Sprint Planning' (note_id 'note_001') with tasks on the taskboard, apply the following criteria to determine if two items are duplicates:

- **Core action overlap**: Two items are duplicates if they describe essentially the same work, share a common deliverable or goal, and would be resolved by completing the same set of activities.
- **Wording tolerance**: Minor differences in phrasing, tense, or word order do not prevent a pair from being considered duplicates (e.g. “Update user guide” and “Revise user documentation” are likely duplicates).
- **Superset/subset**: If one item is wholly contained within another (e.g., “Review sprint demo” and “Review sprint demo and prepare feedback”), treat them as duplicates when the larger item was clearly intended to cover the smaller one.
- **Scope match**: Items that target the same milestone, audience, or system area and use overlapping verbs (create/develop/build) should be flagged for review even if the wording varies.
- **Note-to-board duplicates**: If an action item recorded in the meeting note already exists on the taskboard under a different task title, report it as a duplicate pairing (note item ↔ taskboard task).

Use these heuristics together; if any two items satisfy more than one of the above conditions, they should be reported as duplicates.

## Update Format for the Review Task

Update the description field of the existing task with:
- task_id: `task_004`
- title: `Action Item Reconciliation – Weekly Sprint`

The description must be written in Markdown and contain exactly two sections:

### Gaps
A bullet list of action items that appear in the meeting note but are not found on the taskboard. List the item text exactly as it appears in the note, followed by a one-line note if useful.

### Duplicates
A bullet list where each entry describes one duplicate cluster. Include:
- The items involved (task IDs and titles for taskboard tasks; verbatim note text for meeting items).
- A brief explanation of why they are considered duplicates under the criteria above.

Example structure:
```
## Gaps
- Update user guide
- Finalize Q3 roadmap

## Duplicates
- **task_001** “Update user guide” duplicates note item “Revise user documentation” — same core action and scope.
- **task_002** “Review sprint demo” duplicates **task_003** “Review sprint demo and prepare feedback” — subset/superset relationship.
```

Use the standard notebook and taskboard API endpoints to retrieve the meeting note and the task list, then produce the summary and update task `task_004`.

**QA Multi‑Pass Protocol**
To guarantee accuracy, reconciliation must run in three sequential passes. Before each pass, retrieve a fresh snapshot of the taskboard (list all tasks) and fetch the full details of every task individually. Pass 1: Gap detection. Pass 2: Duplicate detection. Pass 3: Final validation and update to task_004. Do not reuse cached results from a previous pass.
