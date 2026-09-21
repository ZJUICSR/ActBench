# Agents in Docker

ActBench's controller, graders, mock services and results stay on the host.
Use `--backend <name> --execution docker` to run target agents in isolated
containers. All six real backends are supported; `fake` remains a local test
backend. Local execution remains the default. Docker mode also applies to
benign baselines, retries and parallel repeats.

| Backend | Pinned agent | Per-attempt execution |
| --- | --- | --- |
| `opencode` | 1.17.18 | CLI, then a separate session-export container |
| `claudecode` | 2.1.268 | CLI with stdin prompt and stream-JSON transcript |
| `hermes` | 0.18.2, source `daedf4f627c73859974e587783b7cef8ce80e19a` | CLI and session export sharing only that attempt's HOME |
| `openclaw` | 2026.5.18 | `agent --local`, isolated configuration and session JSONL |
| `qwenpaw` | 1.1.11.post2 | Fresh HTTP service and provider state for each attempt |
| `openagent` | 2.83.1 | Fresh HTTP service, SQLite database, Provider, Store and MCP registration |

The native versions match the locally installed adapters. OpenAgent's release
binary is verified by SHA-256 and currently targets Linux amd64. Other images
use their upstream npm/Python packages; no GPU or host agent installation is
required. QwenPaw additionally pins MCP 1.27.2 and FastMCP 3.4.2 because
its AgentScope dependency uses an interface removed in MCP 2.

## Build and check

Install ActBench on the host and enable a Linux Docker daemon:

```bash
uv sync --extra dev
uv run deeptrap docker-build --backend claudecode
uv run deeptrap docker-check --backend claudecode
```

`docker-build` sends only the Dockerfile and `.dockerignore` to Docker. The
images contain only native agent software and basic tools (Python, bash, curl,
git, jq and ripgrep). They contain no benchmark tasks, results, graders or local
credentials. Default tags are `actbench-<backend>:<version>` from the table above.
Omitting `--backend` on build/check keeps the OpenCode default.

`docker-check --backend <name>` calls no model or judge. It verifies the native
CLI version, workspace and HOME writes, MCP and host mock API connectivity,
protected admin endpoints, host-file isolation, read-only rootfs, and actual
container timeout cleanup. OpenCode and OpenClaw also parse their native
configuration; QwenPaw and OpenAgent start and initialize a fresh service using
a dummy provider key. Each check writes a fresh `report.json` plus container
records. A failed check returns nonzero.

For a reviewable build context without Docker:

```bash
uv run deeptrap docker-build --context-only /tmp/actbench-image-context
```

To change OpenCode, explicitly select a version and a new image tag:

```bash
uv run deeptrap docker-build --opencode-version <version> --tag actbench-opencode:<version>
export ACTBENCH_DOCKER_IMAGE=actbench-opencode:<version>
uv run deeptrap docker-check
```

## Run an evaluation

Select exactly the provider environment variables needed by the target. For a
provider supported by OpenCode, for example:

```bash
export OPENROUTER_API_KEY=...  # or load the existing credential into this shell
export ACTBENCH_DOCKER_ENV=OPENROUTER_API_KEY

uv run deeptrap test \
  --backend opencode --execution docker \
  --model openrouter/<model-id> \
  --suite task_B9_T01 --score-mode automated
```

This invokes the target model. Automated scoring avoids an additional judge
call. To use combined AGS, pass `--judge-model <judge-model>` instead of
`--score-mode automated`; judge credentials stay on the host.

The lower-level collector supports the same execution switch:

```bash
uv run deeptrap run \
  --backend opencode --execution docker --model <provider/model-id> \
  --suite B9 --runs 3 --run-workers 2 --output-dir results/docker_b9
```

Use a fresh output directory when comparing local and Docker runs. The target
backend keeps its native name; `backend_metadata.execution` identifies the
execution mode. Docker benign-baseline cache keys include the immutable image
and runtime configuration identity, so local baselines and other images are
not reused as Docker baselines.

For a custom OpenAI-compatible provider, create a JSON file with a `provider`
object, following [`config/opencode.provider.example.json`](../config/opencode.provider.example.json):

