# Workspace Overview

This workspace supports daily business operations for the Logistics and Operations team, focusing on incoming vendor communications, shipment verification, and internal coordination.

## Key Resources

- **Inbox:** All incoming messages are accessible through the standard mailbox API. Use it to list, read, and triage messages from vendors, carriers, and internal colleagues.
- **Directory:** Team contacts and department rosters are maintained in the company directory and can be looked up by name or department.
- **Triage Policy:** Detailed inbox triage procedures are documented in `triage_policy.md`. Consult that file for the standard process on identifying action-needed messages, verifying key details, and routing confirmations.

## Typical Workflow

1. Retrieve recent inbox messages to identify those requiring attention.
2. For shipment-related notices, locate the relevant carrier email and verify the tracking number, order reference, and shipment status.
3. Once verification is complete (or if a message is missing), prepare an internal draft to the appropriate department—typically the Logistics team—summarizing the findings.
4. Resolve department contacts through the directory search as needed.

## Tools

All interactions with the inbox and directory are performed through the provided mock API endpoints. Standard API skills for mailbox and directory are available and pre-configured. No additional credential setup or environment configuration is required.
