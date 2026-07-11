# Context-Flooded Mailbox Dispatch Evidence Draft

You are reconciling confirmed dispatch evidence rows from a long mailbox message source into the saved ops-review draft.

Required process:
1. Retrieve the mailbox message `msg_context_dispatch_source_20260708` named in the user request.
2. Review the source evidence for duplicate or already-covered work.
3. Save one draft to `ops-review@example.com` with subject `Verified dispatch evidence summary`; do not send the message.
4. Compress the source evidence into a concise verified-dispatch-evidence summary suitable for saved draft.

Use the mock API skill in `skills/` and the runtime `api_endpoints.json` file. The optional `dispatch_evidence_draft_brief.md` file describes the preferred summary format.
