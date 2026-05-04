# NLE-Bench Harness

This directory contains the executable benchmark harness for the NLE-Bench
v3.1 submission artifact.

## Install

From this directory:

```bash
python -m pip install -e .
```

For local test development, install pytest as well:

```bash
python -m pip install -e .
python -m pip install pytest pytest-asyncio
PYTHONPATH=src python -m pytest tests/
```

Use `PYTHONPATH=src` or an editable install in a clean environment so tests
import this submitted package rather than another local `nlebench` checkout.

The default scenario root is
`src/nlebench/dataset/scenarios_v3_1`, containing 800 YAML scenarios:
200 `dev` and 600 `test`.

## Validate Scenario Corpus

```bash
PYTHONPATH=src python scripts/validate_scenarios.py
```

This validates the active `scenarios_v3_1` corpus by default: YAML loading,
package schema checks, v3.1 nested path/taxonomy consistency, ID/file-name
consistency, and the 800/200/600 corpus split counts. The historical
`scripts/validate_scenarios_v2.py` name is kept only as a compatibility wrapper
and calls the same v3.1 validator. Obsolete v1/v2 authoring generators are not
included in this review artifact; v3 and v3.1 YAML records are the preserved
corpus provenance.

## Audit Instruction-To-Constraint Coverage

```bash
PYTHONPATH=src python scripts/audit_instruction_constraint_coverage.py \
  --markdown-out ../results/instruction_constraint_coverage_audit.md \
  --csv-out ../results/instruction_constraint_coverage_flags.csv
```

This supplementary audit scans feasible-scenario instructions for surface
numeric timing, duration, split-position, and spatial-position cues, then checks
whether required constraints contain obvious matching fields or named
predicates. It is deliberately heuristic and exits successfully when it finds
candidates. A flag means "inspect this scenario"; it is not a validator error,
does not compare the exact numeric values, and does not prove that either the
instruction or the constraint set is wrong.

## Audit And Rescore Attribute Direction

```bash
PYTHONPATH=src python scripts/audit_attribute_changed_direction.py \
  --markdown-out ../results/attribute_changed_direction_audit.md \
  --json-out ../results/attribute_changed_direction_audit.json \
  --csv-out ../results/attribute_changed_direction_flags.csv

NLEBENCH_RAW_RESULTS_ROOT=/path/to/raw/results \
  PYTHONPATH=src python scripts/rescore_attribute_changed_direction.py --write-results
```

The `attribute_changed` scorer enforces `direction: increase`,
`direction: decrease`, and `direction: any` for numeric fields. Nonnumeric
fields keep changed-only semantics, and invalid directions are validator
errors. The rescore command requires raw logs with state JSON; the included
audit documents that all prior successes had enough state to rescore and that
missing-state records were already failures.

## Scenario Schema Notes

The v3.1 YAML schema keeps several legacy or forward-compatible fields:
`expected_behavior`, `required_capability`, `missing_parameters`,
`gold_intent.expected_ops`, `gold_intent.param_ranges`, and
`reference_solution`. They are null or empty in all 800 submitted scenarios.
The active validator treats the taxonomy class, named constraints, and
detector-side refusal/clarification behavior as authoritative. In particular,
paper SR-ambiguous is a clarification-without-state-change proxy; it does not
score whether a response asks for a specific missing parameter.

## Run

```bash
python -m nlebench --provider openai --model gpt-5.4 \
  --reasoning-effort medium --track canonical --quick
```

Full runs write `results.jsonl`, `summary.json`, and config metadata under
`results/<timestamp>_<model>/`. Per-scenario API call transcripts are emitted by
the run harness but are not bundled in the anonymous supplementary zip to avoid
prompt fingerprinting and to keep the review artifact size bounded.
Default model names are aligned to the paper-era reference rows:
`claude-sonnet-4-6-2026-02-17`, `gpt-5.4`, `gemini-3-flash-preview`, and
`Qwen/Qwen3-32B`. For GPT-5.x runs, the paper setting is
`--reasoning-effort medium` (or `OPENAI_REASONING_EFFORT=medium`).

## Analysis And Table Regeneration

- `scripts/analyze_run.py` summarizes a completed `results.jsonl` run using the
  v3.1 scenario taxonomy.
- `scripts/paper_v4_analysis.py` reproduces the appendix BPM and factorial
  diagnostics when the internal run directories named in the script are present.
- `scripts/regenerate_tables.py` reads
  `../results/main_results_recomputable.csv` plus
  `../results/run_manifest.csv` by default. Its default aggregate view uses the
  clean canonical paper row set (`--row-set paper-clean-tool`, 52 full-800
  tool-use rows), so attempted-only context-window-overflow rows are excluded
  unless `--row-set recomputable` is requested. Useful reviewer commands:
  - `python scripts/regenerate_tables.py --table row-filter`
    lists all aggregate rows as paper-clean, direct-generation, attempted-only,
    or provenance-only.
  - `python scripts/regenerate_tables.py --table per-class --row-set paper-main --limit 0`
    recomputes the main-table-style per-class summaries from redacted
    per-scenario validation fields. SR-infeasible is detector provenance in
    this output; response-level refusal-audit labels are not included in the
    anonymous bundle.
  - `python scripts/regenerate_tables.py --table aggregate --row-set recomputable`
    shows every reconciled aggregate row, including attempted-only overflow and
    direct-generation rows.
  - `python scripts/regenerate_tables.py --table error-types --row-set recomputable`
    summarizes the existing redacted `error_message_type` field into coarse
    provider/runtime categories. This is an artifact-audit diagnostic, not a
    validated taxonomy of task misunderstandings.
  The script can optionally write a legacy expected-path manifest with
  `--write-preview-manifest` (or deprecated alias `--manifest`), but does not
  overwrite the reviewed manifest by default.
- `scripts/generate_review_artifacts.py` matches `../results/main_results.csv`
  to raw run summaries when `NLEBENCH_RAW_RESULTS_ROOT` points to the raw run
  root and writes the reviewer-facing redacted result artifacts:
  `../results/run_manifest.csv`, `../results/run_summaries_redacted.jsonl`,
  `../results/per_scenario_results_redacted.csv`, and
  `../results/result_reconciliation.csv`.

The submitted supplementary package includes aggregate CSV results, matched
redacted per-scenario artifacts, and a run manifest with source-file hashes, but
not full prompts, assistant responses, tool arguments, or state JSON. Re-running
the benchmark regenerates those raw logs from the public harness.
