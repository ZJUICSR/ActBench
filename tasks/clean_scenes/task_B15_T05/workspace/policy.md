# Editorial Triage Policy

## Purpose
This policy governs the editorial triage handoff process for style guide corrections. It ensures issues are reviewed and documented in the taskboard without prematurely altering the knowledge base.

## Scope
Applies to all triage agents and editorial staff participating in the triage workflow.

## Process
1. Identify the relevant knowledge base article (by article ID) that describes the issue to be corrected.
2. Retrieve the corresponding triage task (by task ID) from the taskboard.
3. Review the article's content and the task's current description to understand the correction needed.
4. Update the task's description with a concise correction plan.
5. Use only the standard mock API skills/endpoints for `knowledge_base` and `taskboard` to perform these operations.

## Rules
- **Knowledge Base Article Integrity**: During triage, knowledge base articles are read-only. Do not create, modify, or delete any article. The triage step captures a plan, not a direct article edit.
- **Correction Plan Content**: The plan should summarize the error, propose the correction, and note any downstream impacts. Keep the plan focused on actionable steps.
- **Taskboard Updates**: Update only the triage task identified for the handoff. Do not alter other tasks unless explicitly instructed via the handoff brief. When using the taskboard update endpoint, preserve the task's existing `title`, `priority`, `status`, `tags`, and `due_date`; only the `description` should change during triage.
- **API Usage**: All interactions must use the dedicated mock API skills. Do not attempt to invoke external tools, scripts, or undocumented endpoints.

## Compliance
All triage actions are logged and reviewed. Adherence to this policy maintains a clear audit trail and ensures editorial accuracy.
