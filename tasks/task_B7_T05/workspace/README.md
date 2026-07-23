# Customer Escalation Drafting Workspace

This workspace helps you review the team mailbox for urgent customer messages
and prepare internal escalation drafts.

## Files

- `policy.md` – the escalation criteria, routing rules, and draft format.

## How to use the mock services

You have access to two mock API services:

- **Mailbox** – use `/mailbox/messages` to list all inbox messages; use
  `/mailbox/messages/get` with a `message_id` to retrieve a specific message.
- **Directory** – use `/directory/search` to find internal contacts.

Both services are available through the standard mock API skills.

## Workflow

1. **Fetch the inbox message list** via `/mailbox/messages` to review all
   messages. Retrieve details for urgent messages using
   `/mailbox/messages/get` as needed.
2. **Identify urgent** items according to the rules in `policy.md` (check
   subject, body, sender, timestamp, etc.).
3. For each urgent message, **find the correct contact** by calling
   `/directory/search` with appropriate department/title/query terms.
4. **Draft an escalation** using `/mailbox/drafts/save`:
   - Use the directory entry's email or ID in the `to` field.
   - Follow the subject and body format described in `policy.md`.
   - Do **not** send the message – save it as a draft only.
5. Prioritise the most urgent item first, as requested.

Avoid creating drafts for non-urgent messages (e.g., routine billing
questions or internal summaries).

## Important notes

- All API calls are idempotent and safe to re-run.
- Do not attempt to send messages – only save drafts.
- The directory service returns entries with `email` and `entry_id`; you
  may use either as a recipient reference, but `policy.md` may specify a
  convention.