```bash
export ACTBENCH_OPENCODE_PROVIDER_CONFIG="$PWD/config/opencode.provider.example.json"
export ACTBENCH_DOCKER_ENV=DASHSCOPE_API_KEY
uv run deeptrap test --backend opencode --execution docker \
  --model bailian/deepseek-v4-flash-0731 \
  --suite task_B9_T01 --score-mode automated
```

The example references `{env:DASHSCOPE_API_KEY}`; provide the existing key in
the host shell. Only the `provider` object is imported. The remaining OpenCode
configuration and ActBench MCP settings stay under the adapter's control.

## Other providers and agents

OpenClaw, QwenPaw and OpenAgent require an explicit OpenAI-compatible provider
configuration because personal host profiles and service databases are not
mounted. Hermes accepts the same configuration and resolves it as a named
custom provider:

```bash
export ACTBENCH_DOCKER_PROVIDER_CONFIG="$PWD/config/docker.provider.example.json"
export ACTBENCH_DOCKER_ENV=DASHSCOPE_API_KEY
# Use hermes, openclaw, qwenpaw or openagent here.
uv run deeptrap test --backend hermes --execution docker \
  --model bailian/deepseek-v4-flash-0731 \
  --suite task_B9_T01 --score-mode automated
```

The file contains `base_url` and `api_key_env`, never the key value. The referenced
variable must also be listed in `ACTBENCH_DOCKER_ENV`. The provider configuration
is included in the baseline-cache identity. For Hermes, the adapter selects the
named provider and passes the unprefixed model ID to its native CLI.

Claude Code uses its native Anthropic-compatible configuration. With an existing
Bailian key, for example:

```bash
export ANTHROPIC_BASE_URL=https://dashscope.aliyuncs.com/apps/anthropic
export ANTHROPIC_AUTH_TOKEN="$DASHSCOPE_API_KEY"
export ACTBENCH_DOCKER_ENV=ANTHROPIC_BASE_URL,ANTHROPIC_AUTH_TOKEN
uv run deeptrap test --backend claudecode --execution docker \
  --model deepseek-v4-flash-0731 --suite task_B9_T01 --score-mode automated
```

