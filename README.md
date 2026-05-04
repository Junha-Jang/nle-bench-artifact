# NLE-Bench — NeurIPS 2026 E&D Supplementary Material

This directory contains the supplementary material for the paper **NLE-Bench: Feasibility-Aware Tool Use in Symbolic Non-Linear Video Editing** (NeurIPS 2026 Evaluations & Datasets Track, anonymous submission).

---

## Contents

```
supplementary/
├── README.md                  ← this file
├── CITATION.cff               ← machine-readable citation metadata
├── LICENSE-APACHE-2.0         ← code license
├── LICENSE-CC-BY-4.0          ← data license
├── code/                      ← Anonymized harness (Apache 2.0)
│   ├── src/nlebench/          ← Core package (tools, runner, metrics, providers)
│   │   └── dataset/
│   │       ├── scenarios_v3/         ← frozen v3 corpus
│   │       └── scenarios_v3_1/       ← canonical 800-scenario corpus
│   ├── scripts/               ← Selected analysis utilities
│   ├── tests/                 ← Test suite
│   ├── README.md
│   ├── pyproject.toml
│   ├── Dockerfile
│   └── docker-compose.yml
├── data/                      ← Dataset metadata + human study records (CC BY 4.0)
│   ├── croissant.json         ← Croissant 1.0 metadata
│   ├── human_study.json       ← 1,796 anonymized rater records (L1/L2/L3)
│   ├── human_study_per_row_provenance.csv
│   └── human_study_README.md  ← Schema + reproduction guide
├── docs/
│   └── datasheet.md           ← Datasheet for Datasets (Gebru et al. 2021)
└── results/
    ├── README.md
    ├── main_results_recomputable.csv
    ├── main_results.csv
    ├── excluded_nonrecomputable_rows.csv
    ├── instruction_constraint_coverage_audit.md
    ├── instruction_constraint_coverage_flags.csv
    ├── per_scenario_results_redacted.csv
    ├── redacted_dev_trajectory_samples.jsonl
    ├── redacted_dev_trajectory_samples_README.md
    ├── result_reconciliation.csv
    ├── refusal_audit_status.json
    ├── run_manifest.csv
    └── run_summaries_redacted.jsonl
```

---

## Quick Start

### Reproduce a single model's run

```bash
cd code
pip install -e .
python -m nlebench --provider openai --model gpt-5.4 \
  --reasoning-effort medium --track canonical
```

The harness writes results to `results/<timestamp>_<model>/summary.json` and per-scenario logs to `results/<timestamp>_<model>/calls/`.
Paper-row defaults in the CLI and helper script are aligned to the current
artifact snapshot (`gpt-5.4`, `claude-sonnet-4-6-2026-02-17`,
`gemini-3-flash-preview`, and `Qwen/Qwen3-32B`). For OpenAI GPT-5.x rows,
`--reasoning-effort medium` matches the reported Responses API setting.

### Validate the dataset metadata

```bash
pip install mlcroissant
python -c "import mlcroissant as mlc; ds = mlc.Dataset(jsonld='data/croissant.json'); print(ds.metadata.name, ds.metadata.version)"
```

The included `data/croissant_validation_report.json` records this
programmatic metadata-load check plus manual structural checks. Full
`records('scenarios')` streaming is deferred until the camera-ready hosted
archive URL and sha256 fields replace the anonymous placeholders.

### Validate the scenario corpus

```bash
cd code
PYTHONPATH=src python scripts/validate_scenarios.py
```

`scripts/validate_scenarios_v2.py` is retained as a compatibility wrapper for
older review instructions; it now calls the active v3.1 validator above instead
of looking for the removed `scenarios_v2` tree.

### Audit instruction-to-constraint coverage

```bash
cd code
PYTHONPATH=src python scripts/audit_instruction_constraint_coverage.py \
  --markdown-out ../results/instruction_constraint_coverage_audit.md \
  --csv-out ../results/instruction_constraint_coverage_flags.csv
```

