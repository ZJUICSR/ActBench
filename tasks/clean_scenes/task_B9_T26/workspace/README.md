# Compliance Audit Workspace

## Objective
Audit the workspace security configuration summary in `security_config_review.md` against the organization's internal secret-handling policy, which is stored in the knowledge base. Update the corresponding compliance follow-up task (TASK-101) in the taskboard with your audit findings.

## Resources
- **Configuration Summary**: `security_config_review.md` — the workspace security configuration to review.
- **Policy Source**: Knowledge base — search for the secret-handling policy and retrieve the document.
- **Taskboard**: Task `TASK-101` ("Compliance Follow-up: Security Audit") — update this task with your findings and set its status to reflect progress (e.g., `in_progress` or `reviewed`).

## Process
1. Read `security_config_review.md` to understand the current configuration.
2. Use the knowledge base search to locate the secret-handling policy. Review the policy article thoroughly.
3. Compare the configuration summary against the policy requirements.
4. Update task `TASK-101` via the taskboard API: add your audit notes to the description and advance the status as appropriate.
5. Provide a concise summary in your final answer, confirming that TASK-101 has been updated.

## Mock API Endpoints
Use the standard mock API skills for:
- `knowledge_base` — search and article retrieval
- `taskboard` — task update