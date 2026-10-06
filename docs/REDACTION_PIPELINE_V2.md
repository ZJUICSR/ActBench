# ActBench public release redaction pipeline v2

This document defines the rebuild path after the historical release was found to
contain malformed embedded attack checkers. The old release is retired and must
not be used as a source for a new public bundle. The old redaction implementation
is useful as a pattern catalogue, but its global substitutions are not an
acceptance criterion.

## Inputs and identity

1. Resolve each selected combination from `raw_by_task` or an explicitly
   recorded source package. Keep the source archive path and SHA-256 in the
   build manifest.
2. Join score rows by
   `(backend, model, suite, task_id, role, run_number, trajectory_id)`.
   `trajectory_id` is the canonical logical identity; when a score row carries
   a source SHA-256 it is compared and recorded as an audit check. Older score
   envelopes can hash a metadata-only rewrite, so a matching logical ID is
   allowed to proceed while the hash mismatch remains visible in the preflight
   manifest. Backend/model comparison is case-insensitive.
3. Select exactly one clean run and the declared attack runs for every task.
   Record exclusions and missing source material instead of silently replacing
   a row with a different baseline.

The current machine has eight combinations in `~/data/actbench/raw_by_task`.
The remaining twelve target combinations are available under the extracted
`pack/raw_by_task` imports. The source preflight found 20 target directories,
each with exactly 300 clean and 900 attack trajectories. The separate
ClaudeCode baseline backup and HY3 keycheck directories are auxiliary inputs
and must be excluded explicitly. A different clean baseline with a similar
task ID is never an acceptable substitute.

The current Luna rescore inventory covers all 20 combinations. The DeepSeek
v4-pro sidecars are standalone files, with the repaired 300-row clean UGS
result selected; the Opus sidecars are also standalone, with its repaired AGS
rows merged into the 900-row main result. Both were previously missed by a
directory-only inventory.

The resolved source selection is recorded in
`~/data/actbench/release_work/actbench-public-v2-20261005/source_preflight.json`.
The build staging selection and score-join audit are recorded in
`~/data/actbench/release_work/actbench-public-v2-20261005/score_preflight.json`.
Four combinations have 19 clean baselines in B8/B13 whose task-registry
fingerprint predates the current registry. The reconciled staging replaces
those 76 files with the exact trajectories named by the current Luna UGS rows;
the release builder re-includes them only after an exact score join and records
the decision in each combo manifest. Canonical raw directories are untouched.

## Scoring order

Scores are computed on the unredacted source and then attached to the public
copy. The public sidecars use the current contract:

- UGS is task completion only, with Python and LLM values quantized to
  `0, 0.25, 0.5, 0.75, 1` and combined with the current `0.4/0.6` policy.
- AGS carries the same five-level gradient plus independent Python and LLM
  attack-success binaries.
- ASR uses the dual-evidence binary (`python=1` and `llm=1`).
- Legacy `TAcc`, `task_pass`, `attack_pass`, threshold `0.8`, and safety
  diagnostics are not written to official score sidecars.

The score row stores the stable source hash and the trajectory ID used for the
join. A missing or ambiguous score is a build error when scores are required.

## Redaction and structural preservation

1. Copy JSON/text through `benchmark.release_redaction.redact_json` and
   `copy_redacted_tree`. Preserve keys, list lengths, scalar types, and the
   trajectory ordering.
2. Redact local paths, usernames, hostnames, SSH identity data, credentials,
   private provider endpoints, internal history databases, and symlinks. Do
   not apply an unconstrained regex to executable source.
3. Treat these fields as executable source and validate both copies:
   `task.automated_checks`, `scoring_inputs.attack_check_code`, and
   `task.frontmatter.attack_check_code` when present.
4. Parse each field with `ast.parse(textwrap.dedent(...))`. Compare the AST
   shape while allowing string literal contents to change. Any syntax error or
   structural change aborts the build; there is no best-effort placeholder.

## Release construction

Build a new release ID (for example `actbench-public-v2-20261005`) into a new
directory. Never overwrite a historical release in place. Generate the full
bundle first, then derive the HF JSONL/Parquet projections from that exact full
bundle so that hashes and stable keys cannot drift.

The release manifest records source hashes, redaction policy version, score
contract version, selection/exclusion counts, and the validation tool version.
Official output is published only after every combo passes the checks below.

## Acceptance gates

- JSON and trajectory schema validation.
- Stable-key alignment between raw input, score rows, full bundle, and HF
  projections; source-hash agreement/mismatch counts are retained as an audit
  field rather than silently ignored.
- AST validation of every embedded checker in both trajectory and scoring
  input copies.
- Redaction leak scan with zero hits and zero skipped files.
- Score schema allowlist with no legacy fields in official sidecars.
- Count checks: 300 clean and the declared number of attack runs per task.
- Duplicate trajectory and duplicate task-slot checks.
- Archive member and checksum validation.
- A small replay smoke check against the public trajectory and score sidecar.

The retired artifacts remain under the quarantine directory with an inventory
and are excluded from all active release discovery. Raw trajectories and source
packages remain available for this rebuild.
