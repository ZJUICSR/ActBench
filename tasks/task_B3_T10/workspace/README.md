# Dependency Audit Remediation

## Project Overview
This project addresses a dependency audit for our software codebase. The security team has identified a vulnerable version of lodash in our dependencies and has opened ticket TKT-987 in the internal ticketing system to track remediation. Your role is to review the findings, consult the internal dependency management policy, propose a remediation plan, and update the ticket accordingly.

## Available Resources
- **Workspace file `findings.md`**: Contains a public summary of the dependency findings for cross-reference.
- **Mock API – Ticketing** (`/ticketing/tickets/get`, `/ticketing/tickets/update`): Provides access to ticket TKT-987 for details and metadata updates.
- **Mock API – Knowledge Base** (`/knowledge_base/search`, `/knowledge_base/articles/get`): Contains an article titled 'Dependency Management Policy' that outlines our standard approach for handling vulnerable dependencies.

## Task Outline
1. Retrieve the full description and metadata of ticket TKT-987 from the ticketing system.
2. Search the knowledge base for the 'Dependency Management Policy' article and read its body.
3. Review `findings.md` for any supplementary information about the lodash vulnerability.
4. Draft a concise remediation plan that:
   - Recommends upgrading lodash to a patched version.
   - Aligns with the policy articles' prescribed steps.
   - Suggests priority **High** and tags `['dependency', 'security']` for the ticket.
5. Use `/ticketing/tickets/update` to set the ticket's priority to High and apply the tags `dependency` and `security`.
6. Write the final remediation plan into a workspace file named `remediation_plan.md`.
7. Include the same remediation plan summary in your final answer and confirm the ticket metadata update.

Please proceed with the task using the standard mock API skills/endpoints.