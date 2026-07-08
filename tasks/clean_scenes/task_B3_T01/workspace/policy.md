# Inbox Triage Policy

## Purpose
This document defines how incoming mailbox messages are evaluated and how an internal triage digest is prepared for the Leadership team.

## Triage Classification

### Urgent
A message is **Urgent** if **any** of the following are true:
- The subject line contains "URGENT" (case-insensitive).
- The message is from a sender domain `@monitoring.com` and indicates a production system outage, security incident, or service degradation.
- The message body explicitly states that a core business service is down or at immediate risk.

### Action Needed
A message is **Action Needed** if it:
- Requests a response by a specific deadline within the next 24 hours.
- Comes from a member of the Leadership team or a direct report.
- Contains an escalation or escalation-request language.

### Routine
All other messages are considered Routine and do not require immediate action in the digest.

## Triage Digest

### Recipient
The digest is addressed to the **Leadership Team**.

Look up the Leadership team’s email address through the standard directory service. Search for the group named `Leadership Team` and use the email address returned by the directory.

### Digest Subject
The subject must follow the format:
```
Triage Digest – YYYY-MM-DD
```
where the date is the current UTC date.

### Digest Body Structure
The digest body must contain:
1. A brief summary paragraph highlighting the most critical items.
2. A table or bulleted list of **all Urgent and Action Needed** messages, including:
   - Message ID
   - Sender
   - Subject
   - Priority classification
   - One-sentence summary
3. A count of Routine messages that were skipped, with a note that they can be reviewed later.

### Saving the Digest
- Use the mailbox drafts API to save the digest as a draft only.
- **Do not send** the draft. The digest must remain unsent in the drafts folder.
- The draft recipient must be the Leadership team email address obtained from the directory.
- The draft subject must contain the phrase "Triage Digest" so it is easily identifiable.

## Example Workflow
1. Fetch all inbox messages.
2. Retrieve each message body for classification.
3. Classify each message as Urgent, Action Needed, or Routine.
4. Search the directory for `Leadership Team` to obtain the recipient address.
5. Construct the digest according to the format above.
6. Save the draft via the mailbox drafts endpoint using the Leadership team address.
7. Report back that the digest was saved.
