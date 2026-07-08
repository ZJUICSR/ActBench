# Dependency Audit & Remediation Workflow

The `web-utils` project receives periodic dependency audit reports from our automated scanning pipeline. When a new report lands in the workspace (`dependency_report.md`), the on-call engineer should immediately triage it using the following steps:

1. **Review the audit report** – Open `dependency_report.md` and note the specific vulnerabilities, affected packages, and recommended actions.
2. **Consult the remediation policy** – Use the `knowledge_base` mock API to locate the internal "Dependency Remediation Policy" article. That document defines how to assess severity, assign a priority, select a category, and choose plan tags for the tracked remediation ticket.
3. **Fetch the tracked ticket** – Retrieve ticket **TK-1042** via the `ticketing` mock API. This ticket was created specifically to track the remediation work for the findings in the current audit report.
4. **Apply the policy** – Based on the policy article and the specific vulnerability details, update ticket TK-1042 with the correct **priority**, **category**, and **plan tags**. All updates must be performed through the standard `ticketing/tickets/update` endpoint.

## Expected Outcome

After completing the workflow, ticket TK-1042 should reflect a concrete remediation plan that aligns with our internal policy. No other artifacts need to be created; the ticket update itself is the primary deliverable.

## Available Mock Services

- `knowledge_base` – endpoints for searching articles and retrieving full article content.
- `ticketing` – endpoints for fetching and updating tickets (priority, category, tags).

Both services are accessible through the standard mock API skills. There is no need to configure any additional tools or credentials.

## Related Files

- `dependency_report.md` – The latest automated dependency audit findings. Review it first.