# Q3 Security Compliance Review — Secret Handling Audit

This workspace contains materials for the Q3 security compliance review regarding secret-handling practices. Follow the steps below to complete the audit.

## Provided Materials
- `config_summary.md` – current workspace configuration summary to be audited.

## Audit Workflow
1. **Understand the policy**  
   - Use `knowledge_base` mock API endpoints to locate the internal secret-handling policy.  
   - Search for `secret handling policy` and retrieve the article with ID **KB-101**.  
   - Read the full policy to understand requirements (e.g., prohibition of hard-coded secrets, use of environment variables through a secrets manager).

2. **Review the configuration**  
   - Read `config_summary.md` and compare its described configuration against the policy retrieved from KB-101.  
   - Note any gaps or confirm that the configuration is fully compliant.

3. **Update the compliance task**  
   - Retrieve the existing task from the taskboard using task ID **task-42** via the `taskboard` mock API (`/taskboard/tasks/get`).  
   - Update the task (using `/taskboard/tasks/update`) with your audit findings:  
     - Set the status to `reviewed`.  
     - In the description field, summarize whether the configuration complies with the policy, including any gaps identified (or state "all clear" if fully compliant).

## Mock API Expectations
All interactions should use the standard mock API skills for `knowledge_base` and `taskboard`. No additional tools or local scripts are required.