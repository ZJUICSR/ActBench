# Trajectory PDF Input Standard

This document defines the **plot-ready trajectory format** for converting ActBench agent execution traces into PDF visualizations with the original `~/to_trajectory/run_pdf.py` renderer.

The goal is not to replace the full ActBench canonical trajectory format. The goal is to define the smaller, stable, renderer-facing subset needed to produce consistent trajectory graphs.

## 1. Scope

A plot-ready trajectory file represents **one agent attempt** for **one task/run/model/backend**.

The original renderer expects a JSON object with a top-level `transcript` array:

```json
{
  "agent_id": "bench-model-name",
  "task_id": "task_B1_T01",
  "status": "success",
  "backend": "openclaw",
  "model": "deepseek/deepseek-v4-pro",
  "run_number": 1,
  "role": "attacked_attempt",
  "transcript": []
}
```

Only `transcript` is strictly required for rendering. The other fields are required for **batch organization, naming, provenance, and quality checks**.

## 2. File types

### Renderable file

Renderable by the original PDF script:

```text
plot_trajectories/<task_id>/<backend>__<model_slug>__<run-label>__<role>.json
```

For attacked repeated runs, `<run-label>` is `run-01`, `run-02`, etc. For the clean comparison trajectory, `<run-label>` is `clean` and `<task_id>` is the original attacked task ID, not the `_baseline` task ID.

This file must contain:

```json
{
  "transcript": [ ... ]
}
```

### Non-renderable locator files

These files are useful for finding source data but should not be passed directly to the original PDF renderer:

- `trajectory_index.json`
- `metadata.json`
- ActBench canonical `trajectory.json` unless it has first been converted/unwrapped to top-level `transcript: [...]`

Canonical ActBench trajectories store transcript content here:

```json
{
  "transcript": {
    "entries": [ ... ],
    "entry_count": 123,
    "source": { ... }
  }
}
```

For the original renderer, this must be exported as:

```json
{
  "transcript": [ ... ]
}
```

## 3. Required top-level metadata

These fields should be present in every plot-ready JSON, even if the renderer itself only needs `transcript`.

| Field | Required | Purpose |
|---|---:|---|
| `schema_version` | recommended | Use `actbench.plot_trajectory.v1` for plot-ready exports. |
| `source_schema_version` | recommended | Original source schema, e.g. `actbench.trajectory.v1`. |
| `source_path` | required | Absolute or repo-relative source trajectory path. |
| `source_sha256` | recommended | Hash of source trajectory JSON. |
| `agent_id` | recommended | Agent identifier from the run. |
| `task_id` | required | Task folder grouping key, e.g. `task_B1_T01`. For clean baselines this is mapped back from `task_B1_T01_baseline` to `task_B1_T01`. |
| `plot_task_id` | recommended | Same as `task_id`; explicit folder/plot grouping key. |
| `source_task_id` | recommended | Original attacked task ID used for comparison, e.g. `task_B1_T01`. |
| `clean_task_id` | required for clean baselines | Source clean task ID, e.g. `task_B1_T01_baseline`. Empty for attacked runs. |
| `suite` | recommended | Suite/behavior bucket, e.g. `B1`. |
| `backend` | required | Backend name, e.g. `openclaw`, `openagent`. |
| `model` | required | Model name, e.g. `deepseek/deepseek-v4-pro`. |
| `run_number` | required for repeated runs | Source human-facing run number. Attacked runs are usually 1..3; clean baselines may keep their original baseline run number. |
| `source_run_number` | recommended | Copy of the source run number when filename/run-label differs. |
| `plot_run_label` | recommended | Filename run label, e.g. `run-01` for attacked or `clean` for benign baseline. |
| `role` | required | `attacked_attempt`, `benign_baseline`, etc. |
| `comparison_role` | recommended | Coarse comparison bucket, `attacked` or `clean`. |
| `status` | recommended | Execution status, e.g. `success`, `error`, `timeout`. |
| `transcript_source_kind` | recommended | Source transcript type, e.g. `sessions_json`, `openagent_openai_compatible`. |
| `transcript` | required | Top-level array of transcript events for the renderer. |

## 4. Required transcript semantics

A plot-ready transcript must be an ordered array of event objects:

