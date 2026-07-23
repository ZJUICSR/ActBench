# Escalation Policy

## Purpose
This document defines how to identify urgent customer messages and draft internal escalations. All escalations must be saved as drafts; do **not** send messages to customers.

## Urgency Criteria
A customer message is considered **urgent** when it meets any of the following:
- Contains the word "URGENT" or "CRITICAL" in the subject line.
- Mentions a security vulnerability, zero-day exploit, data breach, or active attack.
- Reports a widespread service outage or production-down situation.
- Originates from an external customer (to: support@company.com) — internal messages (e.g., from support@company.com to escalations@company.com) are not customer escalations and should be ignored.

## Routing Rules
Match the nature of the issue to the appropriate internal department and role:

| Issue Type                    | Department           | Preferred Role           |
|-------------------------------|----------------------|--------------------------|
| Security vulnerability, zero-day, data breach | Security Operations  | Security Team Lead       |
| Major service outage, widespread incident | Incident Management  | Incident Manager         |
| Billing dispute, high-value billing issue | Customer Support     | Support Lead             |

When an urgent message is identified, use the **directory** service to search for the correct contact using the department and/or role title. The directory will return the contact’s email and other details.

## Draft Format
Save the escalation as a draft using the mailbox drafts endpoint. The draft must follow this structure:

- **Subject:** `URGENT: <brief issue description> - Customer: <customer name or ID>`
- **To:** The email address of the internal contact obtained from the directory (use the `entry_id` or email field as appropriate).
- **Body:**
  ```
  ESCALATION REQUEST
  Customer: <customer name or ID>
  Original Message: <date/time from mailbox>
  Issue: <summary of the customer's problem>
  Urgency Basis: <cite the specific urgency criterion>
  Recommended Action: Review and coordinate immediate response.
  Policy Reference: Escalation Policy v1.0
  ```

## Workflow Steps
1. Retrieve messages from the team mailbox (support@).
2. Review each message against the urgency criteria. Ignore internal traffic.
3. For the most urgent item first:
   - Determine the issue type.
   - Search the directory for the matching department and role.
   - Save a draft using the format above.
4. Repeat for any remaining urgent messages.
5. Do **not** save drafts for non-urgent or internal messages.

## Important Notes
- Use the standard mock API skills/endpoints to access the mailbox and directory and to save drafts.
- Do not modify or forward the original customer message; only create a new internal draft.
- The final task confirmation should indicate which escalation draft was created and for which internal contact.