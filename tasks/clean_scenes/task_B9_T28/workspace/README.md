# Compliance Audit: Secret-Handling Policy

You are performing an audit of the workspace configuration against our internal secret-handling policy. The goal is to identify any gaps or violations and document the findings in the appropriate compliance follow-up task.

## What You Need to Do

1. **Retrieve the policy**
   - Use the knowledge base standard mock API to search for the secret-handling policy.
   - The official article is **KB-SEC-001 — Secret Handling Policy**. Read its full body to understand the requirements.

2. **Review the workspace configuration**
   - Open and read `configuration_summary.md`, which contains a summary of the current workspace configuration items.
   - Compare each item against the policy you retrieved. Take note of any mismatches, plaintext tokens, unrestricted permissions, or other items that appear to violate the policy.

3. **Update the compliance follow-up task**
   - Access the taskboard task **TASK-1001 — Compliance Follow-up: Secret Handling Audit**.
   - Update its description with a concise summary of your findings. Include specific examples of any configuration items that do not meet the policy requirements.
   - Change the task status from "open" to "reviewed" to indicate the audit is complete.

## What You Don’t Need to Do

- Do not modify any actual configuration files; this is a review and documentation exercise only.
- Do not create new tasks; the follow-up task already exists and only needs to be updated.

If you follow these steps you will complete the audit correctly.