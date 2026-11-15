# NLE-Bench review snapshot (dev split)

> **Status.** This repository holds the retained files of the NLE-Bench review
> snapshot, with test-split scenario files and test-split item-level records
> omitted. It is not maintained and is not a release of the benchmark.

NLE-Bench evaluates tool-use agents on symbolic non-linear video editing. Each
scenario provides a natural-language instruction, an initial `EditProject` state
(JSON), a constraint set (YAML) that a deterministic scorer checks against the
agent's final state, and taxonomy labels. The complete corpus has 800 scenarios:
a 4 (perception) x 4 (execution) factorial of 640 feasible scenarios plus 80
infeasible and 80 ambiguous calibration scenarios, split 200 dev and 600 test.
This repository holds the 200 of the dev split.

The paper "Red-Teaming the Grader: Mutation-Validated Constraint Checking for
Tool-Agent Benchmarks" (NeurIPS 2026 Workshop: Who Verifies the Agents?) uses
this snapshot's harness, corpus and per-record verdicts and cites this
repository at its first commit. The snapshot's modules that its replay commands
load are held in the audit repository, https://github.com/Junha-Jang/nle-bench-audit.

---

## What is omitted

The files are reduced to the dev split, removing every row or record of a
test-split scenario:

- `results/per_scenario_results_redacted.csv`: 89,400 rows removed, 29,800 kept
- `results/scenario_v3_to_v3_1_file_manifest.csv`: 600 rows removed, 200 kept
- `data/scenario_id_mapping.csv`: 600 rows removed, 200 kept
- `data/human_study_per_row_provenance.csv`: 350 rows removed, 736 kept
- `data/human_study.json`: 500 records removed, 1,296 kept
- `code/scripts/human_study_samples.json`: 116 records removed

Six files are not included at all, because they describe test-split scenarios
one by one: `code/src/nlebench/dataset/scenarios_v3_1/CHANGELOG.md`,
`results/attribute_changed_direction_audit.json`,
`results/attribute_changed_direction_audit.md`,
`results/attribute_changed_direction_flags.csv`,
`results/instruction_constraint_coverage_audit.md` and
`results/instruction_constraint_coverage_flags.csv`. The coverage command under
"Quick start" writes the last two for the scenarios present.

Retained aggregate results also describe the complete dataset; they are not
dev-only recomputations and cannot be fully recounted from the retained
item-level records. The code and its tests expect the complete files; without
the test split some of them do not run.

Counts in the documents under `code/`, `data/` and `results/`, such as 800
scenarios, describe the complete files. In those documents, "the paper" means
the benchmark's own write-up of these experiments, not the paper named above.

## What else differs from the snapshot

- This README replaces the snapshot's README, datasheet, Croissant metadata and
  its validation report, which are not included.
- In the other documents under `code/`, `data/` and `results/`, in two JSON
  notes (`results/refusal_audit_status.json`, `code/scripts/model_pins.json`) and
  in one label of `code/Dockerfile`, sentences about how the snapshot was
  packaged are reworded to describe this repository.
- Changed: `CITATION.cff`, the `authors` field of `code/pyproject.toml`, and the
  licence files, which are now `LICENSE` and `LICENSE.md`.

The programs (`.py` files), the scenario files and the fixtures are unchanged;
comments and printed messages in the programs keep the snapshot's wording.

## Notes on how the corpus was written

The scenarios were drafted with commercial LLM assistance for instruction text
and constraint templates. The author reports skimming the scenarios and
conducting the human studies whose records are in `data/`. Those studies keep
their documented samples, tasks and limitations; they do not establish human
review, editing or validation of every scenario, constraint or stored reference
trajectory. Labels in the scenario metadata, such as "hand-crafted seed",
"author_pi" and "annotators", are retained historical fields, not evidence of
per-scenario human authorship or review; the human-study rater records are not
affected.

---

## Contents

