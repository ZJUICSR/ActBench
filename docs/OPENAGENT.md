# OpenAgent Backend Setup

ActBench can run tasks through a running OpenAgent service by using OpenAgent's OpenAI-compatible chat-completions API. Unlike backends that can bind a per-task workspace directly to the agent runtime, OpenAgent needs one extra setup step: configure OpenAgent with an ActBench MCP server so it can access the per-task workspace and mock APIs.

## Why MCP is required

OpenAgent exposes a chat-completions API without a per-request workspace binding. A plain chat-completions request can send the user prompt, but it cannot reliably attach the current workspace directory or the random mock-service ports, so ActBench uses MCP for OpenAgent workspace and mock API access.

The `openagent` backend therefore uses an ActBench-owned MCP gateway:

1. ActBench materializes the task workspace into a temporary directory.
2. ActBench starts the task's declared mock services on local random ports.
3. ActBench registers a high-entropy `context_id` with the MCP gateway. The context maps that id to the workspace and the declared mock APIs for this one task attempt.
4. OpenAgent calls the configured MCP server. The model must pass the injected `context_id` to every ActBench MCP tool call.
5. After the attempt, ActBench unregisters the context, stops mock services, and collects workspace/API audit evidence for scoring.

The MCP gateway exposes only task-scoped tools:

- `actbench_list_files`
- `actbench_read_file`
- `actbench_write_file`
- `actbench_get_api_endpoints`
- `actbench_call_api`

`actbench_call_api` accepts only mock services declared by the task and only each service's allowed business paths. The gateway does not expose raw service ports, fixture paths, audit/reset endpoints, or other administrative mock-service endpoints.

## What you need to provide

Before running `--backend openagent`, prepare:

- A running OpenAgent service reachable from the ActBench machine.
- An OpenAgent **Store external API key** for the Store being evaluated. In current OpenAgent builds, MCP server selection is attached to a Store, so a Store key is the recommended key for normal ActBench OpenAgent runs. A Provider external API key can reach the OpenAI-compatible endpoint, but it does not attach the Store's MCP server and is useful only for weak HTTP-only checks.
- A model/provider configured inside that OpenAgent Store.
- An ActBench MCP URL that OpenAgent can reach.
- Python dependencies installed for ActBench (`uv sync` or `pip install -e .`).

ActBench still records and sends the CLI `--model` value in the chat-completions payload, but the actual model/provider behavior is controlled by the OpenAgent Store and its underlying provider.

## One-time OpenAgent MCP configuration

Configure this once for the OpenAgent Store that will be used by ActBench.

### 1. Start or expose the ActBench MCP gateway for tool sync

OpenAgent needs the gateway to be online when you click **Sync** in the OpenAgent MCP server UI.

For local OpenAgent on the same host:

```bash
uv run python scripts/lib_mcp_gateway.py --host 127.0.0.1 --port 8765
```

Use this MCP URL in OpenAgent:

```text
http://127.0.0.1:8765/mcp
```

For OpenAgent running in Docker, bind the gateway on all host interfaces so the container can reach it:

```bash
uv run python scripts/lib_mcp_gateway.py --host 0.0.0.0 --port 8765
```

Use this MCP URL in OpenAgent:

```text
http://host.docker.internal:8765/mcp
```

On Linux Docker engines that do not provide `host.docker.internal` automatically, start the OpenAgent container with a host-gateway mapping, for example `--add-host=host.docker.internal:host-gateway`, or use another routable host IP.

### 2. Add an MCP server in OpenAgent

In the OpenAgent web UI:

1. Open the MCP server/Servers page.
2. Add a new MCP server.
3. Set a stable `name`, for example `actbench_mcp`.
4. Set a readable display name, for example `ActBench MCP`.
5. Set `url` to the MCP URL from the previous section.
6. Leave the OpenAgent MCP server access token blank unless you put your own authenticated proxy in front of the gateway.
7. Save the server.
8. Click **Sync**.
9. Confirm these tools appear, and mark/leave them allowed: `actbench_list_files`, `actbench_read_file`, `actbench_write_file`, `actbench_get_api_endpoints`, `actbench_call_api`.

OpenAgent's URL-based MCP client uses Streamable HTTP; there is no transport selector to configure for this setup.

`ACTBENCH_MCP_ADMIN_TOKEN` is different from the OpenAgent MCP server access token. It protects ActBench's local `/admin/contexts` registration endpoints. OpenAgent does not need that token to call `/mcp` in the default gateway.

### 3. Attach the MCP server to the Store

In the OpenAgent Store edit page for the Store under test:

1. Configure the Store's model/provider as usual.
2. Select the MCP server created above in the Store's **MCP server** dropdown.
3. Save the Store.
4. Copy the Store's **External API key**. Use this key as `OPENAGENT_API_KEY` when running ActBench.

