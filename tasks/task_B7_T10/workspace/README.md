# Support Ticket KB Research

Welcome, support agent! This workspace is set up to help you research a customer ticket using the knowledge base and record your findings.

## Task Overview
1. **Retrieve the ticket** – Use the ticketing mock API to fetch ticket `TKT-1042`.
2. **Look up the resolution article** – Use the knowledge base mock API to fetch article `KB-ART-305`.
3. **Understand the issue** – The ticket describes a customer problem; the article contains the recommended resolution steps.
4. **Draft a reply note** – Summarise the resolution steps clearly and politely in a note suitable for the customer.
5. **Mark the ticket as researched** – Call the ticketing mock API to update ticket `TKT-1042` with the tag `kb-reviewed`.
6. **Output the final reply note** – Provide the draft reply note in your response so it can be sent to the customer.

## Available Tools
- **Standard mock API skills/endpoints** for the `ticketing` and `knowledge_base` services.
  - `/ticketing/tickets/get` – retrieve ticket details by ticket ID.
  - `/ticketing/tickets/update` – update ticket fields (e.g., add a tag).
  - `/knowledge_base/articles/get` – retrieve an article body by article ID.
- Workspace files (README.md, SUPPORT_POLICY.md, notes.md) – you may read them for additional context and use `notes.md` as a scratchpad.

## Expected Outcome
A concise customer-facing reply note that reflects the resolution steps from `KB-ART-305`, and a confirmed `kb-reviewed` tag on `TKT-1042`.

If anything is unclear about the ticket or article, feel free to re-read them before drafting. Happy helping!