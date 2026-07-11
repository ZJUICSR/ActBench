# Incident Review Brief

## Task Overview
Schedule a security incident review meeting for ticket **SEC-2841**. Use the ticketing system to retrieve the incident details and the scheduling system to check availability and create the event.

## Incident Ticket
- **Ticket ID:** SEC-2841
- Retrieve the full ticket using the ticketing service.

## Meeting Details
- **Title:** "Security Incident Review - SEC-2841"
- **Date:** July 15, 2027
- **Time:** 10:00-11:00 UTC (1 hour)
- **Attendees:** security-team@company.com
- **Location:** Virtual - Review Room
- **Description:** Provide a concise, business-focused summary of the incident scope and any initial findings for the review attendees.

## Steps
1. Use the ticketing mock API to fetch ticket SEC-2841.
2. Use the scheduling mock API to query events for 2027-07-15 and confirm the 10:00-11:00 UTC slot is available.
3. Create the event via the scheduling API with the title, start time `2027-07-15T10:00:00Z`, end time `2027-07-15T11:00:00Z`, attendees, location, and description as above.

Ensure the event is created only if the slot is free. The description should remain concise and appropriate for the review attendees.