Do not manually add a task `context_id` in OpenAgent. ActBench generates a fresh id for every task attempt and injects it into the OpenAgent conversation automatically.

## Run ActBench with local OpenAgent

If OpenAgent and ActBench run on the same host, the default MCP settings are usually enough:

```bash
OPENAGENT_API_KEY=sk-... \
OPENAGENT_BASE_URL=http://localhost:14000 \
ACTBENCH_MCP_URL=http://127.0.0.1:8765/mcp \
uv run scripts/actbench.py \
  --backend openagent \
  --model deepseek/deepseek-v4-pro \
  --suite task_B9_T01
```

If the gateway is not already running, ActBench autostarts it on `127.0.0.1:8765` by default.

## Run ActBench when OpenAgent is in Docker

For Docker, keep a gateway process bound to `0.0.0.0`, but let ActBench use `127.0.0.1` for local admin registration:

Terminal 1:

```bash
uv run python scripts/lib_mcp_gateway.py --host 0.0.0.0 --port 8765
```

Terminal 2:

```bash
OPENAGENT_API_KEY=sk-... \
OPENAGENT_BASE_URL=http://localhost:14000 \
ACTBENCH_MCP_AUTOSTART=0 \
ACTBENCH_MCP_HOST=127.0.0.1 \
ACTBENCH_MCP_PORT=8765 \
ACTBENCH_MCP_URL=http://host.docker.internal:8765/mcp \
uv run scripts/actbench.py \
  --backend openagent \
  --model deepseek/deepseek-v4-pro \
  --suite task_B9_T01
```

`ACTBENCH_MCP_HOST` is the address ActBench uses for local health checks and admin context registration. `ACTBENCH_MCP_URL` is the public URL that OpenAgent sees in the injected system message and should match the URL configured in OpenAgent.

## Environment variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `OPENAGENT_API_KEY` | required | OpenAgent Store external API key. Use a Store key for MCP-enabled ActBench runs. |
| `OPENAGENT_BASE_URL` | `http://localhost:14000` | Base URL of the running OpenAgent service. |
| `OPENAGENT_ENDPOINT` | `/api/v1/chat/completions` | OpenAI-compatible chat-completions endpoint path. |
| `OPENAGENT_TIMEOUT_SECONDS` | unset | Optional per-request HTTP timeout. If unset, ActBench uses the task timeout budget. |
| `OPENAGENT_ENABLE_ACTBENCH_MCP` | `1` | Set to `0` to disable MCP and run weak chat-completions-only mode. |
| `ACTBENCH_MCP_AUTOSTART` | `1` | If enabled, ActBench starts the gateway when one is not already healthy. Set to `0` for a manually managed gateway. |
| `ACTBENCH_MCP_HOST` | `127.0.0.1` | Host used by ActBench for gateway health checks/admin registration, and the autostart bind address. |
| `ACTBENCH_MCP_PORT` | `8765` | Gateway port. |
| `ACTBENCH_MCP_URL` | `http://<ACTBENCH_MCP_HOST>:<ACTBENCH_MCP_PORT>/mcp` | MCP URL shown to OpenAgent. Must be reachable from the OpenAgent process/container. |
| `ACTBENCH_MCP_ADMIN_TOKEN` | unset | Optional bearer token for ActBench gateway admin context registration endpoints. If you run an external gateway with this token, set the same value for the ActBench run. |

## Troubleshooting

- **OpenAgent health check fails**: verify `OPENAGENT_BASE_URL` and confirm the OpenAgent service responds at `/api/health` from the ActBench machine.
- **OpenAgent Sync fails or no ActBench tools appear**: start the gateway first, check the MCP URL from the OpenAgent process/container, and then click **Sync** again.
- **The model does not use workspace/API tools**: confirm the Store has the ActBench MCP server selected, all five tools are allowed, `OPENAGENT_API_KEY` is the Store external API key, and `OPENAGENT_ENABLE_ACTBENCH_MCP` is not `0`.
- **Tool calls report `unknown or expired context_id`**: run a fresh ActBench task attempt. The `context_id` is per attempt and expires after the task timeout window.
- **Mock API calls fail because of localhost ports**: OpenAgent should not call mock APIs directly. It should call `actbench_get_api_endpoints` and `actbench_call_api`; ActBench injects this instruction automatically when MCP is enabled.
- **Docker cannot reach the gateway**: bind the gateway to `0.0.0.0`, use `http://host.docker.internal:8765/mcp` or another routable host IP as `ACTBENCH_MCP_URL`, and keep `ACTBENCH_MCP_AUTOSTART=0` for that run.
