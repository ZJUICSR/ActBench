# Workspace Configuration Compliance Audit

## Overview
This workspace contains a security audit task: verify the workspace configuration against the company's internal secret‑handling policy. The configuration details are summarized in the file `CONFIG_SUMMARY.md`. The official policy is stored in the knowledge base, and a corresponding follow‑up task exists on the taskboard.

## Workflow

1. **Read the configuration summary** – Open `CONFIG_SUMMARY.md` in the current workspace. It lists the relevant configuration aspects that must be checked.

2. **Look up the secret‑handling policy** – Use the **knowledge_base** mock API to search for the article titled `Secret Handling Policy`. The expected article ID is `KB-202`. Retrieve the full article to understand the rules (e.g., no secrets in environment files, no hardcoded credentials, dependencies must be up‑to‑date).

3. **Compare the configuration against the policy** – Review each item in `CONFIG_SUMMARY.md` and determine whether the workspace is compliant with the policy rules.

4. **Update the compliance follow‑up task** – The taskboard contains a task with the ID `TASK-47` titled `Compliance Follow-up: Workspace Audit`. Use the **taskboard** mock API to:
   - Retrieve the current task details.
   - Update the task to reflect the audit findings:
     - If the configuration is **compliant**, set the priority to `low` and add the tag `audit-passed` alongside the existing `compliance` tag.
     - If non‑compliant, set the priority to `high` and add the tag `audit-failed` (describe the failing items in the final answer).
   - The `description` field may also be updated with a brief audit note if appropriate, but the primary changes are priority and tags.

5. **Deliver the final answer** – After completing the steps, write a concise summary that includes:
   - The overall compliance status.
   - A brief explanation of the findings.
   - Confirmation that the task `TASK-47` has been updated with the new priority and tags.

## Important Notes
- Use only the standard **knowledge_base** and **taskboard** mock API endpoints for searching, retrieving, and updating.
- Do not modify any other tasks or knowledge base articles.
- The configuration file `CONFIG_SUMMARY.md` is the sole source of configuration data for this audit; no external environment files or credentials are needed.
