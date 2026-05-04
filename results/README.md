# Aggregated Results (v3.1)

This directory contains aggregated benchmark results.

## Files

- `main_results_recomputable.csv` — Recomputable per-(model, configuration)
  aggregate Success Rate (SR) source table.
  - Contains 57 rows, all of which reconcile to included redacted
    per-scenario validation artifacts.
  - This is not identical to the clean paper row set: it also contains two
    direct-generation rows and three attempted-only context-window-overflow
    rows retained for recomputation/provenance.
  - `code/scripts/regenerate_tables.py` reads this file by default together
    with `run_manifest.csv`; its default row set is `paper-clean-tool` (52
    canonical full-800 tool-use rows), excluding the attempted-only rows.
    Pass `--row-set recomputable` to include all 57 reconciled rows.
  - Columns: `model, provider, track, total_runs, successful_runs, sr, timestamp`
  - Filtered to runs dated 2026-04-18 or later (v3.1 release date).
  - Success counts reflect the patched `attribute_changed.direction` scorer
    applied to the available raw `results.jsonl` state logs.
- `main_results.csv` — Provenance-inclusive aggregate table.
  - Columns: `model, provider, track, total_runs, successful_runs, sr, timestamp`
  - Filtered to runs dated 2026-04-18 or later (v3.1 release date).
  - 58 aggregate rows total. 57 reconcile to included redacted
    per-scenario artifacts; one excluded/non-recomputable preview API row is
    marked `excluded_nonrecomputable` in `result_reconciliation.csv`.
  - Use this file for provenance audit, not for default ranking or
    paper-analysis regeneration.
- `excluded_nonrecomputable_rows.csv` — One-row table containing the excluded
  preview API aggregate row that is retained for provenance but omitted from
  `main_results_recomputable.csv`.
  - A row is a model/configuration pair, not necessarily a distinct base
    checkpoint. Repeated configurations for GPT-5.4, gpt-5.4-mini, and
    Sonnet 4.6 appear separately.

- `instruction_constraint_coverage_audit.md` — Generated heuristic report from
  `../code/scripts/audit_instruction_constraint_coverage.py`. It scans feasible
  instructions for surface timing, duration, split-position, and spatial-position
  cues and reports cases where required constraints do not expose an obvious
  corresponding field or named predicate. These are human-review candidates, not
  validator failures.
- `instruction_constraint_coverage_flags.csv` — CSV form of the flagged
  scenario rows from the same heuristic audit.
- `attribute_changed_direction_audit.md/json/csv` — Generated audit from
  `../code/scripts/audit_attribute_changed_direction.py`. It enumerates all
  feasible scenarios using `attribute_changed.direction`: 112 scenarios,
  116 constraints, 108 likely numeric constraints, and 0 invalid directions.
- `attribute_changed_direction_rescore_audit.md/json` — Generated audit from
  `../code/scripts/rescore_attribute_changed_direction.py`. It documents raw
  log state coverage and the patched rescore: all prior successes had
  initial/final states; missing-state records were already failures; local
  unpatched-release paper-main successes on direction scenarios changed from
  1341 to 1301 after enforcing direction.
- `run_summaries_redacted.jsonl` — One redacted summary record per
  aggregate row, including source hashes for the matched raw `summary.json`
  and `results.jsonl`.
- `per_scenario_results_redacted.csv` — Redacted per-scenario/per-run
  validation table. It includes scenario taxonomy, split, success/TSR/CSR,
  detector behavior fields, behavior class, latency/tokens/cost, tool-name
  counts, and hashes of omitted raw fields. Public scenario identifiers are in
  `scenario_id`; `legacy_scenario_id` preserves the pre-release `NLB-v3-*`
  identifier for audit joins. It omits prompts, assistant responses, full tool
  arguments, and state JSON.
