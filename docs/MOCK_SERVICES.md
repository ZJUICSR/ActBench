# ActBench Mock Services

ActBench tasks interact with local fixture-backed FastAPI services. These services provide deterministic business APIs and audit every call for scoring.

The runner starts required services automatically for each task. It allocates local ports, writes endpoint URLs to `api_endpoints.json` in the workspace, collects audit logs after the run, and stops the services.

## Services

The public release includes these services:

- `automation`
- `customer_records`
- `directory`
- `integrations`
- `knowledge_base`
- `ledger`
- `mailbox`
- `notebook`
- `scheduling`
- `taskboard`
- `ticketing`
- `web_content`

Each service has:

- `health` endpoint for readiness checks.
- `audit` endpoint for scoring evidence.
- `reset` endpoint for test isolation.
- Business endpoints documented in `mock_services/README.md` and the corresponding `skills/mock_apis/*/SKILL.md` file.

## Task fixtures

Tasks declare services and fixture files in `task.yaml`:

```yaml
mock_services:
  - ledger
  - ticketing
mock_service_fixtures:
  ledger: fixtures/ledger/transactions.json
  ticketing: fixtures/ticketing/tickets.json
```

At runtime the benchmark copies fixture files into a temporary service directory so task runs do not mutate the repository.

## Runtime endpoint discovery

The runner writes `api_endpoints.json` into the agent workspace. Agent instructions and mock API skills tell the agent to read that file rather than assuming fixed ports.

Example shape:

```json
{
  "ticketing": {
    "base_url": "http://127.0.0.1:49231",
    "endpoints": {
      "tickets": "http://127.0.0.1:49231/ticketing/tickets",
      "tickets_update": "http://127.0.0.1:49231/ticketing/tickets/update"
    }
  }
}
```

## Manual service runs

Manual runs are usually unnecessary, but individual services can be started for debugging:

```bash
uv run python mock_services/ticketing/server.py
PORT=9200 uv run python mock_services/ledger/server.py
```

Use task-specific fixture environment variables when debugging a service outside the benchmark runner; see `mock_services/README.md` for service-specific details.
