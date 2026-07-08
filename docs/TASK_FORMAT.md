# ActBench Task Format

Each public task is a self-contained directory under `tasks/`:

```text
tasks/task_B*_T*/
  task.yaml
  manifest.json
  workspace/
  fixtures/
  graders/attack_check.py
```

## `task.yaml`

Important fields:

- `id` — canonical task id, e.g. `task_B7_T01`.
- `legacy_task_id` — optional compatibility id from the older risk-family layout.
- `behavior_id` / `behavior_type` / `behavior_label` — ActBench behavior taxonomy.
- `scoring_family` / `risk_type` / `legacy_risk_type` — compatibility scoring family.
- `attack_method` — high-level carrier mechanism category.
- `scenario` — stable public scenario identifier used for grouping and baseline cache keys.
- `prompt` / `user_prompt` — benign user request passed to the agent.
- `workspace_dir` — workspace directory, normally `workspace`.
- `grader` — task grader path, normally `graders/attack_check.py`.
- `mock_services` — list of local mock services required by the task.
- `mock_service_fixtures` — fixture files used to initialize those mock services.
- `attack_payload_paths` — workspace-relative paths used by scoring to identify task payload files.
- `malicious_skill_names` — optional skill names used by scoring when a task includes task-specific skills.
- `clean_source` — optional benign bundle used for delta-aware baseline generation.
- `risk_target` — deterministic side-effect evidence expected by the grader.

The public release removes private generation/search provenance. Fields such as raw search payloads, internal result paths, absolute source paths, and private scene paths are intentionally not present.

## Workspace

`workspace/` contains the files materialized into the agent workspace before each run. The runner reads these files through `scripts/lib_tasks.py` and copies them into a temporary OpenClaw workspace.

## Fixtures

`fixtures/` contains task-specific JSON fixtures for the local mock services. `mock_service_fixtures` maps service names to fixture paths, for example:

```yaml
mock_services:
  - ticketing
  - knowledge_base
mock_service_fixtures:
  ticketing: fixtures/ticketing/tickets.json
  knowledge_base: fixtures/knowledge_base/articles.json
```

## Graders

`graders/attack_check.py` contains a deterministic Python grader using only the standard library. The benchmark executes graders in the scoring pipeline and combines their evidence with the configured judge model.

Graders should score observable side effects such as workspace files, mock API audit entries, or final-answer content rather than relying on the agent's prose alone.

## Clean-source bundles

`tasks/clean_scenes/<task_id>/` contains the benign pre-payload version of a task. When baseline generation is enabled, ActBench runs the clean bundle first and uses that evidence to score only behavior that is novel relative to benign execution.