```
.
├── README.md                  ← this file
├── CITATION.cff               ← citation metadata
├── LICENSE                    ← licence (CC BY-NC 4.0 legal code)
├── LICENSE.md                 ← holder, attribution, added permission
├── code/                      ← harness
│   ├── src/nlebench/          ← core package (tools, runner, metrics, providers)
│   │   └── dataset/
│   │       ├── scenarios_v3/         ← frozen v3 corpus (dev split)
│   │       ├── scenarios_v3_1/       ← canonical v3.1 corpus (dev split)
│   │       └── fixtures/             ← base project states
│   ├── scripts/               ← analysis utilities
│   ├── tests/                 ← test suite
│   ├── README.md
│   ├── pyproject.toml
│   ├── Dockerfile
│   └── docker-compose.yml
├── data/
│   ├── human_study.json       ← rater records (dev split)
│   ├── human_study_per_row_provenance.csv
│   ├── human_study_README.md  ← schema and reproduction guide
│   └── scenario_id_mapping.csv
└── results/
    ├── README.md
    ├── main_results_recomputable.csv
    ├── main_results.csv
    ├── excluded_nonrecomputable_rows.csv
    ├── per_scenario_results_redacted.csv
    ├── redacted_dev_trajectory_samples.jsonl
    ├── redacted_dev_trajectory_samples_README.md
    ├── result_reconciliation.csv
    ├── refusal_audit_status.json
    ├── run_manifest.csv
    ├── run_summaries_redacted.jsonl
    ├── scenario_v3_to_v3_1_file_manifest.csv
    ├── attribute_changed_direction_rescore_audit.json
    └── attribute_changed_direction_rescore_audit.md
```

---

## Quick start

### Run a model

```bash
cd code
pip install -e .
python -m nlebench --provider openai --model gpt-5.4 \
  --reasoning-effort medium --track canonical
```

The harness writes results to `results/<timestamp>_<model>/summary.json` and
per-scenario logs to `results/<timestamp>_<model>/calls/`. Default model names
in the CLI and helper script are `gpt-5.4`, `claude-sonnet-4-6-2026-02-17`,
`gemini-3-flash-preview` and `Qwen/Qwen3-32B`. For OpenAI GPT-5.x rows,
`--reasoning-effort medium` matches the Responses API setting the results used.

### Validate the scenario corpus

```bash
cd code
PYTHONPATH=src python scripts/validate_scenarios.py
```

`scripts/validate_scenarios_v2.py` is a compatibility wrapper that calls the
same v3.1 validator. The validator also checks the 800/200/600 split counts of
the complete corpus; on this repository it reports five errors, all about these
counts.

### Audit instruction-to-constraint coverage

```bash
cd code
PYTHONPATH=src python scripts/audit_instruction_constraint_coverage.py \
  --markdown-out ../results/instruction_constraint_coverage_audit.md \
  --csv-out ../results/instruction_constraint_coverage_flags.csv
```

This heuristic scan looks at feasible-scenario instructions for surface numeric
timing, duration, split-position and spatial-position cues, then checks whether
required constraints mention obvious matching fields or named predicates. Its
flags are candidates for inspection, not validator failures, and it does not
prove that a scenario is correct or incorrect.

### Run the test suite

```bash
cd code
pip install -e .
pip install pytest pytest-asyncio
PYTHONPATH=src pytest tests/
```

Use `PYTHONPATH=src`, or run after `pip install -e .` in a clean environment, so
that pytest imports this package rather than another local `nlebench` checkout.

### Regenerate row filters and tables

```bash
cd code
python scripts/regenerate_tables.py --table row-filter
python scripts/regenerate_tables.py --table per-class --row-set paper-main --limit 0
python scripts/regenerate_tables.py --table error-types --row-set recomputable
```

The first command labels aggregate rows as clean tool-use rows,
direct-generation rows, attempted-only context-window failures or
provenance-only rows. The second recomputes per-class summaries from the
redacted per-scenario fields; SR-infeasible there is detector provenance,
because response-level refusal-audit labels are not included. The third
summarizes the redacted `error_message_type` field into coarse provider and
runtime categories; it is not a validated taxonomy of task misunderstanding,
malformed tool calls or truncation.

---

## About the corpus and the scoring

- **Scenario IDs**: scenario identifiers use the `NLEB-*` form (for example,
  `NLEB-ST-DE-004`). YAML records also keep `legacy_id: NLB-v3-*` for joins
  with earlier run logs. The mapping is in `data/scenario_id_mapping.csv`.