```json
{
  "transcript": [
    {"type": "message", "id": "...", "message": {"role": "user", "content": [...]}}
  ]
}
```

The renderer ignores non-message events such as session/model metadata unless they participate in the active `id`/`parentId` chain. It builds the visual graph from user, assistant, tool-call, and tool-result messages.

### 4.1 Start event

There must be at least one user message after any setup/session metadata:

```json
{
  "type": "message",
  "id": "user-1",
  "message": {
    "role": "user",
    "content": [
      {"type": "text", "text": "Please complete the task..."}
    ]
  }
}
```

Renderer effect:

- first user message becomes the `START` node
- later user messages become `USER` nodes

### 4.2 Assistant reasoning/tool dispatch events

Assistant messages that are not terminal `stop` messages become `REASONING` nodes.

If the assistant makes tool calls, put the tool calls inside the same assistant message content:

```json
{
  "type": "message",
  "id": "assistant-1",
  "parentId": "user-1",
  "message": {
    "role": "assistant",
    "content": [
      {"type": "text", "text": "I will inspect the brief and taskboard skill."},
      {
        "type": "toolCall",
        "id": "read_0",
        "name": "read",
        "arguments": {"file_path": "/tmp/workspace/brief.md"}
      }
    ]
  }
}
```

Renderer effect:

- assistant text/thinking becomes a `REASONING` node
- each tool call becomes a tool node in the next stage
- multiple tool calls in one assistant message are shown as a parallel batch

### 4.3 Tool result events

Tool results should carry the matching tool call id.

Preferred form:

```json
{
  "type": "message",
  "id": "tool-result-1",
  "parentId": "assistant-1",
  "message": {
    "role": "toolResult",
    "toolCallId": "read_0",
    "toolName": "read",
    "content": [
      {"type": "text", "text": "# Brief\n..."}
    ],
    "isError": false
  }
}
```

Also acceptable if using normalized OpenAI-compatible item fields:

```json
{
  "type": "message",
  "message": {
    "role": "toolResult",
    "content": [
      {
        "type": "toolResult",
        "tool_call_id": "read_0",
        "name": "read",
        "text": "# Brief\n...",
        "isError": false
      }
    ]
  }
}
```

Renderer effect:

- matching result text is summarized inside the tool node
- `isError: true` or non-zero exit metadata makes the node status `ERROR`
- missing result makes the node status `NO RESULT`

### 4.4 Terminal event

For compatibility with the original renderer, every plot-ready transcript should end with, or contain on the active branch, an assistant message with:

```json
"stopReason": "stop"
```

Example:

```json
{
  "type": "message",
  "id": "assistant-final",
  "parentId": "tool-result-1",
  "message": {
    "role": "assistant",
    "content": [
      {"type": "text", "text": "Done. I updated the taskboard."}
    ],
    "stopReason": "stop"
  }
}
```

Renderer effect:

- terminal assistant message becomes the `END` node

If the source backend does not record `stopReason` (common for OpenAgent/OpenAI-compatible traces), a plot-ready export must choose one of these policies:

1. **Strict mode:** exclude the trajectory from original-renderer plotting and mark it as missing terminal stop metadata.
2. **Sequential compatibility mode:** add a clearly synthetic terminal assistant event with `stopReason: "stop"` and mark `terminal_event_synthetic: true` in top-level metadata.

For consistent batch visualization, sequential compatibility mode is usually preferable, but it should be documented in the manifest.

## 5. Active branch requirements

The original renderer prefers to recover the active branch by walking backward from the latest `stopReason="stop"` event through `parentId` links.

For best graph fidelity, each meaningful message event should have:

| Field | Purpose |
|---|---|
| `id` | Stable event id. |
| `parentId` | Previous event on the active branch. |
| `timestamp` | Used to choose the latest final stop event when multiple exist. |

If `id`/`parentId` metadata is missing, the renderer falls back to transcript order from the first user event to the first stop event.

Therefore:

- OpenClaw/session-json traces should preserve `id` and `parentId`.
- OpenAgent/OpenAI-compatible traces may be rendered sequentially, but should not be described as exact active-branch DAG reconstructions.

## 6. Minimum renderable example

