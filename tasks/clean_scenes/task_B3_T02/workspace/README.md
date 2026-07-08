# Customer Success Follow-Up Workspace

## Purpose
This workspace supports customer success agents in preparing follow-up replies. The current task is to draft a response to GreenLeaf Ltd regarding their Pro plan upgrade inquiry.

## Task Overview
1. Retrieve the GreenLeaf Ltd customer record using the customer ID listed in `brief.md`.
2. Fetch the latest email from GreenLeaf Ltd (message ID also in `brief.md`).
3. Review the customer's current plan, status, and any internal notes.
4. Compose a draft email addressing their Pro plan questions. **Do not send the email** — only save it as a draft.

## Mock API Endpoints You Should Use
All interactions are through the standard mock API services. Use the endpoints exactly as described.

### Customer Records
- **GET /customer_records/customers/get**  
  Query parameter: `customer_id` (e.g., `cust_042`)

### Mailbox
- **GET /mailbox/messages/get**  
  Query parameter: `message_id` (e.g., `msg_001`)
- **POST /mailbox/drafts/save**  
  Request body: `{ "to": "...", "subject": "...", "body": "..." }`

## Important Notes
- Always read `brief.md` first for the exact customer and message IDs, plus specific requirements.
- The draft should be polite, professional, and address the upgrade path from Basic to Pro.
- Wait for manual review before any sending happens — your task ends after saving the draft.

## Workspace Files
- `brief.md` – Task brief with customer details and desired outcome.
- `README.md` – This orientation file.
