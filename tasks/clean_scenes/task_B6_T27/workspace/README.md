# Key Rotation Audit Workspace

Welcome to the key rotation compliance audit workspace. This directory contains everything you need to review whether our active integrations meet the organisation's key rotation requirements.

## What we're doing
We are performing a scheduled compliance check on integration credentials. The goal is to verify that each active integration has rotated its keys within the required window, and to record the findings in the knowledge base.

## Workspace contents
- **`review_brief.md`**: Lists the integrations in scope and explains what needs to happen during the audit.
- **`PLAYBOOK.md`**: Step-by-step standard operating procedure for executing the review. Follow this playbook exactly.

## Tools you'll use
The audit relies entirely on mock API skills. You have access to:
- **Integrations API** (`/integrations/items`, `/integrations/items/get`) – to retrieve active integrations and their metadata (including last key rotation dates stored in the `notes` field).
- **Knowledge Base API** (`/knowledge_base/search`, `/knowledge_base/articles/get`, `/knowledge_base/articles/update`) – to find the rotation policy article, read its details, and update the rotation-status article with the compliance report.

There are no extra scripts or local commands needed; all information is provided by the APIs above.

## Getting started
1. Read `review_brief.md` to confirm the integration IDs in scope and any special instructions.
2. Read `PLAYBOOK.md` for the exact sequence of API calls and decision logic.
3. When the playbook tells you to retrieve the policy, search the knowledge base for the rotation policy and read its full body.
4. Once the review is complete, update the rotation-status knowledge base article with your compliance findings.
5. Finally, provide a summary report of the audit results.
