# Hermes backend

ActBench can drive Hermes through the `hermes` CLI one-shot mode. The backend launches one isolated `hermes -z` subprocess per task attempt, materializes the task workspace as the subprocess working directory, and records results in the same schema as the other ActBench backends.

The first integration is intentionally ActBench-side only: it does not import Hermes internals or require changes to the Hermes source tree.

## Prerequisites

- Hermes CLI installed and available as `hermes` on `PATH`, or `ACTBENCH_HERMES_BIN` set to the CLI path.
- A Hermes-supported model/provider configured through environment variables. ActBench runs Hermes with an isolated `HERMES_HOME`, so credentials stored only in the user's default `~/.hermes` profile are not read unless exported into the ActBench process environment.
- ActBench dependencies installed with `uv sync` or `pip install -e .`.

## Basic usage

```bash
ACTBENCH_HERMES_PROVIDER=<provider> \
uv run scripts/actbench.py \
  --backend hermes \
  --model <model-id> \
  --suite task_B7_T01 \
  --runs 1
```

`--model` is recorded as the model under test and is passed to `hermes -z --model`. If `ACTBENCH_HERMES_PROVIDER` is set, ActBench also passes `--provider` to Hermes. If it is unset, Hermes resolves the provider using its normal model/provider logic.

## Default MCP mode

By default, the Hermes backend exposes task workspace and mock APIs through the ActBench MCP gateway. For each task attempt, ActBench:

1. Materializes an isolated workspace.
2. Starts any declared mock API services.
3. Registers a high-entropy task `context_id` with the ActBench MCP gateway.
4. Writes an isolated Hermes config under the run-scoped `HERMES_HOME` with:

   ```yaml
   mcp_servers:
     actbench:
       enabled: true
       url: http://127.0.0.1:8765/mcp
   ```

5. Runs `hermes -z` with the task workspace as the subprocess CWD.
6. Prepends instructions telling Hermes to use the ActBench MCP tools with the exact `context_id`.
7. Unregisters the context after the attempt; stale contexts also expire by TTL.

The exposed MCP tools are:

- `actbench_list_files`
- `actbench_read_file`
- `actbench_write_file`
- `actbench_get_api_endpoints`
- `actbench_call_api`

When MCP is enabled, ActBench result payloads sanitize `api_endpoints`: raw mock-service localhost URLs, audit/reset/health/admin paths, fixture paths, and admin tokens are not exposed.

## Environment variables

### Hermes adapter variables

| Variable | Default | Description |
| --- | --- | --- |
| `ACTBENCH_HERMES_BIN` | `hermes` | Hermes CLI executable name or path. |
| `ACTBENCH_HERMES_PROVIDER` | unset | Optional provider passed as `hermes --provider`. |
| `ACTBENCH_HERMES_MODEL` | ActBench `--model` | Optional override for the model passed to Hermes. |
| `ACTBENCH_HERMES_TOOLSETS` | `actbench` when MCP is enabled; unset otherwise | Explicit Hermes `--toolsets` value. The default `actbench` refers to the MCP server configured in the isolated Hermes profile. |
| `ACTBENCH_HERMES_TIMEOUT_SECONDS` | unset | Optional per-subprocess timeout cap. If unset, ActBench uses the task timeout budget. |
| `ACTBENCH_HERMES_HOME_ROOT` | unset | Optional parent directory for run-scoped Hermes homes. |
| `ACTBENCH_HERMES_ENABLE_ACTBENCH_MCP` | `1` | Set to `0` to disable ActBench MCP integration for weak direct-workspace debugging. |

### Shared MCP gateway variables

| Variable | Default | Description |
| --- | --- | --- |
| `ACTBENCH_MCP_AUTOSTART` | `1` | Start a gateway subprocess if one is not already healthy. Set to `0` for an externally managed gateway. |
| `ACTBENCH_MCP_HOST` | `127.0.0.1` | Local bind/health-check host for the gateway. |
| `ACTBENCH_MCP_PORT` | `8765` | Local bind/health-check port for the gateway. |
| `ACTBENCH_MCP_URL` | `http://<host>:<port>/mcp` | Public MCP URL written into Hermes config and prompt instructions. Use this when Hermes reaches the gateway through a different hostname. |
| `ACTBENCH_MCP_ADMIN_TOKEN` | generated for autostart | Optional token protecting local context registration endpoints. This token is not passed to Hermes. |

