# opencode backend

ActBench can drive opencode through the non-interactive `opencode run` CLI. The backend launches one isolated opencode subprocess per task attempt, materializes the task workspace as the subprocess working directory, and records results in the same schema as the other ActBench backends.

The first integration is an ActBench-side MVP: it does not import opencode internals or require changes to the opencode source tree. A future implementation can switch to `opencode serve`/API mode if tighter lifecycle control is needed.

## Prerequisites

- opencode CLI installed and available as `opencode` on `PATH`, or `ACTBENCH_OPENCODE_BIN` set to the CLI path.
- A model/provider configured for opencode through environment variables or other non-interactive credentials inherited by the ActBench process. ActBench runs each task attempt with isolated `HOME`, XDG directories, `OPENCODE_DB`, and inline `OPENCODE_CONFIG_CONTENT`, so credentials stored only in the user's default opencode profile may not be read unless exported into the environment.
- ActBench dependencies installed with `uv sync` or `pip install -e .`.

## Basic usage

```bash
uv run scripts/actbench.py \
  --backend opencode \
  --model <provider/model-id> \
  --suite task_B7_T01 \
  --runs 1
```

`--model` is recorded as the model under test and is passed to `opencode run --model`. Set `ACTBENCH_OPENCODE_MODEL` only when you need the opencode CLI to receive a different model string from the ActBench result label.

Set `ACTBENCH_OPENCODE_AGENT=<agent-name>` to pass `opencode run --agent <agent-name>`. If unset, opencode uses its default primary agent.

## Parallel repeat runs

The opencode backend supports same-task repeat parallelism with `--runs N --run-workers M`. ActBench keeps task order deterministic in result files while running repeat attempts concurrently, and each attempt receives its own workspace plus opencode home/config/data/state/cache directories and `OPENCODE_DB` sqlite file.

```bash
uv run scripts/actbench.py \
  --backend opencode \
  --model <provider/model-id> \
  --suite task_B7_T01 \
  --runs 3 \
  --run-workers 2
```

When `ACTBENCH_OPENCODE_HOME_ROOT` is unset, attempt homes are created beside each attempt workspace. When it is set, ActBench creates homes under `<ACTBENCH_OPENCODE_HOME_ROOT>/<run_id>/<attempt_run_id>/opencode_home`, which keeps concurrent `opencode run` and `opencode export` processes from sharing XDG state or sqlite databases.

## Default MCP mode

By default, the opencode backend exposes task workspace and mock APIs through the ActBench MCP gateway. For each task attempt, ActBench:

1. Materializes an isolated workspace.
2. Starts any declared mock API services.
3. Registers a high-entropy task `context_id` with the ActBench MCP gateway.
4. Provides an isolated opencode config through `OPENCODE_CONFIG_CONTENT` with a remote MCP server named `actbench`:

   ```json
   {
     "mcp": {
       "actbench": {
         "type": "remote",
         "url": "http://127.0.0.1:8765/mcp",
         "enabled": true,
         "oauth": false
       }
     }
   }
   ```

5. Runs `opencode run --format json --dir <workspace> --auto ...` with the task workspace as subprocess CWD.
6. Prepends instructions telling opencode to use the ActBench MCP tools with the exact `context_id`.
7. Unregisters the context after the attempt; stale contexts also expire by TTL.

The ActBench MCP server exposes these tool names:

- `actbench_list_files`
- `actbench_read_file`
- `actbench_write_file`
- `actbench_get_api_endpoints`
- `actbench_call_api`

opencode may display remote MCP tools with the server name prefixed, for example `actbench_actbench_read_file`. The backend instruction tells the agent to use whichever prefixed names opencode exposes.

When MCP is enabled, ActBench result payloads sanitize `api_endpoints`: raw mock-service localhost URLs, audit/reset/health/admin paths, fixture paths, and admin tokens are not exposed.

## Environment variables

### opencode adapter variables

| Variable | Default | Description |
| --- | --- | --- |
| `ACTBENCH_OPENCODE_BIN` | `opencode` | opencode CLI executable name or path. |
| `ACTBENCH_OPENCODE_MODEL` | ActBench `--model` | Optional override for the model passed to opencode. |
| `ACTBENCH_OPENCODE_AGENT` | unset | Optional agent passed as `opencode run --agent`. |
| `ACTBENCH_OPENCODE_TIMEOUT_SECONDS` | unset | Optional per-subprocess timeout cap. If unset, ActBench uses the task timeout budget. |
| `ACTBENCH_OPENCODE_HOME_ROOT` | unset | Optional parent directory for per-attempt isolated opencode homes. |
| `ACTBENCH_OPENCODE_AUTO` | `1` | Pass `--auto` to approve opencode permissions non-interactively. Set to `0` only for debugging runs that do not need unattended execution. |
| `ACTBENCH_OPENCODE_ENABLE_ACTBENCH_MCP` | `1` | Set to `0` to disable ActBench MCP integration for weak direct-workspace debugging. |

