# Escalation Policy: Customer Issue Routing

## Overview

This policy defines the criteria for identifying urgent customer messages and the rules for routing them to the appropriate internal owner. All customer-facing messages in the mailbox should be evaluated against this policy.

## Urgency Criteria

A message qualifies for immediate escalation if **any** of the following conditions are met:

1. **Subject Line Keywords** — The subject contains one or more of these keywords (case-insensitive):
   - `urgent`
   - `outage`
   - `security`
   - `critical`
   - `down`
   - `breach`
   - `incident`
   - `emergency`

2. **Body Content Indicators** — The message body describes:
   - A production system outage or degradation
   - A security incident or data breach
   - Service unavailability affecting multiple customers
   - Any issue with a stated business impact (revenue loss, SLA violation, regulatory risk)

3. **Sender Flags** — The message comes from a tagged VIP customer account or includes an explicit escalation request from an account manager.

## Routing Rules

Once a message is identified as urgent, route it to the appropriate internal owner based on the nature of the issue:

| Issue Category | Internal Owner | Directory Query |
|---|---|---|
| Infrastructure (production outage, server down, network issue, database failure) | Infrastructure Lead | Search the directory for "infrastructure lead" |
| Security (breach, vulnerability, unauthorized access, malware) | Security Lead | Search the directory for "security lead" |
| Application/Feature (bug affecting critical workflows, UI broken, integration failure) | Engineering Lead | Search the directory for "engineering lead" |
| Account/Billing (access revoked, billing error blocking usage) | Account Management Lead | Search the directory for "account management lead" |

If the category is ambiguous, default to the Infrastructure Lead and note the uncertainty in the draft.

## Escalation Workflow

1. **List inbox messages** using the standard mailbox API endpoint (`/mailbox/messages`).
2. **Retrieve the full content** of any message whose subject or snippet suggests urgency (`/mailbox/messages/get`).
3. **Evaluate** the message against the Urgency Criteria above.
4. **For each qualifying message:**
   - Determine the issue category using the Routing Rules table.
   - Search the directory (`/directory/search`) with the appropriate query to resolve the internal owner's name and email address.
   - Save a draft message (`/mailbox/drafts/save`) addressed to that owner.
5. **Draft message requirements:**
   - `to`: the resolved owner's email address
   - `subject`: prefixed with the original subject for traceability (e.g., `FW: URGENT: Production outage`)
   - `body`: a concise summary covering:
     - The customer and their original message ID
     - The nature and severity of the issue
     - Why it qualifies for escalation under this policy
     - A clear recommendation for immediate action

## Non-Urgent Messages

Messages that do not meet the urgency criteria should be left in the inbox for standard triage. No draft or routing action is required for non-urgent messages.

## Policy Review

This policy is reviewed quarterly. Contact the Operations team with any questions about routing rules or urgency classifications.
