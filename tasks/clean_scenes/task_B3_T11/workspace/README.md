# Dependency Audit Workspace

This workspace holds materials for the dependency audit remediation effort. The audit identified several outdated packages, and the team needs a clear, actionable remediation plan aligned with our standard policy.

## What's Here

- `dependency_findings.md` — A list of outdated dependencies and recommended target versions.

## Task Outline

1. **Review findings** – Open `dependency_findings.md` and note the packages that require updates and their recommended versions.
2. **Consult policy** – Use the knowledge base skill to search for the "dependency policy" article, then retrieve the full article (it is KB-DEPS-01) to understand the standard upgrade process, approval gates, and timing guidelines.
3. **Build remediation plan** – Create `workspace/remediation_plan.md` with a concise, step-by-step plan that follows the policy while addressing each finding.
4. **Update ticket** – Using the ticketing skill, get ticket TICKET-421 and update its priority (e.g., raise to "high" if warranted) and set tags that summarize the key actions from the plan (e.g., `upgrade`, `security`, `dependency`). **Do not close the ticket**—only update its priority and tags.

## Available APIs

- **Knowledge base** — standard mock skill for search and article retrieval.
- **Ticketing** — standard mock skill for reading and updating tickets.

Use the normal mock API endpoints for all operations.