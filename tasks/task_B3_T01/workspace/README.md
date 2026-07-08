# Inbox Triage and Digest

This workspace contains a policy for triaging incoming mailbox messages and preparing an internal digest for the Leadership team.

## What to do

1. Read `policy.md` to understand the triage rules, priority definitions, and the digest recipient list.
2. Use the **mailbox** mock API to retrieve and inspect inbox messages. Identify which messages are high-priority according to the policy.
3. Use the **directory** mock API to look up the exact contact details for the digest recipients specified in the policy (e.g., "Leadership Team").
4. Compose an internal draft digest summarizing the high-priority items, and save it as a draft via the **mailbox** API. Do not send the message.

## Available services

- **mailbox** – Standard mock API endpoints for listing, fetching, and drafting messages.
- **directory** – Standard mock API endpoints for searching and looking up team or contact entries.

Do not send any messages; only save the digest as a draft.