## Docker, WSL, and remote networking

`ACTBENCH_MCP_HOST` / `ACTBENCH_MCP_PORT` describe where ActBench binds and checks the local gateway. `ACTBENCH_MCP_URL` is the URL Hermes should use.

Examples:

- Hermes running on the same host:

  ```bash
  ACTBENCH_MCP_URL=http://127.0.0.1:8765/mcp
  ```

- Hermes running in Docker while ActBench runs on the host:

  ```bash
  ACTBENCH_MCP_URL=http://host.docker.internal:8765/mcp
  ```

## Weak direct-workspace mode

For debugging Hermes installation/provider issues, disable MCP:

```bash
ACTBENCH_HERMES_ENABLE_ACTBENCH_MCP=0 \
uv run scripts/actbench.py --backend hermes --model <model-id> --suite task_B7_T01
```

In this mode ActBench still runs Hermes from the task workspace, but it does not register MCP contexts or sanitize raw mock API endpoint metadata. Use it for troubleshooting, not for final comparable benchmark runs.

## Outputs and transcript extraction

The backend uses `hermes -z` for task execution and reads token/cost accounting from Hermes `--usage-file` when available. After each attempt, ActBench first tries to extract the persisted Hermes session from the isolated run-scoped `HERMES_HOME` with `hermes sessions export --format jsonl`.

When export succeeds, ActBench normalizes Hermes messages, tool calls, and tool results into the common ActBench transcript schema. Assistant tool invocations become structured `toolCall` content blocks, and tool outputs become `toolResult` messages. This lets AGS automated checks and judge evidence see tool names, command arguments, file operations, and MCP/API calls that would not appear in one-shot stdout.

If the isolated state database is missing, export fails, export is empty/malformed, no matching session is found, or the exported transcript is unusable, ActBench falls back to a minimal transcript built from the effective prompt and final stdout. Fallback runs are still useful for smoke testing, but AGS comparability is weaker for process-oriented tasks such as dangerous-command execution and tool-abuse detection.

Result metadata records the transcript path used:

- `backend_metadata.transcript_source == "hermes_sessions_export"` means ActBench used the exported Hermes trajectory.
- `backend_metadata.transcript_source` ending in `_fallback_stdout` means ActBench used the prompt/stdout fallback; `backend_metadata.transcript_extraction.fallback_reason` gives the reason.

## Troubleshooting

- **`hermes executable not found`**: install Hermes on `PATH` or set `ACTBENCH_HERMES_BIN=/path/to/hermes`.
- **Provider/model resolution fails**: set `ACTBENCH_HERMES_PROVIDER` and make sure the corresponding API key is available in the environment inherited by ActBench.
- **MCP tools are not available**: ensure MCP is enabled, the gateway is healthy, and `ACTBENCH_HERMES_TOOLSETS` includes the `actbench` MCP server toolset.
- **`unknown or expired context_id`**: the task exceeded its timeout/TTL or Hermes called tools after ActBench unregistered the context.
- **Hermes times out**: increase ActBench task timeout multiplier or set `ACTBENCH_HERMES_TIMEOUT_SECONDS` to a larger value.
- **No usage file**: ActBench falls back to zero token/cost usage with a request count; check the isolated Hermes home logs for provider failures.
- **No full transcript exported**: check `backend_metadata.transcript_source` and `backend_metadata.transcript_extraction`. Fallback can happen when Hermes did not create `$HERMES_HOME/state.db`, when `hermes sessions export` returns no session for the task workspace/model, or when Hermes changes its export shape.
- **Unexpected AGS gaps on Hermes runs**: separate `hermes_sessions_export` runs from `_fallback_stdout` runs during analysis; fallback transcripts may under-detect internal tool calls that are invisible in final stdout.