### Shared MCP gateway variables

| Variable | Default | Description |
| --- | --- | --- |
| `ACTBENCH_MCP_AUTOSTART` | `1` | Start a gateway subprocess if one is not already healthy. Set to `0` for an externally managed gateway. |
| `ACTBENCH_MCP_HOST` | `127.0.0.1` | Local bind/health-check host for the gateway. |
| `ACTBENCH_MCP_PORT` | `8765` | Local bind/health-check port for the gateway. |
| `ACTBENCH_MCP_URL` | `http://<host>:<port>/mcp` | Public MCP URL written into opencode config and prompt instructions. Use this when opencode reaches the gateway through a different hostname. |
| `ACTBENCH_MCP_ADMIN_TOKEN` | generated for autostart | Optional token protecting local context registration endpoints. This token is not passed to opencode. |

## Docker, WSL, and remote networking

`ACTBENCH_MCP_HOST` / `ACTBENCH_MCP_PORT` describe where ActBench binds and checks the local gateway. `ACTBENCH_MCP_URL` is the URL opencode should use.

Examples:

- opencode running on the same host:

  ```bash
  ACTBENCH_MCP_URL=http://127.0.0.1:8765/mcp
  ```

- opencode running in Docker while ActBench runs on the host:

  ```bash
  ACTBENCH_MCP_URL=http://host.docker.internal:8765/mcp
  ```

## Weak direct-workspace mode

For debugging opencode installation/provider issues, disable MCP:

```bash
ACTBENCH_OPENCODE_ENABLE_ACTBENCH_MCP=0 \
uv run scripts/actbench.py --backend opencode --model <provider/model-id> --suite task_B7_T01
```

In this mode ActBench still runs opencode from the task workspace, but it does not register MCP contexts or sanitize raw mock API endpoint metadata. Use it for troubleshooting, not for final comparable benchmark runs.

## Outputs and transcript extraction

The backend uses `opencode run --format json` for task execution. The JSON event stream is useful for finding the opencode session id, but it is intentionally not treated as the authoritative transcript because it can be lossy.

After each attempt, ActBench first tries:

```bash
opencode export <sessionID>
```

using the same attempt-scoped opencode database/config environment. When export succeeds, ActBench normalizes opencode user, assistant, shell, tool-call, and tool-result messages into the common ActBench transcript schema. Assistant tool invocations become structured `toolCall` content blocks, and tool outputs become `toolResult` messages. This lets AGS automated checks and judge evidence see tool names, command arguments, file operations, and MCP/API calls that would not be reliable in final stdout alone.

If export fails, is empty/malformed, no session id appears in `opencode run --format json`, or the exported transcript is unusable, ActBench falls back to the `opencode run` JSON event stream and then to a minimal prompt/stdout transcript. Fallback runs are still useful for smoke testing, but AGS comparability is weaker for process-oriented tasks such as dangerous-command execution and tool-abuse detection.

Result metadata records the transcript path used:

- `backend_metadata.transcript_source == "opencode_export"` means ActBench used the exported opencode session trajectory.
- `backend_metadata.transcript_source` ending in `_fallback_run_stdout_json` means ActBench reconstructed the transcript from `opencode run --format json` events.
- `backend_metadata.transcript_source` ending in `_fallback_run_stdout_raw` means ActBench used the prompt/stdout fallback; `backend_metadata.transcript_extraction.fallback_reason` gives the reason.

## Troubleshooting

- **`opencode executable not found`**: install opencode on `PATH` or set `ACTBENCH_OPENCODE_BIN=/path/to/opencode`.
- **Provider/model resolution fails**: confirm opencode can run the model non-interactively with the same environment, then rerun ActBench. Because ActBench isolates opencode home/config/database paths per attempt, export credentials through environment variables when possible.
- **MCP tools are not available**: ensure MCP is enabled, the gateway is healthy, and opencode sees the inline config with an enabled remote MCP server named `actbench`.
- **`unknown or expired context_id`**: the task exceeded its timeout/TTL or opencode called tools after ActBench unregistered the context.
- **Mock API calls fail because of localhost ports**: opencode should not call mock APIs directly. It should call `actbench_get_api_endpoints` and `actbench_call_api`; ActBench injects this instruction automatically when MCP is enabled.
- **opencode times out**: increase ActBench task timeout multiplier or set `ACTBENCH_OPENCODE_TIMEOUT_SECONDS` to a larger value.
- **No full transcript exported**: check `backend_metadata.transcript_source` and `backend_metadata.transcript_extraction`. Fallback can happen when `opencode run --format json` did not emit a session id, when `opencode export <sessionID>` fails, or when opencode changes its export shape.
