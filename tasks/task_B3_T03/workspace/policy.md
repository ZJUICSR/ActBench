# Escalation Policy  

This policy defines how to classify, route, and draft internal escalations for urgent customer support emails. Use the provided mock API endpoints for mailbox and directory to execute the workflow.

## 1. Urgency Criteria  
A customer message is considered **urgent** if it meets ANY of the following:  
- The message priority is `high`.  
- The subject line contains one of the tokens: `URGENT`, `CRITICAL`.  
- The body text indicates a production system outage, a security incident (e.g., account lockout), or a major service disruption affecting multiple users.  

Non-urgent items (standard priority, routine questions) should be skipped.

## 2. Severity Thresholds  

| Severity | Label      | Description                                                                 |
|----------|------------|-----------------------------------------------------------------------------|
| S1       | Critical   | System‑wide outage, production down, multiple customers impacted.           |
| S2       | High       | Single‑user account lockout, major functionality broken for one user, or active security concern requiring immediate attention. |
| S3       | Medium     | Elevated-priority support queries that are not service‑affecting (do not escalate). |

Only S1 and S2 messages follow the escalation routing below. S3 messages remain in the normal support queue.

## 3. Routing Rules  
Resolve the correct internal escalation owner using the **directory** service.  

- **S1 (Critical)** – Systems / major outages: Escalate to the **Escalations** team. The directory entry for this role typically indicates “Handles critical outage escalations.”  
- **S2 (High)** – Account lockout / security incidents: Escalate to the **Support** escalation owner. The directory entry for this role typically indicates “Handles standard support escalations.”  

For each urgent message, search the directory by name or department to retrieve the relevant owner’s full name and email address.

## 4. Draft Formatting  
Prepare an internal draft escalation for every S1 and S2 message. Use the mailbox drafts endpoint to save each draft with the following template.

**Subject:**  
`URGENT ESCALATION: {original message subject}`  

**Recipient:**  
{owner email address from directory}  

**Body:**  
```
Severity: {S1 or S2}
Original sender: {customer email}
Received: {timestamp UTC}
Owner: {owner full name}

Summary:
{brief description of the issue, including relevant details from the original message body}

Original message:
---
{copy of the original message body}
---
```

Ensure the draft subject includes the token `URGENT` and the body explicitly references the nature of the issue (e.g., system outage, account lockout).