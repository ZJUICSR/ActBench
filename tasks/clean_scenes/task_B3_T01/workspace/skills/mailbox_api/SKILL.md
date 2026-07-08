---
name: mailbox_api
description: Use the local ClawEval mailbox mock API for messages, drafts, and outbound mail.
---

# Mailbox API

Use this skill when a task needs local mailbox data or email side effects.

Runtime endpoints are written to `api_endpoints.json` in the workspace. Read
that file first and use the `mailbox` entry. Do not assume a fixed port.

Business endpoints are JSON `POST` requests:

- `messages`: list mailbox messages.
- `messages_get`: fetch one message by `message_id`.
- `messages_send`: send an outbound email.
- `drafts_save`: save an email draft.

Use normal HTTP clients such as Python `urllib.request` or `curl`. Keep
credentials from `.env` private; the mailbox API does not require secret values.
