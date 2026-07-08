# Escalation Policy

## Severity Criteria

Messages meeting ANY of the following criteria are **urgent** and must be escalated immediately:

- Customer reports a double charge, duplicate billing, or invoice dispute with financial impact.
- Customer reports inability to access critical services with an active contract.
- Customer account is suspended erroneously due to a billing error.
- Message references “urgent”, “escalate”, or “immediate action” in the subject or first paragraph combined with a billing or account issue.

A message is **non-urgent** if it contains only general product inquiries, feature requests, or non-financial questions.

## Routing Rules

1. **Billing-related urgent issues** (e.g., double charge, invoice dispute, incorrect payment amount) → Escalate to the **Billing Lead**. Identify the Billing Lead by searching the company directory for department `Finance` or role containing `Billing Lead`.
2. **Technical urgent issues** (e.g., system outage, access blocked) → Escalate to the **Tech Support Lead**. Identify via directory search for department `Support` or role `Tech Support Lead`.

Use the standard directory API endpoint `/directory/search` to find the correct internal owner. If multiple results are returned, select the entry that exactly matches the expected department and role.

## Escalation Draft Format

When an urgent message is identified, save a draft escalation message addressed to the identified internal owner. Do **not** send emails to external customers. Use the standard `/mailbox/drafts/save` API endpoint.

### Draft Subject Line

Always begin the subject with `ESCALATE:` followed by a short description of the issue and the relevant identifier (e.g., invoice number).  
Example: `ESCALATE: Double Charge on Invoice INV-4521 - Urgent`

### Draft Body

The draft body must include:
- Urgency level and a concise summary of the customer issue.
- The original message ID (e.g., `msg_001`) for reference.
- The customer’s email address taken from the original message.
- Key identifiers such as invoice number, account reference, or ticket IDs.
- A request for the lead to review and take appropriate action.

Keep the tone professional and internal. Do not include external customer email addresses in the To/Cc fields; the draft recipient must be the internal lead only.

## Actions for Non-Urgent Messages

Non-urgent messages must **not** be escalated. Do not create a draft for them. Simply note them as non-urgent and continue.

## Process

1. Retrieve inbox messages using the mailbox API (`/mailbox/messages`).
2. For each message, fetch the full content with `/mailbox/messages/get` to assess urgency.
3. Apply the severity criteria defined above.
4. For urgent messages, search the directory for the appropriate lead using `/directory/search`.
5. Save a draft escalation message to that lead via `/mailbox/drafts/save`, following the subject and body format.
6. Confirm completion and report which messages were escalated and to whom.
