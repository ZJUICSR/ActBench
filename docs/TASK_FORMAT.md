# ActBench Task Format

Each public attacked task is a self-contained directory under `tasks/`:

```text
tasks/task_B*_T*/
  task.yaml
  manifest.json
  workspace/
  fixtures/
  graders/attack_check.py
```

Clean source bundles used for benign baselines live under
`tasks/clean_scenes/task_B*_T*/` and use `scenario.yaml`.

## `task.yaml`

The task file contains the execution contract and the current B1-B15 behavior
taxonomy. The public fields are:

- `id`, `name` — stable task identity and display name.
- `behavior_id`, `behavior_type`, `behavior_label` — canonical behavior label.
- `scoring_family` — the B-class scoring bucket (`B1`-`B15`).
- `taxonomy_version` — taxonomy schema version.
- `attack_method` — carrier mechanism used by the task.
- `scenario` — clean-source scenario id used for grouping and baseline cache keys.
- `grading_type`, `timeout_seconds` — execution and grading settings.
- `user_prompt` — the benign user request passed to the agent.
- `expected_behavior`, `grading_criteria` — the task contract shown to scoring.
- `grader` — deterministic grader path, normally `graders/attack_check.py`.
- `attack_goal` — observable attack objective used by scoring.
- `clean_source` — relative clean bundle path and content hash for baseline checks.
- `mock_services`, `mock_service_fixtures` — local services and fixture files.
- `attack_payload_paths` — optional payload paths. Workspace payloads are
  relative to `workspace/`; fixture payloads are relative to the task bundle.
- `secret_declarations` — optional synthetic secrets materialized for the task.
- `risk_target` — optional deterministic side-effect evidence expected by the grader.

The task loader defaults `workspace_dir` to `workspace`; it is therefore not
stored in every task. The older R-class fields, duplicate prompt, legacy task
ids, and generation-time behavior inference notes are not part of the public
task schema. Runtime code still accepts those fields when reading historical
trajectory artifacts.

## Workspace, fixtures, and graders

`workspace/` contains files materialized into the agent workspace before each
run. `fixtures/` contains task-specific JSON for local mock services. The
`mock_service_fixtures` mapping uses paths relative to the task directory.

`graders/attack_check.py` scores observable side effects such as workspace
files, mock API audit entries, and modified deliverables. It uses only the
standard library.

## Clean-source bundles

`tasks/clean_scenes/<task_id>/` contains the benign pre-payload workspace and
the grader entry under `graders.attack`. Its scenario file keeps the stable
scenario id, user prompt, workspace file list, mock-service fixtures, secret
declarations, and canonical B-class labels needed for baseline execution.
Attack goals and risk targets stay on the attacked task, where they are
consumed by scoring.

## Integrity manifests

Each `manifest.json` is a small file-integrity manifest. It records hashes and
relative paths for workspace files, fixtures, and the grader, plus the stable
task or scenario id. It contains no release labels, source paths, author
metadata, or generation provenance.
