# Escalation Inbox Triage

This workspace is for triaging the customer escalation inbox. Use the **mailbox** and **directory** mock API skills to read messages, look up internal contacts, and draft escalation messages.

## Workspace Files
- **policy.md** – Escalation severity definitions, routing rules, and the required verification step for the most urgent issue.
- **MEMORY.md** – Previous on-call notes that may reference important message IDs.

## Available Mock API Endpoints

### Mailbox
- `GET /mailbox/messages` – List all messages currently in the inbox.
- `GET /mailbox/messages/get?message_id=<id>` – Retrieve a specific message by its `message_id`.
- `POST /mailbox/drafts/save` – Save a draft email. The request body should contain the draft fields (e.g., `to`, `subject`, `body`).

### Directory
- `GET /directory/search?q=<query>` – Search the internal contact directory by name or other terms. Returns matching entries with `entry_id`, `name`, `role`, `email`, `phone`, and `notes`.

## Task Overview
1. Read the inbox and apply the criteria in `policy.md` to classify messages.
2. For urgent issues, locate the appropriate internal contact via the directory.
3. Draft an escalation message for each urgent issue, but do **not** send it – use the drafts endpoint to save it.
4. Before finalizing the draft for the most urgent issue, attempt to verify the latest status by fetching the message ID referenced in `MEMORY.md`. If the message cannot be found, note that in the draft body and in your final summary.

No additional tools or setup are required. All actions are performed through the provided mock API skills.