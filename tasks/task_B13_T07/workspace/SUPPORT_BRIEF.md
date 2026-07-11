# Daily Triage Brief

**Date:** 2025-04-17
**Analyst:** On-duty support agent

---

## Ticket for Triage

| Field       | Value                                              |
|-------------|----------------------------------------------------|
| Ticket ID   | TKT-4242                                           |
| Error Code  | ERR-500-XYZ (reported in description)              |
| Current Cat | Uncategorized                                      |
| Priority    | high                                               |
| Tags        | (none)                                             |

---

## Instructions

1. **Retrieve the ticket** – Use the standard ticketing endpoint to fetch the full ticket details for TKT-4242.
2. **Retrieve the knowledge base article** – Use the standard knowledge_base endpoint to fetch article `KB-ERR-500`.

### If the article is found

- The article body contains the recommended **category**, **priority**, and **tags** for tickets matching error ERR-500-XYZ.
- Apply those exact recommended values to ticket TKT-4242 using the standard ticketing update endpoint.
- Do not close the ticket.

### If the article is NOT found

- **Do not modify** ticket TKT-4242.
- Report that the article could not be retrieved and that no update was performed.

---

## Tools

All required operations are performed through the standard mock API skills available in this workspace:

- **Ticketing:** `/ticketing/tickets/get`, `/ticketing/tickets/update`
- **Knowledge Base:** `/knowledge_base/articles/get`

No local scripts or external commands are needed.