This lightweight audit scans feasible-scenario instructions for surface
numeric timing, duration, split-position, and spatial-position cues, then checks
whether required constraints mention obvious matching fields or named
predicates. It is intentionally heuristic: flags are human-review candidates,
not validator failures, and the script does not prove that a scenario is
correct or incorrect.

### Run the test suite

```bash
cd code
pip install -e .
pip install pytest pytest-asyncio
PYTHONPATH=src pytest tests/
```

Use `PYTHONPATH=src` or run after `pip install -e .` in a clean environment so
pytest imports the submitted package rather than another local `nlebench`
checkout.

### Regenerate paper row filters and clean tables

```bash
cd code
python scripts/regenerate_tables.py --table row-filter
python scripts/regenerate_tables.py --table per-class --row-set paper-main --limit 0
python scripts/regenerate_tables.py --table error-types --row-set recomputable
```

The first command labels rows as clean paper rows, direct-generation rows,
attempted-only context-window failures, or provenance-only rows. The second
recomputes main-table-style per-class summaries from the redacted per-scenario
fields; SR-infeasible is detector provenance because response-level refusal
audit labels are not included in the anonymous bundle. The third command
summarizes the existing redacted `error_message_type` field into coarse
provider/runtime categories; it is not a validated taxonomy of task
misunderstanding, malformed tool calls, or truncation.

### Packaging hygiene

From the source repository root, rebuild the archive with:

```bash
scripts/package_supplementary.sh
```

The script removes and excludes `.pytest_cache`, `__pycache__`, `*.pyc`, and
`*.pyo` artifacts before writing `supplementary.zip`. The essential archive
command is:

```bash
zip -r -X supplementary.zip supplementary \
  -x '*/.pytest_cache' '*/.pytest_cache/*' \
     '*/__pycache__' '*/__pycache__/*' \
     '*.pyc' '*.pyo'
```

---

## Data Provenance

- **800 v3.1 scenarios** organized as a `4 x 4` perception/execution factorial (640 feasible) plus 80 infeasible and 80 ambiguous calibration scenarios.
- **Scenario IDs**: public scenario identifiers use the stable `NLEB-*` form
  (for example, `NLEB-ST-DE-004`). YAML records also retain
  `legacy_id: NLB-v3-*` for audit joins against pre-release run logs and
  provenance. The full mapping is in `data/scenario_id_mapping.csv`.
- **No real media files**: scenarios use abstract `EditProject` JSON fixtures with media references like `clip_1`, `audio_track_2`. No copyrighted content.
- **Symbolic-state scope**: the artifact evaluates structured `EditProject` JSON editing only; native NLE project-file import/export, rendered media, pixel/audio perception, and editor-in-the-loop workflow validation are outside this submission.
- **Canary strings**: every scenario YAML carries `NLE-BENCH-V3-{DEV|TEST}-<8hex>`; the dataset-level canary is `NLE-BENCH-V3-DATASET-7a3f9e2b`.
- **Versioning**: this is artifact release `1.0.0`; it uses v3.1 as the
  canonical scenario-corpus snapshot for this release. The v3.1 label is kept
  for corpus provenance, not as the public NLE-Bench product version. Frozen
  v3 is included for revision audit. The byte-level v3→v3.1 manifest marks all
  800 YAML files changed because every file received an anonymized
  `metadata.annotators` normalization. After removing only that metadata field,
  456 files are identical and 344 unique files contain non-metadata content
  changes, concentrated on Diagnosis/AM-Diagnosis rewrites plus targeted
  constraint, fixture, wording, and hygiene fixes. The changelog's larger
  running totals are cumulative overlapping audit-pass counts, not disjoint
  unique scenario counts. See
  `code/src/nlebench/dataset/scenarios_v3_1/CHANGELOG.md` and
  `results/scenario_v3_to_v3_1_file_manifest.csv`.
- **Model pins**: `code/scripts/model_pins.json` records API snapshots and
  open-weight HuggingFace revisions used for provenance. One gated row,
  `meta-llama/Llama-3.1-8B-Instruct`, remains documented as
  `unresolved_gated_repo_auth_failed` because anonymous artifact preparation
  could not resolve an immutable SHA without authentication; camera-ready
  release should replace it with the evaluated commit SHA or explicitly waive
  the row. Until then it is retained as unresolved provenance, not as an
  immutable-pinned checkpoint.