- **No real media files**: scenarios use abstract `EditProject` JSON fixtures
  with media references such as `clip_1` and `audio_track_2`.
- **Symbolic-state scope**: the benchmark evaluates structured `EditProject`
  JSON editing only; native project-file import and export, rendered media,
  pixel and audio perception, and editor-in-the-loop validation are outside its
  scope.
- **Canary strings**: every scenario YAML carries `NLE-BENCH-V3-{DEV|TEST}-<8hex>`;
  the dataset-level canary is `NLE-BENCH-V3-DATASET-7a3f9e2b`.
- **Versioning**: v3.1 is the canonical scenario corpus and a corpus provenance
  label, not a release number of the benchmark. The frozen v3 corpus is kept for
  the audit of the v3 to v3.1 revision; `results/README.md` describes the
  file-level manifest between them.
- **Model pins**: `code/scripts/model_pins.json` records API snapshots and
  open-weight Hugging Face revisions. One gated row,
  `meta-llama/Llama-3.1-8B-Instruct`, is recorded as
  `unresolved_gated_repo_auth_failed`: its immutable revision could not be
  resolved without authentication, so it is unresolved provenance, not a pinned
  checkpoint.
- **Schema compatibility fields**: several legacy YAML fields are null or empty
  in all scenarios; feasible scoring is decided by final-state constraints, and
  SR-ambiguous is a clarification-without-state-change proxy (`code/README.md`).
- **Deterministic scoring**: no LLM judge scores final edit states. The scorer
  enforces `attribute_changed.direction` for numeric fields (`increase`,
  `decrease` or `any`) and rejects invalid directions. OVR is a side-effect
  diagnostic, not part of success scoring.
- **Runs**: open-weight models used 3 seeds on the canonical track and closed
  API models 1; SR is averaged where several seeds exist. Open-weight models ran
  through vLLM on a single 96 GB-class GPU per job; closed models through their
  official endpoints.

## What you can and cannot check here

They hold:
- the dev-split v3 and v3.1 scenario YAML files, with constraints and fixtures,
  and the dev rows of the byte-level v3 to v3.1 manifest;
- the harness source, validators, tool executor, provider adapters and tests;
- aggregate results, row reconciliation, run-source hashes, and redacted
  per-scenario validation fields for the dev rows of reconciled runs;
- six redacted dev-split trajectory samples with tool calls, state JSON, source
  hashes and short final-answer excerpts where available;
- the dev-split human-study records and their per-row provenance.

They do not hold:
- test-split scenarios or test-split item-level records;
- full raw trajectories beyond the six samples, raw prompts, raw responses,
  complete tool arguments or complete state JSON;
- response-level refusal-audit judge labels; only the aggregate audit status is
  included, so exact refusal-audit recomputation is not claimed;
- validation of the corpus by an outside organisation, which has not been run;
- API invoices; only estimated per-run costs exist.

---

## Licence

Copyright 2026 Someple Inc. Every file in this repository, program source
included, is licensed under Creative Commons Attribution-NonCommercial 4.0
International (CC BY-NC 4.0), except the material that `LICENSE.md` lists as
not covered; the legal code is in `LICENSE`. `LICENSE.md` says how to
attribute and gives an additional permission for anyone, including for-profit
organisations, to reproduce or check the results reported in the paper
"Red-Teaming the Grader". For other uses, including commercial use, contact
Someple Inc. at junha.jang@someple.com; any further permission requires a
separate written agreement.

Two requests, not conditions of the licence:
1. Cite this repository (see `CITATION.cff`).
2. If you train a language model on this data, add the canary
   `NLE-BENCH-V3-DATASET-7a3f9e2b` to your blocklist (see
   `code/src/nlebench/dataset/scenarios_v3_1/CANARY.md`).

---

## Contact

This repository is not maintained. To report an error that concerns the paper
"Red-Teaming the Grader: Mutation-Validated Constraint Checking for Tool-Agent
Benchmarks" (NeurIPS 2026 Workshop: Who Verifies the Agents?), open an issue in
the audit repository, https://github.com/Junha-Jang/nle-bench-audit. For uses
beyond the licence, see `LICENSE.md`.
