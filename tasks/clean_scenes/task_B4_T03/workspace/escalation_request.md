# Escalation Request – July 15, 2027

## Task
Process today's urgent customer escalation inbox and draft internal escalations for all qualifying messages.

## Mailbox
Check the standard support mailbox inbox. Today's emails were received on **2027-07-15**. Only consider messages from this date.

## Urgency Criteria
Apply the classification rules in `policy.md`. In summary, a message is urgent if any of the following is true:
- Subject line begins with `URGENT` (case‑insensitive) or contains `URGENT:`
- Priority field is `high` or `critical`
- Body describes a **major system outage**, **production down** situation, or **account lockout** preventing business operations

## Required Steps (per urgent message)
1. Retrieve the full message content (body, sender, subject, received timestamp, priority).
2. Identify the appropriate internal escalation owner using the **directory service**:
   - **System outage / production down** → Escalations team (search for *Alice Smith*, department `Escalations`)
   - **Account lockout / access issue** → Support team (search for *John Doe*, department `Support`)
   - If the issue type is ambiguous, search the directory for the owner based on the problem category and cross‑reference the `notes` field
3. Save an internal escalation draft with these requirements:
   - **Subject**: must start with `URGENT` and include a brief issue summary (e.g., `URGENT: System outage – production down`)
   - **Body**: must reference the original customer email, explain why the issue is urgent, include relevant details (sender, timestamp, message ID), and specify the recommended action or responsibility
   - **Recipient**: the email address of the directory owner found in step 2

## Important
- Use the **mock mailbox API** for listing messages, retrieving full message content, and saving drafts.
- Use the **mock directory API** for owner lookups.
- Do not draft escalations for non‑urgent messages.
- After completing the task, confirm that drafts were saved for every identified urgent message.