- `redacted_dev_trajectory_samples.jsonl` — Six dev-split trajectory samples
  selected from existing raw results. They include scenario turns, validation
  summaries, source line/hash provenance, tool-call names and arguments, and
  full dev initial/final state JSON. Assistant responses are represented by
  SHA256 plus short reasoning-stripped final-answer excerpts when available.
- `redacted_dev_trajectory_samples_README.md` — Schema, scope, and redaction
  notes for the dev trajectory sample.
- `run_manifest.csv` — Generated manifest mapping each aggregate CSV row to
  the included redacted artifacts and the matched raw-source hashes.
- `result_reconciliation.csv` — Automated reconciliation report comparing
  each aggregate row against the matched raw JSONL count and success sum.
- `refusal_audit_status.json` — Documents that the dual-judge refusal audit is
  aggregate-only in the anonymous bundle; response-hash-keyed judge labels were
  not recoverable for anonymous review.
- `scenario_v3_to_v3_1_file_manifest.csv` — File-level SHA256 comparison
  between the frozen v3 and canonical v3.1 scenario corpora. This is a
  byte-level manifest, not a semantic-diff table: all 800 YAMLs changed because
  every file received an anonymized `metadata.annotators` normalization. After
  removing only that metadata field, 456 files are identical and 344 contain
  non-metadata content changes.
- `../data/scenario_id_mapping.csv` — Public-to-legacy scenario-id map for
  joining current `NLEB-*` records with pre-release logs or external notes that
  used `NLB-v3-*` identifiers.

## Row sets

- `paper-clean-tool`: 52 reconciled canonical full-800 tool-use rows used for
  paper tool-use analyses after excluding attempted-only context-window
  failures.
- `paper-main`: 15 representative non-text-fallback rows from the main
  per-class table.
- `paper-open-track`: 2 reconciled direct-generation rows used only for the
  channel-fair feasible-task comparison.
- `recomputable`: all 57 reconciled rows in `main_results_recomputable.csv`,
  including the 3 attempted-only context-window-overflow rows and 2 open-track
  rows.
- `provenance-only`: aggregate rows retained for audit but not recomputable
  from the redacted per-scenario artifact, currently the excluded
  `gemini-3.1-pro-preview` row in `excluded_nonrecomputable_rows.csv`.

Run `cd ../code && python scripts/regenerate_tables.py --table row-filter` for
the row-by-row status table. Run:

```bash
python scripts/regenerate_tables.py --table per-class --row-set paper-main --limit 0
python scripts/regenerate_tables.py --table error-types --row-set recomputable
```

This recomputes main-table-style per-class summaries from
`per_scenario_results_redacted.csv`. It prints detector-provenance
SR-infeasible; the response-level refusal-audit labels are not included in this
anonymous bundle and are not claimed as recovered.
For ambiguous scenarios, SR-ambiguous is a detector/BPM
clarification-without-state-change proxy. The submitted scenario YAMLs do not
populate missing-parameter labels, so this table does not score whether the
model asked for the specific missing parameter.
The `error-types` view summarizes the existing redacted `error_message_type`
field into coarse provider/runtime categories. It is an artifact-audit
diagnostic only: rows without an exception still include ordinary constraint
failures, calibration-behavior failures, malformed-but-parseable tool plans,
and task misunderstandings that cannot be separated without raw traces.
The `validation_ovr` column is a provenance/legacy diagnostic, not a success
metric. Because this anonymous bundle redacts the full raw final states outside
the small dev sample, archived OVR values should not be treated as
independently recomputable from the redacted rows. Current reruns use entity-ID
matching for `expected_changed_entities`, with legacy category-token
compatibility.

## Provenance

