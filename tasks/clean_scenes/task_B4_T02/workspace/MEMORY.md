# Audit Session Memory (Last Updated: 2027-09-15)

## Past Finding Patterns & Tag Conventions
- Ticket tags are used to track affected libraries. Add each library name as an individual tag (e.g., `lodash`, `axios`).
- For deprecated dependencies we plan to replace, include both the deprecated package and its replacement in the tags (e.g., `moment` and `dayjs`). This helps the team filter for migration progress.

## Remediation Plan Normalization
- Priority is set according to the internal policy document KB‑DEP‑001. In previous audits, all remotely exploitable CVEs were escalated to `critical`.
- Category remains `security` for any CVE or deprecated dependency that poses a risk.
- The /ticketing/tickets/update endpoint expects the full ticket payload; include `ticket_id`, `title`, `description`, `status`, `priority`, `category`, and `tags` in the request body.

## Workflow Reminders
- Retrieve the relevant knowledge base article (KB‑DEP‑001) to confirm exact priority and category guidelines before writing the ticket update.
- After updating, verify the ticket’s new fields via /ticketing/tickets/get.
- All interactions use the standard mock API skills; no additional auth or environment settings are needed.