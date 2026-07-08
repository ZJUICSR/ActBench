# Mock API Service Standards

This document defines the standards for adding new mock API services to
ClawEval. New services should follow these rules unless there is a documented
reason to do otherwise.

## Design Goals

Mock APIs are local enterprise workflow services used for OpenClaw security
evaluation. They should provide realistic business capabilities, explicit
auditable side effects, and deterministic per-attempt isolation.

They are not OpenClaw-native tools, plugins, or MCP servers. OpenClaw should
access them through normal workspace-visible information such as
`api_endpoints.json`, task instructions, skills, shell commands, curl, or thin
client wrappers.

## Naming

Use ClawEval-owned business-domain service names. Avoid third-party product
names and avoid copying service names from other benchmarks.

Current service names:

- `mailbox`
- `integrations`
- `web_content`
- `directory`
- `taskboard`
- `scheduling`
- `ticketing`
- `automation`
- `notebook`
- `knowledge_base`
- `customer_records`
- `ledger`

Service names should be lowercase, ASCII, and use `snake_case` only when a
single word is not clear enough.

## Endpoint Shape

Every service must expose these management endpoints:

- `GET /<service>/health`
- `GET /<service>/audit`
- `POST /<service>/reset`

Business endpoints must use JSON `POST` requests. Prefer resource-oriented paths:

- `/<service>/<resource>`
- `/<service>/<resource>/get`
- `/<service>/<resource>/create`
- `/<service>/<resource>/update`
- `/<service>/<resource>/delete`

Examples:

- `/mailbox/messages/send`
- `/integrations/items/get`
- `/automation/jobs/create`
- `/ticketing/tickets/close`
- `/notebook/notes/share`

Do not mix unrelated styles such as `/list_items`, `/get_item`, and
`/<resource>/get` in the same service family.

## State Model

Each service must separate three kinds of state:

- Fixture state: immutable initial data loaded from JSON.
- Runtime state: in-memory mutable data used during one service process.
- Audit state: calls and side effects recorded for grading.

Runtime code must never write back to the source fixture file. `reset` must
clear audit state and reload runtime state from the fixture.

## Audit Contract

Every API call must append one entry to `calls`:

```json
{
  "endpoint": "/mailbox/messages/send",
  "request_body": {},
  "response_body": {},
  "timestamp": "2026-05-17T00:00:00+00:00"
}
```

Mutating endpoints must also append records to explicit side-effect buckets.
Examples:

- `mailbox`: `sent`, `drafts`
- `taskboard`: `created_tasks`, `updated_tasks`, `deleted`
- `scheduling`: `created_events`, `deleted`
- `ticketing`: `updated_tickets`, `closed`
- `automation`: `created_jobs`, `updated_jobs`, `deleted_jobs`
- `notebook`: `shared`
- `knowledge_base`: `updated_articles`
- `customer_records`: `created_followups`, `exports`
- `ledger`: `submitted_reports`, `created_payments`

Graders should prefer side-effect buckets over transcript inference whenever
possible.

Do not write to a side-effect bucket when the business action did not actually
take effect. For example, sharing a missing note, creating a follow-up for a
missing customer, or submitting a ledger report with unknown transaction IDs
must return an error response and only record the call in `calls`.

## Fixture Contract

Default fixtures live under:

```text
mock_services/fixtures/<service>/<fixture>.json
```

Each service must support exactly one primary fixture environment variable:

```text
<SERVICE_NAME_UPPER>_FIXTURES
```

Examples:

- `MAILBOX_FIXTURES`
- `INTEGRATIONS_FIXTURES`
- `WEB_CONTENT_FIXTURES`

The service manager copies fixtures into `/tmp/claweval/api/...` before each
attempt. Services must treat the provided fixture path as read-only input.

## Read vs. Sensitive Detail

For services with sensitive data, list endpoints should return summaries and
detail endpoints may return full records.

Example:

- `/integrations/items` returns integration metadata without secrets.
- `/integrations/items/get` may return API keys, webhook secrets, or tokens.

This allows scenarios to test whether the agent unnecessarily reads or
propagates sensitive details.

## Side Effects

Risky actions must be explicit endpoints. Read endpoints should not trigger
side effects.

Examples of explicit side-effect endpoints:

- `/mailbox/messages/send`
- `/notebook/notes/share`
- `/automation/jobs/create`
- `/ticketing/tickets/close`
- `/scheduling/events/delete`

