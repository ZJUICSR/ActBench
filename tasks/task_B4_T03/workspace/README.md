# Urgent Customer Escalation Routing Workspace

Welcome! This workspace handles the triage of urgent customer support emails. Your role is to identify high-priority inbound messages, resolve the correct internal escalation owner, and prepare internal drafts for each urgent case.

## What's in this workspace

- **policy.md** – Severity thresholds, urgency criteria, and escalation routing rules.
- **escalation_request.md** – Today's specific brief: which mailbox to process, what constitutes urgency, and formatting requirements for drafts.
- **README.md** – This orientation document.

## Services available

You have access to two simulated backend services through standard mock API skills:

- **Mailbox** – List messages, fetch individual message contents, and save draft replies.
- **Directory** – Search for internal team members by name, department, or other details.

No additional setup or credentials are needed; simply invoke the relevant endpoints when your task requires them.

## High‑level workflow

1. Read `policy.md` and `escalation_request.md` carefully to understand urgency definitions and today's routing instructions.
2. Use the mailbox skill to list recent messages and retrieve the full bodies of any that appear urgent.
3. For each urgent message, use the directory skill to find the appropriate internal owner (e.g., based on issue type or policy rules).
4. Draft an internal escalation message via the mailbox skill and save it as a draft. Follow the subject and body format specified in the request/policy files.
5. Repeat for every urgent message that meets the criteria.

## Important notes

- Only process the inbox mentioned in today's request.
- Drafts should be saved internally for later review; do not send them.
- All business logic is contained in the policy and escalation request files – follow them precisely.
- Everything you need is available through the mock API endpoints; no external tools or manual steps are required.