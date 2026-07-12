# Claude Code backend

ActBench can drive Claude Code through the non-interactive `claude` CLI. The backend launches one headless Claude Code subprocess per task attempt, materializes the task workspace as the subprocess working directory, and records results in the same schema as the other ActBench backends.

## Prerequisites

- Claude Code CLI installed and available as `claude` on `PATH`, or `ACTBENCH_CLAUDECODE_BIN` set to the CLI path.
- Non-interactive Claude Code credentials inherited by the ActBench process. ActBench runs each task attempt with isolated `HOME`, XDG directories, and `CLAUDE_CONFIG_DIR`, so credentials stored only in the user's default Claude Code profile may not be read unless exported into the environment.
- ActBench dependencies installed with `uv sync` or `pip install -e .`.

## Basic usage

```bash
uv run scripts/actbench.py \
  --backend claudecode \
  --model <model-id> \
  --suite task_B7_T01 \
  --runs 1
```

`--model` is recorded as the model under test and is passed to Claude Code with `--model`. Set `ACTBENCH_CLAUDECODE_MODEL` only when you need the CLI to receive a different model string from the ActBench result label.

## Parallel repeat runs

The Claude Code backend supports same-task repeat parallelism with `--runs N --run-workers M`. ActBench keeps task order deterministic in result files while running repeat attempts concurrently, and each attempt receives its own workspace plus Claude Code home/config/data/state/cache directories and MCP config directory.

```bash
uv run scripts/actbench.py \
  --backend claudecode \
  --model <model-id> \
  --suite task_B7_T01 \
  --runs 3 \
  --run-workers 2
```

When `ACTBENCH_CLAUDECODE_HOME_ROOT` is unset, attempt homes are created beside each attempt workspace. When it is set, ActBench creates homes under `<ACTBENCH_CLAUDECODE_HOME_ROOT>/<run_id>/<attempt_run_id>/claudecode_home`, which keeps concurrent Claude Code subprocesses from sharing config, state, cache, or MCP config files.

## Default MCP mode

By default, the Claude Code backend exposes task workspace and mock APIs through the ActBench MCP gateway. For each task attempt, ActBench:

1. Materializes an isolated workspace.
2. Starts any declared mock API services.
3. Registers a high-entropy task `context_id` with the ActBench MCP gateway.
4. Writes an attempt-scoped MCP config file for a server named `actbench`.
5. Runs `claude --bare -p --input-format text --output-format stream-json --verbose ...` with the task workspace as subprocess CWD.
6. Prepends instructions telling Claude Code to use the ActBench MCP tools with the exact `context_id`.
7. Unregisters the context after the attempt; stale contexts also expire by TTL.

The ActBench MCP server exposes these tool names:

- `actbench_list_files`
- `actbench_read_file`
- `actbench_write_file`
- `actbench_get_api_endpoints`
- `actbench_call_api`

Claude Code may display these tools with MCP prefixes such as `mcp__actbench__actbench_read_file`. The backend instruction tells the agent to use whichever prefixed names Claude Code exposes.

When MCP is enabled, ActBench result payloads sanitize `api_endpoints`: raw mock-service localhost URLs, audit/reset/health/admin paths, fixture paths, and admin tokens are not exposed.

## Environment variables

### Claude Code adapter variables

| Variable | Default | Description |
| --- | --- | --- |
| `ACTBENCH_CLAUDECODE_BIN` | `claude` | Claude Code CLI executable name or path. |
| `ACTBENCH_CLAUDECODE_MODEL` | ActBench `--model` | Optional override for the model passed to Claude Code. |
| `ACTBENCH_CLAUDECODE_TIMEOUT_SECONDS` | unset | Optional per-subprocess timeout cap. If unset, ActBench uses the task timeout budget. |
| `ACTBENCH_CLAUDECODE_HOME_ROOT` | unset | Optional parent directory for per-attempt isolated Claude Code homes. |
| `ACTBENCH_CLAUDECODE_PERMISSION_MODE` | `dontAsk` | Permission mode passed to Claude Code. |
| `ACTBENCH_CLAUDECODE_ALLOWED_TOOLS` | MCP tools when MCP is enabled; direct workspace tools otherwise | Comma- or shell-split list passed to `--allowedTools`. |
| `ACTBENCH_CLAUDECODE_TOOLS` | disables built-in tools when MCP is enabled; unset otherwise | Value passed to `--tools`. Use `none`, `disabled`, or an empty value to disable built-ins. |
| `ACTBENCH_CLAUDECODE_ENABLE_ACTBENCH_MCP` | `1` | Set to `0` to disable ActBench MCP integration for weak direct-workspace debugging. |

### Shared MCP gateway variables

| Variable | Default | Description |
| --- | --- | --- |
| `ACTBENCH_MCP_AUTOSTART` | `1` | Start a gateway subprocess if one is not already healthy. Set to `0` for an externally managed gateway. |
| `ACTBENCH_MCP_HOST` | `127.0.0.1` | Local bind/health-check host for the gateway. |
| `ACTBENCH_MCP_PORT` | `8765` | Local bind/health-check port for the gateway. |
| `ACTBENCH_MCP_URL` | `http://<host>:<port>/mcp` | Public MCP URL written into Claude Code config and prompt instructions. Use this when Claude Code reaches the gateway through a different hostname. |
| `ACTBENCH_MCP_ADMIN_TOKEN` | generated for autostart | Optional token protecting local context registration endpoints. This token is not passed to Claude Code. |

## Weak direct-workspace mode

For debugging Claude Code installation/provider issues, disable MCP:

```bash
ACTBENCH_CLAUDECODE_ENABLE_ACTBENCH_MCP=0 \
uv run scripts/actbench.py --backend claudecode --model <model-id> --suite task_B7_T01
```

In this mode ActBench still runs Claude Code from the task workspace and permits direct workspace tools, but it does not register MCP contexts or sanitize raw mock API endpoint metadata. Use it for troubleshooting, not for final comparable benchmark runs.

## Outputs and transcript extraction

The backend uses Claude Code `stream-json` output as the transcript source. ActBench normalizes assistant text, tool calls, tool results, terminal result events, and usage into the common ActBench result schema while omitting raw thinking/reasoning blocks. MCP gateway traces are appended when Claude Code's stream omits ActBench tool evidence that the gateway recorded.

Result metadata records `claudecode_home`, `claudecode_config_dir`, `claudecode_session_id`, and `mcp_config_path` when an MCP config file is used.

## Troubleshooting

- **`claudecode executable not found`**: install Claude Code on `PATH` or set `ACTBENCH_CLAUDECODE_BIN=/path/to/claude`.
- **Provider/model/authentication fails**: confirm Claude Code can run the model non-interactively with the same environment, then rerun ActBench. Because ActBench isolates Claude Code home/config paths per attempt, export credentials through environment variables when possible.
- **MCP tools are not available**: ensure MCP is enabled, the gateway is healthy, and Claude Code sees the attempt-scoped MCP config.
- **`unknown or expired context_id`**: the task exceeded its timeout/TTL or Claude Code called tools after ActBench unregistered the context.
- **Mock API calls fail because of localhost ports**: Claude Code should not call mock APIs directly. It should call `actbench_get_api_endpoints` and `actbench_call_api`; ActBench injects this instruction automatically when MCP is enabled.
- **Claude Code times out**: increase ActBench task timeout multiplier or set `ACTBENCH_CLAUDECODE_TIMEOUT_SECONDS` to a larger value.
