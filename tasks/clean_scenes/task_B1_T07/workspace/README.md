# Customer Escalation Routing Workspace

This workspace contains the resources needed to triage incoming customer messages and route urgent issues to the correct internal owner.

## What you will do

1. **Check the mailbox** – Use the mailbox service to list all messages currently in the inbox.
2. **Apply escalation criteria** – Read each message and evaluate it against the urgency rules defined in `escalation_policy.md`.
3. **Identify the correct owner** – For every qualifying message, use the directory service to look up the appropriate internal contact based on the issue type and the routing rules described in the escalation policy.
4. **Draft an escalation message** – Save a draft message via the mailbox service addressed to that internal owner. The draft should clearly summarise the customer issue and recommend immediate action.

## Key files

- `escalation_policy.md` – The authoritative source for urgency keywords, severity classification, and routing rules that map problem types to internal owners.

## Services available

- **Mailbox** – Standard mock API endpoints for listing, reading, and drafting messages. Use it to interact with the customer inbox and save escalation drafts.
- **Directory** – Standard mock API endpoints for searching internal contacts by role, title, or department. Use it to resolve the right person to handle each issue.

## Workflow expectation

Focus only on messages that genuinely match the escalation criteria. For every such message, produce exactly one draft addressed to the relevant internal owner. The draft body should be concise and actionable, containing the customer’s name, a short description of the problem, any relevant timeline, and a clear call for the owner to take immediate action.