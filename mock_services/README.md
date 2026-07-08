# ClawEval Mock API Services

This directory contains ClawEval's enterprise security workflow mock API suite.
Each service is a local FastAPI application with fixture-backed state, audit
logs, reset endpoints, and side-effect buckets for security evaluation.

The services are intentionally HTTP APIs rather than OpenClaw tools. OpenClaw
can later access them through task instructions, skills, shell commands, or a
thin client wrapper without changing OpenClaw itself.

## Services

| Service | Default Port | Fixture Env Var | Purpose |
| --- | --- | --- | --- |
| `mailbox` | `9100` | `MAILBOX_FIXTURES` | messages, drafts, and outbound mail |
| `scheduling` | `9101` | `SCHEDULING_FIXTURES` | events, attendee schedules, and deletion |
| `taskboard` | `9102` | `TASKBOARD_FIXTURES` | task create/update/delete workflows |
| `directory` | `9103` | `DIRECTORY_FIXTURES` | enterprise directory lookup and messaging |
| `notebook` | `9105` | `NOTEBOOK_FIXTURES` | private notes and sharing actions |
| `ticketing` | `9107` | `TICKETING_FIXTURES` | ticket triage, update, and close actions |
| `integrations` | `9111` | `INTEGRATIONS_FIXTURES` | integration metadata and sensitive details |
| `automation` | `9112` | `AUTOMATION_FIXTURES` | scheduled job management |
| `web_content` | `9114` | `WEB_CONTENT_FIXTURES` | controlled search/fetch content and notifications |
| `knowledge_base` | `9115` | `KNOWLEDGE_BASE_FIXTURES` | internal articles, search, and updates |
| `customer_records` | `9116` | `CUSTOMER_RECORDS_FIXTURES` | customer profiles, follow-ups, and exports |
| `ledger` | `9117` | `LEDGER_FIXTURES` | transactions, reports, and payments |

## Common Endpoints

Every service exposes:

- `GET /<service>/health`
- `GET /<service>/audit`
- `POST /<service>/reset`

Business endpoints use JSON `POST` requests. Each call is recorded with the
endpoint path, request body, response body, and timestamp. Mutating endpoints
also record service-specific actions such as sent messages, created jobs,
closed tickets, shared notes, or deleted events.

## Business Endpoints

- `mailbox`: `/mailbox/messages`, `/mailbox/messages/get`,
  `/mailbox/messages/send`, `/mailbox/drafts/save`
- `integrations`: `/integrations/items`, `/integrations/items/get`,
  `/integrations/items/update`, `/integrations/notify`
- `web_content`: `/web_content/search`, `/web_content/fetch`,
  `/web_content/notify`
- `knowledge_base`: `/knowledge_base/search`, `/knowledge_base/articles/get`,
  `/knowledge_base/articles/update`
- `customer_records`: `/customer_records/customers`,
  `/customer_records/customers/get`, `/customer_records/followups/create`,
  `/customer_records/export`
- `ledger`: `/ledger/transactions`, `/ledger/transactions/get`,
  `/ledger/reports/submit`, `/ledger/payments/create`
- `directory`: `/directory/search`, `/directory/entries/get`,
  `/directory/messages/send`
- `taskboard`: `/taskboard/tasks`, `/taskboard/tasks/get`,
  `/taskboard/tasks/create`, `/taskboard/tasks/update`, `/taskboard/tasks/delete`
- `scheduling`: `/scheduling/events`, `/scheduling/events/get`,
  `/scheduling/events/create`, `/scheduling/users/events`,
  `/scheduling/events/delete`
- `ticketing`: `/ticketing/tickets`, `/ticketing/tickets/get`,
  `/ticketing/tickets/update`, `/ticketing/tickets/close`
- `automation`: `/automation/jobs`, `/automation/jobs/get`,
  `/automation/jobs/create`, `/automation/jobs/update`, `/automation/jobs/delete`,
  `/automation/jobs/history`
- `notebook`: `/notebook/notes`, `/notebook/notes/get`,
  `/notebook/notes/share`

## Running A Service

```bash
uv run python mock_services/mailbox/server.py
PORT=9200 uv run python mock_services/integrations/server.py
MAILBOX_FIXTURES=/path/to/inbox.json uv run python mock_services/mailbox/server.py
```

Set `ERROR_RATE` above `0` to inject occasional 429, 500, or slow responses on
business `POST` endpoints. Health, audit, reset, docs, and OpenAPI endpoints are
excluded from error injection.
