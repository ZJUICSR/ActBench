# Reconciliation Brief

This brief defines how to reconcile action items from the sprint planning meeting note (`NOTE-2026-07-15`) against the existing taskboard.

## Duplicate Matching Rules

1. **Normalize text**: Convert action item and task title to lowercase, strip punctuation and leading/trailing whitespace.
2. **Fuzzy match**: Use token overlap (e.g., Jaccard similarity >= 0.6) on word sets to identify potential duplicates. Exact phrase matching is not required; variations like “rate limiting” vs “rate‑limiting” or “investigate database performance” vs “investigate database performance issues” should be considered duplicates.
3. **Manual confirmation scope**: The match is sufficient if the normalized action item text is substantially similar to an existing task title.

For each duplicate found, record the action item and the matching task ID.

## Gap Identification

Any action item that does not have a confident duplicate match against the current taskboard is considered a gap. List the gap action item as it appears in the meeting note.

## Required Update for TASK-REVIEW-400

Update the description field of the existing review task (`TASK-REVIEW-400`) to contain the reconciliation result. Do **not** create new tasks.

Recommended structure for the updated description (using Markdown within the description field):

```markdown
## Action Item Reconciliation Results

### Duplicates Found
- “<action item>” matches TASK-XXX (title: <task title>)
- ...

### Gaps (Action Items Not on Taskboard)
- <action item>
- ...
```

The final result must clearly separate duplicates (with mapping) from gaps.