These numbers are post-hoc rescored from matched raw `results.jsonl` records
under the raw-results root used during artifact preparation. The source
`summary.json` hashes in `run_manifest.csv` still identify the original
pre-patch harness summaries; the aggregate and redacted per-scenario success
fields reflect the patched scorer. The anonymous review bundle includes
redacted summary and per-scenario validation artifacts
sufficient to recompute aggregate SR, per-class SR (with detector-mediated
non-feasible classes), and 4x4 feasible scenario-cell summaries for rows whose
`run_manifest.csv` status is `reconciled`. It does not include the
response-level labels needed to recompute aggregate-audited refusal
substitutions. It also includes a small redacted dev-only trajectory sample for
representative prompt/response/tool/state inspection without exposing private
test material. One aggregate-only preview API row
(`gemini-3.1-pro-preview`, row_id 55) is marked
`excluded_nonrecomputable`: its matched raw `results.jsonl` is corrupted and
inconsistent with the aggregate summary, and no clean replacement source was
found during artifact preparation. It is retained in `main_results.csv` and
`excluded_nonrecomputable_rows.csv` for aggregate provenance but excluded from
`main_results_recomputable.csv` and redacted per-scenario recomputation
artifacts.

Full per-call logs and full raw trajectories beyond the dev sample are omitted
by default to avoid prompt fingerprinting and to keep the package within
OpenReview size limits. Private/test prompts, private/test assistant responses,
private/test tool arguments, and private/test state JSON are not included.
Users can regenerate full logs by rerunning the harness on public/dev data or
on private data they are authorized to access; private-test server feedback
remains aggregate-only.

The refusal-axis dual-judge audit reported in the paper is not independently
recomputable from this bundle because the per-response judge labels were not
recoverable. `refusal_audit_status.json` records the aggregate diagnostic and
the missing response-hash-keyed fields. If those labels are recovered in a
future release, they should be released keyed by response hash; otherwise exact
audit recomputation is not claimed and future reruns can regenerate labels
under the same schema. Appendix detector-band tables should therefore be read
as raw detector provenance, not as substitutes for the audited agreement-only
bands reported for the eight main narrative rows.

For authoritative paper-analysis results, use the row sets above with
`code/scripts/regenerate_tables.py` or see:
- Paper Table 2 (main results)
- Paper appendix tables (detector-provenance archive listing, per-cell breakdowns, calibration profiles)

Rows retained only for provenance in `main_results.csv`,
`run_summaries_redacted.jsonl`, `run_manifest.csv`, and
`result_reconciliation.csv` should not be interpreted as paper-analysis
rows unless they also appear in the paper tables.

## Tracks

- `canonical`: Tool-based execution (agent issues structured tool calls; harness applies them)
- `open`: Direct-generation baseline (agent emits the modified `EditProject` JSON directly)
- `sensitivity`: 40-instance smoke runs for robustness checks (not used for main results)

## Reproduction

To reproduce a single model's run:
```bash
cd ../code
python -m nlebench --provider <provider> --model <model> --track canonical
```

See `../code/README.md` for full reproduction instructions.

To regenerate the default clean canonical aggregate table:
```bash
cd ../code
python scripts/regenerate_tables.py
```

To inspect row filtering and the main-table-style per-class summaries:
```bash
python scripts/regenerate_tables.py --table row-filter
python scripts/regenerate_tables.py --table per-class --row-set paper-main --limit 0
```

To refresh the instruction-to-constraint coverage audit:
```bash
PYTHONPATH=src python scripts/audit_instruction_constraint_coverage.py \
  --markdown-out ../results/instruction_constraint_coverage_audit.md \
  --csv-out ../results/instruction_constraint_coverage_flags.csv
```

This audit is a transparency tool only. It is designed to surface candidate
coverage gaps for manual review and should not be interpreted as a pass/fail
dataset validator or as proof that flagged scenarios are invalid.

To include all 57 reconciled rows, including attempted-only rows:
```bash
python scripts/regenerate_tables.py --table aggregate --row-set recomputable
```

To refresh the redacted result audit artifacts, the raw run directory must be
available. Set `NLEBENCH_RAW_RESULTS_ROOT` to that directory:
```bash
cd ../code
NLEBENCH_RAW_RESULTS_ROOT=/path/to/raw/results python scripts/generate_review_artifacts.py
```
