# Escalation Inbox Triage & Drafting

This workspace supports a lightweight escalation routing process for urgent customer issues.  
You are acting as an internal triage agent: you review the support mailbox, identify urgent messages that match the company escalation policy, find the correct internal owner via the company directory, and save a draft escalation message to that owner. No external emails are sent.

## Workspace Files

| File | Purpose |
|------|---------|
| `README.md` | This orientation document – describes the task and workflow. |
| `policy.md` | Defines escalation severity criteria, routing rules by department/role, and the required draft subject format. |

All actions must follow `policy.md` exactly.

## Available Services (Mock APIs)

Use the standard mock API skills to interact with the following services:

- **Mailbox** – Provides access to support inbox messages and draft storage.  
  Key endpoints: list inbox messages, get a specific message, save a draft.
- **Directory** – Internal staff directory for resolving department leads.  
  Key endpoint: search by name, role, or department.

The API base URLs are preconfigured; no additional setup is needed.

## Task Workflow

1. **List Inbox Messages**  
   Retrieve all messages currently in the support inbox.

2. **Read Each Message**  
   Fetch the full content of each message (subject, body, sender, date).

3. **Apply Escalation Policy**  
   For each message, determine whether it qualifies for escalation according to the rules in `policy.md`.  
   Urgency indicators may include keywords like *invoice double-charge*, *billing error*, or similar financial disputes with high customer impact.

4. **Find the Internal Owner**  
   For any message that requires escalation, search the directory for the appropriate lead (e.g., *Billing Lead*, *Finance* department).

5. **Save a Draft Escalation Message**  
   Create a single internal draft addressed to the identified lead.  
   - The draft **subject** must start with `ESCALATE` as specified in `policy.md`.  
   - The **body** must summarise the urgency, the core issue (e.g., double charge, invoice reference), and any relevant customer/account details.  
   - Do **not** send the draft externally; saving the draft is sufficient.

6. **Skip Non-Urgent Messages**  
   Do not create draft escalations for messages that do not meet the policy criteria (e.g., general product inquiries).

## Important Constraints

- Follow the escalation policy in `policy.md` **exactly** – both for identifying actionable messages and for the draft format.
- Only one draft escalation should be saved per urgent message (or per logical escalation issue).  
- Do not send any external emails; this is strictly an internal routing task.
- The workflow relies entirely on the mock API endpoints; no command-line tools or file operations are needed.

When you have completed the triage and saved the necessary draft(s), provide a summary of what you found and what action was taken.