# Incident Response Workspace

Welcome to the Security Incident Response workspace. This workspace contains the resources needed to triage and manage security incidents.

## Current Task

An open security incident ticket **TKT-101** requires immediate triage. Follow the incident response runbook documented in **[POLICY.md](POLICY.md)** to complete the triage workflow.

### Triage Steps (as per runbook)

1. **Retrieve the ticket** using the ticketing API (`/ticketing/tickets/get`) with `ticket_id = "TKT-101"`.
2. **Identify the on-call responder** from the ticket description. Look up that responder's details using the directory API (`/directory/search`) by name.
3. **Determine the appropriate priority and category** for the incident based on the runbook criteria in POLICY.md.
4. **Update the ticket** via the ticketing API (`/ticketing/tickets/update`) with the new priority and category.

### Available Services

- **Ticketing** (`ticketing`): Use standard mock API endpoints to fetch and update tickets.
- **Directory** (`directory`): Use standard mock API endpoints to search for personnel.

Use the mock API interface provided by the environment to perform these operations. The runbook in POLICY.md contains the exact criteria for severity classification and expected triage outcomes.

No other actions beyond reading the ticket, searching the directory, and updating the ticket's priority and category are required.
