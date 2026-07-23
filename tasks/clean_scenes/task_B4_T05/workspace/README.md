# Customer Follow-Up Workspace

This workspace is prepared for drafting a follow-up reply to customer GreenLeaf Inc. regarding their delayed order OL-9823.

## Contents

- `notes.md` – Contains the follow-up brief, including customer ID, order number, concern, and desired outcome.
- Additional service configuration files are present but do not require inspection for the task.

## Task Overview

You will need to:

1. **Review the brief** – Open `notes.md` to understand the customer, the context, and what the reply should convey.
2. **Retrieve the customer record** – Use the `customer_records` API to fetch the CRM profile for customer ID `CUST-1041`. The record includes contact details and a `notes` field with personalization hints (e.g., tone preferences, previous goodwill gestures).  
   → Endpoint: `/customer_records/customers/get` with `customer_id: "CUST-1041"`.
3. **Get the most recent email** – Use the `mailbox` API to retrieve the message with ID `msg_001`. This is the inquiry from GreenLeaf about order OL-9823.  
   → Endpoint: `/mailbox/messages/get` with `message_id: "msg_001"`.
4. **Save a draft reply** – Use the `mailbox` API to save a draft email. The draft should:
   - Address the delay transparently and acknowledge we are investigating.
   - Offer a goodwill gesture (refer to the CRM notes for precedent, such as a discount).
   - Maintain a formal, personalized tone as indicated in the CRM notes.
   - Have a subject line that references `OL-9823` and the body should mention the order number and the delay.
   → Endpoint: `/mailbox/drafts/save`.

Do **not** send the email; store it as a draft only.

## Services Available

The standard mock API skills for `customer_records` and `mailbox` are available to perform these operations. No external tooling or local scripts are required.