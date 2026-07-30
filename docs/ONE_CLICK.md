# ActBench one-command testing

`actbench-test` is the convenience path for a bounded ActBench run. It wraps the existing two-stage workflow:

1. collect target-agent trajectories with `actbench`, and
2. score only those invocation-local trajectories with `actbench-score`.

It does **not** replace the lower-level runner or scorer. Use the lower-level commands when you need custom recovery, baseline-only preparation, raw-by-task packing, or publication tooling.

## Quick start

From a source checkout after `uv sync`:

```bash
uv run actbench-test \
  --backend claudecode \
  --model <target-model> \
  --judge-model private/gpt-5.5
```

The command prints the resolved plan before execution and writes all artifacts under a fresh directory in `results/one_click/`.

## Self-test

Validate local ActBench plumbing without calling a real target model or an external judge:

```bash
uv run actbench-test --self-test
```

Self-test forces:

- backend: `fake`
- model label: `fake/self-test`
- suite: `task_B9_T01`
- runs: `1`
- baseline generation: skipped
- scoring: `automated`

This exercises task loading, workspace materialization, mock services, artifact recording, canonical trajectory writing, and offline automated scoring. It is not a model evaluation.

## Defaults for real runs

A real `actbench-test` run requires explicit `--backend`, `--model`, and (for the default scoring mode) `--judge-model`.

Default behavior:

| Setting | Default |
| --- | --- |
| Suite | `representative` |
| Representative tasks | `task_B1_T01` through `task_B15_T01` |
| Runs | `1` per task |
| Same-task workers | `1` |
| Baselines | generate/reuse clean baselines |
| Scoring | `combined-ags` |
| Output root | `results/one_click` |

The representative suite is a fixed one-task-per-B-class subset:

```text
task_B1_T01, task_B2_T01, task_B3_T01, task_B4_T01, task_B5_T01,
task_B6_T01, task_B7_T01, task_B8_T01, task_B9_T01, task_B10_T01,
task_B11_T01, task_B12_T01, task_B13_T01, task_B14_T01, task_B15_T01
```

Change the selection with any existing ActBench selector:

```bash
uv run actbench-test --backend claudecode --model <target-model> --judge-model private/gpt-5.5 --suite task_B9_T01
uv run actbench-test --backend claudecode --model <target-model> --judge-model private/gpt-5.5 --suite B9
uv run actbench-test --backend claudecode --model <target-model> --judge-model private/gpt-5.5 --suite all
```

`--suite all` is explicit and can run all 300 public tasks.

## Scoring modes

### Combined AGS (default)

```bash
uv run actbench-test \
  --backend claudecode \
  --model <target-model> \
  --judge-model private/gpt-5.5
```

Combined AGS replays each trajectory with Python automated evidence plus an external LLM judge. Because this can spend time and judge-provider credits, `actbench-test` requires an explicit `--judge-model` in this mode.

### Automated-only scoring

```bash
uv run actbench-test \
  --backend claudecode \
  --model <target-model> \
  --score-mode automated
```

Automated-only scoring reruns local Python checks against durable `workspace_after/` snapshots. It does not call an external judge and does not compute the official combined AGS score.

## Baselines

Real runs preserve the runner's default baseline behavior: missing clean baselines are generated before attacked attempts when a clean scene is available, and existing valid baselines are reused.

This improves delta-aware evidence, but the first run for a new backend/model can execute additional clean scenarios. To skip baseline generation for a faster run:

```bash
uv run actbench-test \
  --backend claudecode \
  --model <target-model> \
  --judge-model private/gpt-5.5 \
  --skip-baseline-gen
```

If baseline evidence is missing in the collection aggregate, `actbench-test` records a warning in `one_click_result.json` and prints it in the final summary. Missing baseline evidence is not converted into a fake score.

## Backend setup

`actbench-test` intentionally uses the existing backend adapters. It validates the selected backend name, task selector, task loadability, and same-task worker support, then delegates backend-specific setup to the normal runner initialization path.

Backend notes:

- `openclaw`: requires the OpenClaw CLI on `PATH` and mutates OpenClaw agent/session state as the normal runner does.
- `qwenpaw`: requires a running QwenPaw service; see the QwenPaw section in `README.md`.
- `openagent`: requires a running OpenAgent service, API key, Store setup, and ActBench MCP configuration; see `docs/OPENAGENT.md`.
- `hermes`: requires the Hermes CLI and provider credentials visible to isolated attempt homes; see `docs/HERMES.md`.
- `opencode`: requires opencode CLI/provider setup; see `docs/OPENCODE.md`.
- `claudecode`: requires Claude Code CLI/provider setup; see `docs/CLAUDECODE.md`.
- `fake`: deterministic plumbing backend for self-test and local tests only.

For OpenAgent, remember that ActBench records and sends `--model`, but the actual provider/model/tools can be controlled by the OpenAgent Store associated with the API key.

## Output layout

A successful run writes a fresh invocation directory like:

```text
results/one_click/20260729T142533Z-a1b2c3d4/
  one_click_result.json
  collection.log
  scoring.log
  score.json
  actbench.log
  benchmark.log
  collection/
    <run_id>_<model>.json
    actbench_summary_<run_id>_<model>.json
    trajectory_index.json
    trajectories/
      <B-class>/<task_id>/runs/run_<n>/trajectory.json
    <run_id>_<model>_artifacts/
      ...
```

`score.json` is the full `actbench.offline_score.v1` payload. `one_click_result.json` is the wrapper summary. It includes:

- request/config fields, without environment variables or secrets,
- resolved task IDs and expected attempts,
- collection and scoring child commands,
- collection result paths and canonical trajectory counts,
- baseline coverage/warnings,
- score metrics such as mean AGS, ASR, pass@k, and `attack_reproduced`, and
- any failure type/message.

## Exit codes

| Code | Meaning |
| ---: | --- |
| `0` | Collection and scoring completed with all expected valid scores |
| `2` | CLI usage or preflight error |
| `3` | Collection subprocess failed or collection output was incomplete/invalid |
| `4` | Scoring subprocess failed or score output was malformed/invalid |
| `5` | Partial scoring result, such as `evaluation_errors > 0` |
| `130` | Interrupted by the user |

A successful infrastructure exit (`0`) does not mean the model was safe. Check `attack_reproduced` and AGS/ASR fields. If `attack_reproduced: true`, the attack succeeded in the benchmark.

## Advanced runs

Use lower-level commands when you need controls not exposed by `actbench-test`, such as targeted `--run-number` recovery, baseline-only generation, raw-by-task packing, utility/UGS scoring, publication bundle construction, or custom artifact handling.

The equivalent two-stage shape is:

```bash
uv run scripts/actbench.py \
  --backend <backend> \
  --model <target-model> \
  --suite <selector> \
  --output-dir results/my_run

uv run scripts/actbench_score.py \
  --trajectory results/my_run/trajectories \
  --mode combined-ags \
  --judge-model <judge-model> \
  --output results/my_run/offline_score.json
```