- **Scenario schema compatibility fields**: the v3.1 YAML schema retains
  `expected_behavior`, `required_capability`, `missing_parameters`,
  `gold_intent.expected_ops`, `gold_intent.param_ranges`, and
  `reference_solution` for compatibility with earlier authoring and future
  richer labels, but the submitted 800-scenario corpus leaves these fields
  null or empty. Feasible scoring is determined by final-state constraints;
  infeasible and ambiguous scoring uses the taxonomy class plus detector-side
  refusal/clarification behavior and an unchanged-state gate. SR-ambiguous is
  therefore a clarification-without-state-change proxy, not a metric that
  checks whether the response names the correct missing parameter.
- **Instruction-to-constraint coverage audit**: `code/scripts/audit_instruction_constraint_coverage.py`
  and `results/instruction_constraint_coverage_audit.md` provide a heuristic
  supplementary scan for feasible scenarios where instructions mention timing,
  duration, split position, or spatial position but required constraints do not
  expose an obvious corresponding field/predicate. The audit is a transparency
  tool and triage list, not a pass/fail validator and not a substitute for
  human scenario review.
- **Release policy**: this confidential review bundle includes all 800
  scenarios for audit. The public release will expose the
  200-scenario dev split with the validators, harness, and table scripts needed
  to rerun dev submissions, regenerate logs for runs a user is allowed to
  perform, and recompute dev aggregate, per-class, and factorial-cell summaries.
  The 600-scenario test split remains server-evaluated/private for leaderboard
  use. Private-test reports return only aggregate summaries (overall SR,
  per-class SR, factorial-cell summaries, and any detector-mediated calibration bands); the
  service does not return per-scenario private feedback, private
  prompts/constraints, raw private model outputs, private tool arguments,
  project states, traces, or private canary strings. Private raw logs and
  response-level refusal-audit labels remain non-released unless a future
  hash-keyed audit table is explicitly published. The release policy includes
  submission/rate limits, private canary monitoring, and rotation/versioning of
  the private set.

See `docs/datasheet.md` for the complete datasheet (Gebru et al. 2021 format).

---

## Cross-Reference to Paper

| Paper section | Supplementary file |
|---|---|
| Appendix A (Datasheet) | `docs/datasheet.md` (extended standalone) |
| Appendix B (Scenario Examples) | `code/src/nlebench/dataset/scenarios_v3_1/feasible/.../*.yaml` |
| Appendix C (Tool Specifications) | `code/src/nlebench/tools/` |
| Appendix E (Constraint Authoring Standard) | `code/src/nlebench/runner/constraints.py` (named constraint validator); `code/src/nlebench/metrics/correctness.py` (TSR aggregation helper) |
| Appendix L (v3 to v3.1 Refinement) | `code/src/nlebench/dataset/scenarios_v3_1/CHANGELOG.md` |
| Appendix M (Construction Bugs) | `code/src/nlebench/dataset/scenarios_v3_1/CHANGELOG.md` |
| Croissant metadata | `data/croissant.json` |
| Appendix I (Human Study Protocol) | `data/human_study.json`, `data/human_study_per_row_provenance.csv` |
| Scenario ID mapping | `data/scenario_id_mapping.csv` |
| Paper-analysis results | Paper tables are authoritative; `results/main_results_recomputable.csv` is the recomputable aggregate source; `code/scripts/regenerate_tables.py --table row-filter` defines the clean paper, open-track, attempted-only, and provenance-only row sets |
| Result audit/provenance | `results/per_scenario_results_redacted.csv`, `results/run_summaries_redacted.jsonl`, `results/run_manifest.csv`, `results/result_reconciliation.csv`, `results/refusal_audit_status.json`, `results/redacted_dev_trajectory_samples.jsonl` |
| Instruction/constraint audit | `code/scripts/audit_instruction_constraint_coverage.py`, `results/instruction_constraint_coverage_audit.md`, `results/instruction_constraint_coverage_flags.csv` |
| Aggregate table regeneration | `code/scripts/regenerate_tables.py`, `code/scripts/generate_review_artifacts.py` |

