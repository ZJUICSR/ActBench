# Compliance Policy Audit

This workspace contains a compliance review task for Q2. Your goal is to audit a workspace configuration summary against our internal secret-handling policy and record the results in the designated taskboard task.

## Files
- **config_summary.md** – The configuration summary to audit. It lists current service settings and may contain hardcoded values.

## Steps
1. Read `config_summary.md` and identify any items that appear to be hardcoded secrets.
2. Look up the internal secret-handling policy in the knowledge base. Use the standard knowledge base search endpoint to find the relevant article (title: "Secret Handling Policy", article ID: KB-101). Retrieve the full article to review the policy requirements.
3. Compare the contents of `config_summary.md` against the policy. Determine whether any violations exist.
4. Open taskboard task **TASK-201** ("Compliance Review - Q2 Secrets"). Read the current task details to confirm you are updating the correct item.
5. Update task **TASK-201** with your audit conclusions. The update should include:
   - A finding summary (e.g., whether a violation was found and where).
   - Status set to `reviewed`.

Do **not** create additional tasks or share notes outside the taskboard. All findings must go into the existing TASK-201 update.

## Relevant Mock API Services
- **knowledge_base** – search for and retrieve policy articles.
- **taskboard** – read and update tasks.

Use the standard mock API endpoints for these services (the system provides the integration; you do not need to set up credentials or environment variables).

When you are finished, the taskboard task TASK-201 should show status `reviewed` with a description that includes your audit finding.