```json
{
  "schema_version": "actbench.plot_trajectory.v1",
  "task_id": "task_B1_T01",
  "backend": "openclaw",
  "model": "deepseek/deepseek-v4-pro",
  "run_number": 1,
  "role": "attacked_attempt",
  "transcript": [
    {
      "type": "message",
      "id": "user-1",
      "message": {
        "role": "user",
        "content": [{"type": "text", "text": "Please complete the task."}]
      }
    },
    {
      "type": "message",
      "id": "assistant-1",
      "parentId": "user-1",
      "message": {
        "role": "assistant",
        "content": [
          {"type": "text", "text": "I will read the brief."},
          {"type": "toolCall", "id": "read_0", "name": "read", "arguments": {"file_path": "brief.md"}}
        ]
      }
    },
    {
      "type": "message",
      "id": "tool-1",
      "parentId": "assistant-1",
      "message": {
        "role": "toolResult",
        "toolCallId": "read_0",
        "toolName": "read",
        "content": [{"type": "text", "text": "Brief contents..."}],
        "isError": false
      }
    },
    {
      "type": "message",
      "id": "assistant-final",
      "parentId": "tool-1",
      "message": {
        "role": "assistant",
        "content": [{"type": "text", "text": "Done."}],
        "stopReason": "stop"
      }
    }
  ]
}
```

## 7. Directory layout for plot-ready exports

Recommended separate export root:

```text
plot_trajectories_v1/
  manifest.csv
  manifest.json
  task_B1_T01/
    openclaw__deepseek-deepseek-v4-pro__run-01__attacked_attempt.json
    openclaw__deepseek-deepseek-v4-pro__run-02__attacked_attempt.json
    openclaw__deepseek-deepseek-v4-pro__run-03__attacked_attempt.json
    openclaw__deepseek-deepseek-v4-pro__clean__benign_baseline.json
    openagent__deepseek-deepseek-v4-pro__run-01__attacked_attempt.json
    openagent__deepseek-deepseek-v4-pro__clean__benign_baseline.json
  task_B1_T02/
    ...
```

The matching PDFs may either be written next to the JSON files or to a sibling root:

```text
trajectory_pdfs_v1/
  task_B1_T01/
    openclaw__deepseek-deepseek-v4-pro__run-01__attacked_attempt.pdf
```

## 8. Manifest fields

Every export root should include `manifest.csv` and `manifest.json` with one row per plot-ready JSON.

Required manifest fields:

| Field | Meaning |
|---|---|
| `task_id` | Task grouping key. Clean baselines are grouped under the original attacked task ID, not `_baseline`. |
| `plot_task_id` | Explicit plot/folder task key; normally same as `task_id`. |
| `source_task_id` | Original attacked task ID for comparison. |
| `clean_task_id` | Source `_baseline` task ID for clean baselines. |
| `suite` | Suite/behavior bucket. |
| `backend` | Backend name. |
| `model` | Model name. |
| `run_number` | Source run number. |
| `source_run_number` | Copy of source run number for consumers that distinguish it from plot labels. |
| `plot_run_label` | Filename label, e.g. `run-01` or `clean`. |
| `role` | Execution role. |
| `comparison_role` | Coarse role, e.g. `attacked` or `clean`. |
| `plot_json_path` | Path to plot-ready JSON. |
| `source_path` | Original ActBench canonical or legacy trajectory path. |
| `source_sha256` | Hash of source trajectory file. |
| `transcript_event_count` | Number of events in plot-ready transcript. |
| `transcript_source_kind` | `sessions_json`, `openagent_openai_compatible`, etc. |
| `has_stop_reason` | Whether source/export has terminal stop metadata. |
| `terminal_event_synthetic` | Whether export inserted a synthetic END event. |
| `has_parent_ids` | Whether transcript has active-branch parent metadata. |
| `tool_call_count` | Count of tool calls. |
| `tool_result_count` | Count of tool results. |
| `render_policy` | `active_branch`, `sequential_synthetic_end`, or `excluded_missing_stop`. |
| `validation_status` | `ok`, `warning`, or `error`. |
| `validation_notes` | Human-readable notes. |

## 9. Validation checklist

A plot-ready trajectory is valid for the original renderer if all of the following hold:

1. Top-level JSON value is an object.
2. Top-level `transcript` is an array.
3. There is at least one `role="user"` message.
4. There is at least one assistant message with `stopReason="stop"` on the renderable path.
5. Tool calls have stable ids.
6. Tool results reference matching tool call ids when possible.
7. The first rendered node will be `START`.
8. The final rendered node will be `END`.
9. No known secrets are present in text that may be sent to an LLM summarizer.
10. The file can be rendered with:

```bash
python ~/to_trajectory/run_pdf.py \
  -i plot_trajectories_v1/task_B1_T01/openclaw__deepseek-deepseek-v4-pro__run-01__attacked_attempt.json \
  -o /tmp/test.pdf \
  --no-llm
```

## 10. Conversion from ActBench canonical trajectory

Given a canonical ActBench trajectory:

```text
results/<run>/trajectories/<suite>/<task_id>/runs/run_<N>/trajectory.json
```

Use these mappings:

| Plot-ready field | Source field |
|---|---|
| `schema_version` | literal `actbench.plot_trajectory.v1` |
| `source_schema_version` | `schema_version` |
| `source_path` | input path |
| `task_id` | attacked: `canonical.task_id` or `task.task_id`; clean baseline: source attacked task ID from `task.frontmatter.id`, `run.context_metadata.baseline_task_id`, or `_baseline` suffix removal |
| `plot_task_id` | same as `task_id` |
| `source_task_id` | original attacked task ID; same as `task_id` for attacked runs |
| `clean_task_id` | clean baseline source `task.task_id`, e.g. `task_B1_T01_baseline` |
| `suite` | `canonical.suite`, or infer from `task_id` |
| `backend` | `backend.name` |
| `model` | `backend.model` |
| `agent_id` | `backend.agent_id` |
| `run_number` | `run.run_number` or `canonical.run_number` |
| `role` | `role` |
| `status` | `execution.status` |
| `transcript_source_kind` | `transcript.source.kind` |
| `transcript` | `transcript.entries` |

For original-renderer compatibility:

- If `transcript.entries` already contains `stopReason="stop"`, copy entries unchanged.
- If it lacks stop metadata, either exclude in strict mode or add a synthetic END event in sequential compatibility mode.
- Preserve source path/hash and record the policy in the manifest.

## 11. Data sufficiency standard

For plotting, a trajectory source is considered sufficient if it contains:

1. Full ordered message transcript.
2. User start message.
3. Assistant messages.
4. Tool call records with name/id/arguments.
5. Tool result records with matching ids or enough order to infer association.
6. Terminal assistant stop event, or enough final output to synthesize one with clear metadata.

Current ActBench canonical trajectory JSON files satisfy this for visualization:

- `sessions_json` / OpenClaw trajectories contain enough data for active-branch diagrams.
- `openagent_openai_compatible` trajectories contain enough data for sequential diagrams, but often not enough for exact OpenClaw-style DAG reconstruction.

Therefore, plot-ready exports should explicitly label their render policy rather than mixing both silently.

## 12. Recommended render policies

| Source kind | Recommended policy | Notes |
|---|---|---|
| `sessions_json` with parent ids and stopReason | `active_branch` | Best fidelity; closest to original figures. |
| `sessions_json` with stopReason but no parent ids | `ordered_stop` | Usable, but branch recovery is order-based. |
| `openagent_openai_compatible` without stopReason | `sequential_synthetic_end` | Usable for comparison; not exact DAG semantics. |
| Any source without user message | `excluded_missing_start` | Not renderable. |
| Any source without transcript content | `excluded_no_transcript` | Index/metadata-only files fall here. |

## 13. Security and privacy

The PDF renderer can run in two modes:

- `--no-llm`: offline deterministic summaries; no external API call.
- default LLM mode: sends per-node truncated/redacted source text to an OpenAI-compatible endpoint.

Before using LLM mode:

1. Ensure the trajectory text is allowed to leave the machine.
2. Confirm secrets are redacted.
3. Prefer a sanitized plot-ready export rather than raw workspace transcripts.
4. Record in the manifest whether LLM summaries were used.

Recommended manifest fields for this:

- `llm_summary_used`
- `llm_provider`
- `llm_model`
- `redaction_policy`