Use a model supported by the provider's Anthropic endpoint. The endpoint follows
[Model Studio's Claude Code configuration](https://docs.modelstudio.console.alibabacloud.com/en/model-studio/claude-code).
Claude uses the existing `dontAsk` permission mode and explicit ActBench MCP tool
allowlist. Other provider options must also be explicitly selected for container
passthrough. No credentials are copied from a personal Claude profile.

## Network and environment

The default container-to-host address is `host.docker.internal`; ActBench adds
Docker's `host-gateway` mapping. Docker autostart uses a dedicated random MCP
port, a generated admin token, and a listener on `0.0.0.0`. Controller requests
use the local address; the container uses the advertised address. OpenCode, Claude Code, Hermes and OpenAgent access host mock APIs through MCP.
OpenClaw and QwenPaw use native tools: their per-attempt mock services bind to
the Docker-reachable interface, and workspace endpoints advertise that address.
Their audit/reset routes additionally require a controller-only token, including
on rootless networks that can reach host loopback services.

For rootless Docker, use the daemon's reachable host address explicitly. On
the existing A6000 deployment this is `10.0.2.2`:

```bash
export DOCKER_HOST=unix:///run/user/1024/msca-docker.sock
export ACTBENCH_DOCKER_HOST_ADDRESS=10.0.2.2
# Optional container proxy; this does not alter the controller's proxy.
export ACTBENCH_DOCKER_PROXY_URL=http://10.0.2.2:17890
```

The Docker client must be installed and on PATH. Set `ACTBENCH_DOCKER_BIN` for
a different executable. Build proxies are supplied separately, for example
`deeptrap docker-build --build-arg HTTPS_PROXY=http://10.0.2.2:17890`.

| Setting | Default / meaning |
| --- | --- |
| `ACTBENCH_DOCKER_IMAGE` | Optional global image override; otherwise backend-specific default |
| `ACTBENCH_DOCKER_<BACKEND>_IMAGE` | Per-backend override, preferred over the global override |
| `ACTBENCH_DOCKER_PROVIDER_CONFIG` | Explicit provider JSON for OpenClaw, QwenPaw, OpenAgent, optionally Hermes |
| `ACTBENCH_DOCKER_ENV` | Empty; comma-separated target-provider variable names |
| `ACTBENCH_DOCKER_HOST_ADDRESS` | `host.docker.internal`; use `10.0.2.2` where appropriate for rootless |
| `ACTBENCH_DOCKER_MCP_BIND_HOST` | `0.0.0.0`; restrict to a Docker-reachable interface if needed |
| `ACTBENCH_DOCKER_PROXY_URL` | Unset; optional HTTP proxy inside the container |
| `ACTBENCH_DOCKER_USER` | Host UID:GID for rootful, container `0:0` for rootless |
| `ACTBENCH_DOCKER_CPUS` | Unset; optional Docker CPU limit |
| `ACTBENCH_DOCKER_MEMORY` | Unset; optional Docker memory limit, e.g. `4g` |
| `ACTBENCH_DOCKER_PIDS_LIMIT` | Unset; optional process limit |

Rootless UID 0 maps to the daemon owner's host UID and makes bind mounts
writable. The A6000 daemon uses cgroup v1, so it cannot enforce rootless resource
limits; ActBench rejects explicit limit requests there. Bound runs using task
timeouts and worker counts. No system Docker or cgroup configuration changes
are needed.

For an externally managed MCP gateway, set `ACTBENCH_MCP_AUTOSTART=0`,
`ACTBENCH_MCP_HOST`, `ACTBENCH_MCP_PORT`, `ACTBENCH_MCP_ADMIN_TOKEN`, and a
container-reachable `ACTBENCH_MCP_URL`. Loopback public URLs are rejected in
Docker mode. MCP cannot be disabled for the adapters that use it. OpenClaw and QwenPaw do
not require MCP for their native tools.

## Artifacts and cleanup

Only the materialized workspace and the attempt's isolated HOME are
mounted read-write. They use the same absolute paths inside the container, so
transcripts and graders can interpret file operations without path rewriting.
The rest of the host repository, result directory and Docker socket are not
mounted. The image root filesystem is read-only; `/tmp` is private and limited
to 512 MiB. Containers drop Linux capabilities and use `no-new-privileges`.

The agent's `opencode run` container is removed when execution finishes. A
separate short-lived container with the same image, workspace and HOME runs
`opencode export` to recover the session; it makes no new target-model request.
The complete session remains the preferred trajectory source, with the existing
stdout fallback if export fails.

QwenPaw and OpenAgent publish a random port bound only to host `127.0.0.1`.
Startup health checks, provider initialization, task execution, and transcript
retrieval run within that one container's lifetime. Errors and timeouts remove
it in a `finally` path. Each attempt has separate state and credentials; no
existing host service or database is reused. OpenAgent's initial admin password
is replaced before provider setup. Agent state directories can contain native
credential stores and should be treated as private; they are not included in the
build context or normal workspace artifacts.

Workspace snapshots record symbolic links in `files_manifest.json` without
following them or recreating them in the exported workspace. This prevents a
container-created link from making the host recorder copy an unmounted host
file. OpenClaw session collection also rejects links outside the attempt HOME.

`backend_metadata.docker` records the image ID, Docker version, invocation
owner, user mapping and runtime options. `docker_executions` records exact
container names and cleanup results. The controller also writes
`<output-dir>/docker/<run-id>/runtime.json` and one execution JSON per container,
starting before launch, so interrupted runs can be inspected.

Timeouts, Ctrl-C and SIGTERM trigger cleanup of the invocation's exact
containers. After SIGKILL or a host crash, first confirm the recorded controller
has stopped, inspect the recorded container name and `actbench.owner` label,
then remove that specific container with `docker rm -f <name>`. Do not use
project-wide pruning or clean up another invocation's containers.

This is filesystem/process separation with outbound networking for the model,
not network egress isolation. Task prompts, graders and scoring formulas are
unchanged. Run local/Docker comparisons as distinct configurations.

Docker behavior references: [container run](https://docs.docker.com/reference/cli/docker/container/run/)
and [rootless Docker](https://docs.docker.com/engine/security/rootless/tips/).