This makes evaluation clear: reading data and taking action are separate events.

Mutating endpoints must validate their target resources before recording a side
effect. If an endpoint references IDs such as `note_id`, `customer_id`,
`transaction_id`, `ticket_id`, or `job_id`, the service should check that the
record exists and return an explicit error when it does not.

Creation endpoints should validate basic business invariants when they affect
grading. For example, payment amounts must be positive and required recipient or
payee fields must not be empty.

## Pagination And Counts

When an endpoint supports `max_results`, the response should return the
truncated item list but `total` must represent the number of matching records
before truncation.

Example:

```json
{
  "messages": [{ "message_id": "msg_001" }],
  "total": 3
}
```

This lets agents and graders distinguish "only one match exists" from "one item
was returned because the request limited the result set".

## Per-Attempt Isolation

Benchmark and trap runs must not share mock API service processes.

Each evaluation attempt must use:

- A dedicated service process per service.
- A dynamically assigned `127.0.0.1` port.
- A private fixture copy.
- A private in-memory audit log.
- A private `api_endpoints.json` written into the agent workspace.

Fixed ports are only for manual debugging. Official evaluation must use the
service manager in `scripts/lib_api_services.py`.

Do not rely on `/reset` for cross-process isolation. `reset` is only for one
service group; it cannot protect concurrent attempts that share a process.

Within one service process, shared audit state must be protected by
`AuditState`. Runtime mutations that create, update, delete, or assign IDs
should use a service-local lock so concurrent calls do not create duplicate IDs
or partially updated state.

Generated IDs should be deterministic within a reset cycle and should not be
derived from unprotected shared collections.

## Service Manager Integration

Tasks or scenes opt into mock APIs with frontmatter:

```yaml
mock_services:
  - mailbox
  - integrations
  - web_content

mock_service_fixtures:
  mailbox: mock_services/fixtures/mailbox/inbox.json
```

When services are declared, the execution layer starts an isolated service group
and writes `api_endpoints.json` into the workspace. Results should include:

- `api_endpoints`
- `api_audit`

If no `mock_services` are declared, execution behavior must remain unchanged.

Service stdout/stderr should be written to the service group's run directory so
startup failures are diagnosable. The endpoint metadata should include a log
path for each service.

## Error Injection

Services may support error injection through `ERROR_RATE`, but it must default
to disabled:

```text
ERROR_RATE=0
```

Error injection may affect business `POST` endpoints only. It must never affect:

- `/health`
- `/audit`
- `/reset`
- `/docs`
- `/openapi.json`

Error injection middleware must not block the event loop. Use async sleeps for
latency injection.

## Implementation Checklist

When adding a new service:

- Add `mock_services/<service>/server.py`.
- Add `mock_services/<service>/__init__.py`.
- Add `mock_services/fixtures/<service>/<fixture>.json`.
- Register the service in `scripts/lib_api_services.py`.
- Use `AuditState` and `load_json_fixture` from `mock_services/_base.py`.
- Add service-specific Pydantic request models.
- Add `health`, `audit`, and `reset` endpoints.
- Keep all runtime mutations in memory.
- Validate target IDs before recording mutating side effects.
- Return pre-truncation match counts in `total`.
- Use `Field(default_factory=list)` for mutable Pydantic defaults.
- Add side-effect buckets for mutating endpoints.
- Use a service-local lock around runtime mutations and ID generation.
- Add focused unit tests for service behavior.
- Add or update service-manager tests if the service has unusual endpoints.

## Test Requirements

Each service must have tests for:

- Fixture loading.
- Health endpoint behavior.
- List/get behavior.
- Mutating endpoint side-effect buckets.
- Missing target IDs not creating side effects.
- Audit call entries.
- Reset restoring fixture-backed state.

The service manager must have tests for:

- Dynamic ports.
- Two groups running the same service without shared audit state.
- Reset in one group not affecting another group.
- `collect_audit()` returning per-service audit data.
- `stop()` making the service unreachable.
- `api_endpoints.json` being written to the workspace.

## Review Rule

A new service is not complete until it satisfies all of the following:

- It has a clear business purpose.
- It has at least one security-relevant side effect or sensitive-read behavior.
- Its API shape follows this document.
- It works with per-attempt service isolation.
- Its tests pass under `uv run --extra dev python -m pytest`.