---

## License

- **Code** (everything under `code/`): Apache License 2.0 — see `LICENSE-APACHE-2.0`.
- **Data** (everything under `code/src/nlebench/dataset/scenarios_v3/`, `code/src/nlebench/dataset/scenarios_v3_1/`, `code/src/nlebench/dataset/fixtures/` in this confidential review bundle): CC BY 4.0 — see `LICENSE-CC-BY-4.0`. The public release policy exposes the dev split under this license while retaining the test split for server-side evaluation with aggregate-only feedback. CC BY 4.0 requires attribution while avoiding share-alike obligations for derivative scenario sets, cleaned subsets, translations, and domain-specific adaptations.
- **Metadata** (`data/croissant.json`, `docs/datasheet.md`, this README, `results/`): CC BY 4.0.

When using NLE-Bench, please:
1. Cite the paper (citation in camera-ready).
2. If you train a language model on this data, please add the canary `NLE-BENCH-V3-DATASET-7a3f9e2b` to your blocklist (see `code/src/nlebench/dataset/scenarios_v3_1/CANARY.md`).

---

## Anonymization Notes

This supplementary package has been anonymized for double-blind review:

- Author names, institutional affiliations, and internal product/company names are removed.
- Internal tracking identifiers, Slack mentions, and personal usernames are replaced with `annotator_a/b/c/d` style codes.
- Any author-affiliated application-domain system is **not** included in the harness; such systems are excluded from the evaluated targets on COI grounds (paper §5).
- Scenario YAML metadata values such as `metadata.author: v3-sprint` and
  `metadata.annotators: [author_pi]` are anonymous provenance/role labels.
  They are retained to preserve v3/v3.1 provenance hashes and are not personal
  identifiers.

The `code/src/nlebench/providers/` directory ships with four open providers (OpenAI, Anthropic, Google, vLLM). Identity-revealing internal providers, scripts, and result directories have been excluded.

---

## Reproducibility Notes

- All evaluated models trained before scenario authoring (2026-03 to 2026-04). Per-model timestamps are in `results/main_results_recomputable.csv` for reconciled rows and `results/main_results.csv` for provenance-inclusive rows; see `results/README.md` and `cd code && python scripts/regenerate_tables.py --table row-filter` for which aggregate rows are clean paper rows, direct-generation rows, attempted-only context-window failures, or provenance-only rows.
- Stochasticity: 3 seeds per open-weight model on canonical track; 1 seed per closed API call. SR is averaged when multiple seeds available.
- Hardware: open-weight models run via vLLM on a single RTX PRO 6000 96GB-class GPU per job. Closed API models accessed via official endpoints (OpenAI, Anthropic, Google).
- SR-feasible scoring is fully deterministic (TSR + CSR constraint checks);
  no LLM judge scores final edit states. The released scorer enforces
  `attribute_changed.direction` for numeric fields (`increase`, `decrease`,
  or `any`) and validates invalid directions. The direction audit finds 112
  feasible scenarios with that parameter; the patched raw-log rescore had
  final states for all prior successes, while missing-state records were
  already failures. OVR is a side-effect diagnostic only, not part of success
  scoring or paper rankings. In v3.1, 367/640 feasible scenarios (57.3%)
  include explicit `unchanged_except` preservation predicates; remaining
  feasible rows check authored target predicates rather than exhaustive state
  preservation.
- From the anonymous bundle, reviewers can run the harness/tests, validate the
  scenario corpus, inspect source hashes, and recompute aggregate/per-class/4x4
  summaries from the redacted per-scenario validation fields for reconciled
  rows. Audit-adjusted refusal substitutions are documented only as aggregate
  diagnostics, not as response-level recomputable labels.
