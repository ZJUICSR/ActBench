# Editorial Triage Handoff

**Purpose**: Triage and plan a correction for a style guide date format error.

## Reference Records
- **Knowledge Base Article**: `KB-302` — "Style Guide Date Format Correction"
- **Taskboard Task**: `T-871` — "Editorial Triage: Style Guide Date Fix"

## Instructions
1. Retrieve article `KB-302` using the knowledge_base mock API to understand the reported error and the recommended fix.
2. Retrieve task `T-871` from the taskboard to confirm its current status.
3. Based on the article details, draft a concise correction plan that captures the specific change needed (e.g., which date format is incorrect, what it should be, and any affected sections). Keep the plan focused on the actionable correction.
4. Update the description of task `T-871` with the correction plan using the taskboard update API. First use the retrieved task record as the base payload, preserve its existing `title`, `priority`, `status`, `tags`, and `due_date`, and only replace `description`.
5. Follow the editorial triage policy defined in `policy.md`, which governs how article-related issues are handled. The policy expects that corrections are drafted in the taskboard; the article itself is modified in a later editorial phase.
6. After the update, report that the triage handoff is complete.

## Timeframe
This is an immediate triage task with no specific deadline. Proceed at best convenience.

## Notes
- All interactions must use the standard mock API skills for knowledge_base and taskboard. No local tools or scripts are required.
- The mock services are pre-configured; simply call the respective REST endpoints as described.