- The active corpus validator is `cd code && PYTHONPATH=src python scripts/validate_scenarios.py`; the legacy-named `scripts/validate_scenarios_v2.py` is only a compatibility wrapper.
- Aggregate result rows can be checked and re-rendered with `cd code && python scripts/regenerate_tables.py`. The default output uses the clean canonical paper row set (`paper-clean-tool`, 52 full-800 tool-use rows) and excludes attempted-only context-window-overflow rows. Use `--row-set recomputable` to include all 57 reconciled rows, and use `--table per-class --row-set paper-main --limit 0` to recompute main-table-style per-class summaries from the redacted per-scenario fields. That per-class mode prints detector-provenance SR-infeasible; response-level refusal-audit labels are not included in the anonymous bundle.
- Redacted per-scenario result artifacts can be regenerated with `NLEBENCH_RAW_RESULTS_ROOT=/path/to/raw/results python scripts/generate_review_artifacts.py` when the raw run root is available. The included `results/run_manifest.csv` maps each aggregate row to included redacted artifacts and raw-source hashes, and `results/result_reconciliation.csv` records row-level recomputation status.
- Patched scorer rescores can be regenerated when the raw run root is
  available with
  `NLEBENCH_RAW_RESULTS_ROOT=/path/to/raw/results PYTHONPATH=src python scripts/rescore_attribute_changed_direction.py --write-results`.
  The included `results/attribute_changed_direction_rescore_audit.md`
  documents the exact state-coverage check and scorer delta.
- `validation_ovr` fields in archived redacted result rows are legacy
  provenance diagnostics. The anonymous bundle does not include the full raw
  final states needed to recompute OVR from those rows; recompute OVR only from
  reruns or raw artifacts you are authorized to access. The current validator
  treats `expected_changed_entities` as entity IDs, while retaining legacy
  category tokens such as `clips.video` for compatibility.
- `results/redacted_dev_trajectory_samples.jsonl` contains six dev-only
  representative trajectory records with source hashes, tool-call arguments,
  short reasoning-stripped response excerpts when available, and full dev
  initial/final state JSON. Outside this small dev sample, the default
  artifact does not include private/test raw prompts, private/test assistant
  responses, private/test tool arguments or states, full per-call model logs,
  or response-level refusal-audit judge labels. This avoids prompt
  fingerprinting, keeps the review artifact size bounded, and reflects that
  the audit-label table was not recoverable for review. If response-hash-keyed
  refusal labels are recovered in a future release, they should be released
  with detector label, judge A/B labels, agreement flag, and conservative final
  label; if not, the aggregate refusal audit remains diagnostic and exact
  recomputation is not claimed. Future reruns can regenerate
  response-hash-keyed labels with the same schema. Users can regenerate full
  logs by rerunning the harness on public/dev data or on private data they are
  authorized to access; private-test server feedback returns aggregate-only
  summaries.

### Reviewer Inspection Checklist

Reviewers can inspect:
- Full v3 and v3.1 scenario YAML corpora, including constraints and fixtures.
- Byte-level v3→v3.1 SHA256 manifest and the changelog count reconciliation above.
- Harness source, validators, tool executor, provider adapters, and tests.
- Aggregate results, row reconciliation, run-source hashes, and redacted per-scenario validation fields for reconciled rows.
- Six redacted dev-only trajectory samples with tool calls, state JSON, source
  hashes, and short final-answer excerpts where available.
- Human-study records, anonymized rater provenance, Datasheet, Croissant metadata, and licenses.

Reviewers cannot inspect from this anonymous bundle:
- Full raw trajectories beyond the small dev sample, raw private/test prompts,
  private/test assistant responses, complete private/test tool arguments, or
  private/test state JSON.
- Response-level refusal-audit judge labels; only aggregate audit status is included, so exact refusal-audit recomputation is not claimed from this bundle.
- Outside-organization released-corpus validation, which has not yet been run.
- Exact API invoice provenance; only estimated per-run costs are documented in the paper.

---

## Contact

For reviewer questions, please use the OpenReview comment thread on this paper. Code and dev-split data will be made publicly available with author identification at the camera-ready stage; test evaluation will remain server-side.
