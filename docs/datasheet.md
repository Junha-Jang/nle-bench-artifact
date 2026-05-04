# Datasheet for NLE-Bench

This datasheet follows the format of Gebru et al. (2021), "Datasheets for Datasets."
It accompanies **NLE-Bench: Feasibility-Aware Tool Use in Symbolic Non-Linear Video Editing**.

A condensed version of this datasheet appears in Appendix A of the main paper. This standalone document expands all sections for reviewer convenience.

---

## Motivation

**For what purpose was the dataset created?**
NLE-Bench was created to fill a gap in automated evaluation of AI agents that perform timeline editing in non-linear editing (NLE) software. Prior agent benchmarks evaluate code generation, web navigation, or general tool use, but no benchmark evaluates editing **execution** — the multi-step manipulation of a structured timeline state — with deterministic constraint-based metrics. NLE-Bench provides 800 scenarios across a 4×4 cognitive demand factorial × 3-way feasibility split, scored by checking constraints on the resulting `EditProject` state rather than via an LLM judge.

**Who created the dataset and on behalf of which entity?**
The dataset was created by the paper authors (identity withheld for double-blind review).

**What support was needed to make the dataset?**
Self-funded; no external funding sources. LLM API costs for scenario drafting, and compute for running the human study harness, were covered internally.

---

## Composition

**What do the instances that comprise the dataset represent?**
Each instance is a **scenario** comprising:
- Natural-language instruction (English)
- Initial `EditProject` state (JSON; tracks, clips, media references, transitions)
- Constraint set (YAML; `required` constraints that must hold post-execution; optional `validity` constraints; optional `refusal`/`clarification` constraints for non-feasible scenarios)
- Taxonomy labels (perception × execution × feasibility)
- Fixture identifier (one of 5 deterministic initial-state templates)
- Per-scenario canary string (for contamination detection)

**How many instances are there in total?**
**800 scenarios** (200 dev split + 600 test split).

| Subset | Count | Structure |
|---|---|---|
| Feasible | 640 | 4 perception × 4 execution × 40 = balanced factorial |
| Infeasible | 80 | 20 per perception level; infeasible by taxonomy and no-change/refusal scoring |
| Ambiguous | 80 | 20 per perception level; ambiguous by taxonomy, vague or underspecified intent |

**Does the dataset contain all possible instances or is it a sample?**
NLE-Bench is a curated benchmark sample; the universe of possible NLE editing scenarios is unbounded. The 4×4 factorial design ensures coverage of qualitatively different cognitive demands (Information Gap × Action Structure axes).

**What data does each instance consist of?**
See "What do the instances..." above. All scenario data is text/structured (YAML, JSON) — **no real media files, no video, no audio, no copyrighted content**. Fixtures reference media via abstract IDs (e.g., `clip_1`, `audio_track_2`).

**Is there a label or target associated with each instance?**
Yes: each scenario has constraint sets that define success/failure deterministically. For non-feasible scenarios, the intended behavior is refusal or clarification, but the submitted v3.1 YAMLs encode this through the taxonomy class and detector-side behavior rather than populated `expected_behavior`, `required_capability`, or `missing_parameters` fields.
For feasible scenarios, paper success uses TSR + CSR only. OVR is a diagnostic
side-effect signal and is not part of success scoring; 367/640 feasible v3.1
scenarios (57.3%) include explicit `unchanged_except` preservation predicates.
The current validator treats `expected_changed_entities` as entity IDs while
retaining legacy category tokens for compatibility.

**Is any information missing from individual instances?**
All scenarios are validated by the active v3.1 validator for YAML loading,
package schema checks, path/taxonomy consistency, ID mapping, fixtures, and
corpus counts. The schema intentionally retains unpopulated compatibility
slots: `expected_behavior`, `required_capability`, `missing_parameters`,
`gold_intent.expected_ops`, `gold_intent.param_ranges`, and
`reference_solution` are null or empty across all 800 submitted scenarios.
They should not be interpreted as missing released labels; SR-ambiguous is a
clarification-without-state-change proxy, not a correct-missing-parameter
metric.
A separate heuristic audit script,
`code/scripts/audit_instruction_constraint_coverage.py`, scans feasible
instructions for timing, duration, split-position, and spatial-position cues
whose required constraints do not expose obvious matching fields or named
predicates. Its report is a transparency and triage artifact, not a validator
failure list or proof of scenario invalidity.
The active scorer also enforces `attribute_changed.direction` for numeric
fields. The direction audit enumerates 112 feasible scenarios using that
parameter, and the coverage audit still flags 173 feasible scenarios as
human-review candidates for possible instruction-to-predicate gaps.

**Are relationships between individual instances made explicit?**
Scenarios share fixtures (5 deterministic templates), and the 16-cell factorial design creates implicit comparison axes (e.g., all DI-AT scenarios are mutually comparable on perception complexity within atomic execution).

**Are there recommended data splits?**
Yes. **dev (200) / test (600)** at a 1:3 ratio per cell:
- Feasible cells: 10 dev / 30 test per cell
- Calibration cells (Infeasible/Ambiguous): 5 dev / 15 test per cell

The dev split is for harness/prompt development; the test split is the canonical evaluation set.
This confidential review bundle includes both splits so reviewers can audit the
paper's claims. The public release will expose the dev split and evaluate
the test split server-side.

**Are there any errors, sources of noise, or redundancies?**
The pre-release → release refinement pass (App. L of paper) addressed identified issues:
- Pilot human study revealed Diagnosis cell instruction-template ambiguity (rated κ = -0.03 vs. κ = 0.37 for unchanged scenarios).
- 344 unique scenario YAMLs (43%) contain non-metadata content changes after excluding the global `metadata.annotators` anonymization; 160 Diagnosis + 20 AM-Diagnosis cells were fully rewritten, while the remaining changes are targeted constraint, fixture, wording, and hygiene fixes.
- The byte-level v3→v3.1 manifest marks all 800 YAMLs as changed because every file received that metadata normalization. Changelog totals such as `~337`, `~378`, `~411`, and `~428` are cumulative overlapping audit-pass counts, not disjoint unique scenario counts.
- Internal follow-up checks suggest the Diagnosis-cell revision moved realism in
  the intended direction, but v3.1 has not yet received a model-blind external
  re-rating pass.

**Is the dataset self-contained, or does it link to or otherwise rely on external resources?**
Self-contained. No external URLs, no media files, no external APIs required for scoring.

**Does the dataset contain data that might be considered confidential?**
The public dev split is non-confidential synthetic data. The 600-scenario test
split is included in the anonymous review bundle for confidential review and
will remain server-evaluated/private in the public leaderboard release.
Scenario metadata role labels such as `v3-sprint` and `author_pi` are anonymous
provenance labels retained to preserve v3/v3.1 corpus hashes; they are not
personal identifiers.

**Does the dataset contain data that, if viewed directly, might be offensive, insulting, threatening, or might otherwise cause anxiety?**
No.

---

## Collection Process

**How was the data associated with each instance acquired?**
Scenarios were authored by the anonymous paper authors with commercial LLM assistance for drafting instruction text and constraint templates. All LLM outputs were manually reviewed, edited, and checked. The authoring process was informed by:
- Semi-structured interviews with three non-author professional video editors from a single convenience pool (30–60 min each, focused on common editing requests and pain points)
- Analysis of 200+ editing-forum posts (coded by operation category)
- L1 pilot feedback from three non-author professional video editors from the same convenience pool (N = 200 scenarios, three raters), followed by internally adjudicated v3.1 revisions

**What mechanisms or procedures were used to collect the data?**
Manual scenario authoring through text editor + LLM draft assistance. Scenarios stored as structured YAML files. A custom validation harness (linter) checks each scenario against a JSON Schema on every commit.

**If the dataset is a sample from a larger set, what was the sampling strategy?**
The 4×4 factorial × 3-way feasibility split was designed a priori from interviews and forum coding, not sampled.

**Who was involved in the data collection process?**
- Scenario authoring: anonymous paper authors (with LLM assistance)
- Three non-author professional video editors from a single convenience pool: domain consultation interviews and L1 scenario validation study (compensated, see paper App. I/J)
- Three non-author mixed-expertise raters from the same coordinated annotator pool: L2 human–metric correlation + L3 mixed-expertise decision reference (compensated, see paper App. I/J)

**Over what timeframe was the data collected?**
2026-03 (initial scenario authoring) to 2026-04 (v3.1 release).

**Were any ethical review processes conducted?**
The annotation studies involved human subjects rating AI outputs. The authors followed NeurIPS' "informal-equivalent review" pathway for ethics review (Code of Ethics permits this when no formal IRB is available). All annotators provided written informed consent and could withdraw without consequence. Compensation details are reported in paper App. I (Human Study Protocol) and App. J (Ethics): L1 non-author professional video editors received KRW 20,000 each for the 200-item scenario-review task, while L2/L3 non-author raters received KRW 70,000 each for the combined 80-item L2 and 80-item L3 task bundle. These are closed-pool diagnostics rather than independent external validation.

---

## Preprocessing / Cleaning / Labeling

**Was any preprocessing/cleaning/labeling of the data done?**
- Constraint linting: every scenario passes schema validation and fixture compatibility checks.
- Instruction-to-constraint coverage audit:
  `results/instruction_constraint_coverage_audit.md` reports heuristic
  candidates where surface timing/duration/position language may not be covered
  by required predicates. Flags require human review and are not part of
  benchmark scoring.
- v3 → v3.1 refinement: 344 unique scenario YAMLs contain non-metadata content changes after excluding global annotator-metadata normalization (160 DI + 20 AM-DI cell-wide rewrites; remaining targeted constraint/fixture/wording/hygiene edits).

**Was the "raw" data saved in addition to the preprocessed data?**
v3 (pre-refinement) is preserved alongside v3.1 in the repository for reproducibility.

**Is the software that was used available?**
Yes. The active scenario validator, constraint linter, scoring harness, and analysis scripts are released under Apache 2.0 (see `code/`). Obsolete v1/v2 authoring generators are not part of this review artifact.

---

## Uses

**Has the dataset been used for any tasks already?**
Yes — the main paper's clean analysis uses 52 full-800 model/configuration rows
on the v3.1 scenario-corpus snapshot. Supplementary result files also retain broader recomputable
and provenance-only row sets for audit; those rows are not the default clean
paper-analysis set.

**Is there a repository that links to any or all papers or systems that use the dataset?**
A leaderboard will be hosted at the project repository (URL in camera-ready).

**What (other) tasks could the dataset be used for?**
- Tool-use agent research (calibration, refusal, clarification)
- Difficulty taxonomy studies (effects of perception × execution complexity)
- Agent-framework comparison (single-LLM vs. ReAct vs. planner-executor)
- Direct-generation baselines for structured-state editing

**Is there anything about the composition of the dataset or the way it was collected and preprocessed/cleaned/labeled that might impact future uses?**
- **Text-only scope**: NLE-Bench does not contain pixel data or audio waveforms. Scenarios that would require video/audio analysis are deliberately assigned to the infeasible taxonomy class when the tool/state interface cannot support them; the legacy `required_capability` slot is not populated in v3.1. This benchmark cannot evaluate VLM/audio-LM perception capabilities.
- **Symbolic-state scope**: NLE-Bench evaluates edits to an abstract `EditProject` JSON state. It does not validate native project-file import/export, media rendering, pixel/audio perception, or editor-in-the-loop workflows.
- **English-only**: All instructions are in English. Multilingual extension is left for future work.
- **Synthetic fixtures**: The four direct base fixtures used by the scenario corpus (`simple_sequence`, `complex_sequence`, `multi_sequence`, `with_transitions`) and their YAML-level patched variants are abstract; real-world editing project files are more complex. Additional support fixtures may be present for tests or harness checks but are not the main corpus substrate.

**Are there tasks for which the dataset should not be used?**
- Video understanding / VLM benchmarking (the text-only scope makes this category-incorrect)
- Training data for production NLE products (see contamination/canary policy below)

---

## Distribution

**Will the dataset be distributed to third parties outside of the entity on behalf of which the dataset was created?**
Yes. A public dev split and harness will be released post-publication, with
private test evaluation served through the leaderboard.

**How will the dataset be distributed?**
The confidential review bundle contains all 800 scenarios. The public release
will expose the 200-scenario `dev` split under CC BY 4.0 together with the
Apache-licensed harness, and will keep the 600-scenario `test` split
server-evaluated/private for leaderboard submissions. Release channels:
- GitHub repository (source, harness, and dev split, post-publication)
- Public dataset hub (dev split, post-publication, programmatic access)
- Zenodo DOI (archival dev-split snapshot and metadata)

Per-scenario canary strings (`NLE-BENCH-V3-{DEV|TEST}-<8hex>`) and a
dataset-level canary (`NLE-BENCH-V3-DATASET-7a3f9e2b`) enable contamination
detection in future LLM evaluations. The leaderboard is hosted on the project
website with server-side test evaluation; public reports should distinguish dev
scores from server-side test scores. Public/dev users can run the validators
and harness on the dev split, generate
logs for runs they are allowed to perform, and recompute dev aggregate,
per-class, and factorial-cell summaries with the supplied scripts. Private-test
reports return only aggregate summaries (overall SR, per-class SR,
factorial-cell summaries, and any detector-mediated calibration bands); they do not return
per-scenario private outcomes, prompts, expected constraints, raw model outputs,
tool arguments, project states, traces, or private canary strings. Private raw
logs and response-level refusal-audit labels remain non-released unless a
future hash-keyed audit table is explicitly published. Submission/rate limits,
private canary monitoring, and private-set rotation/versioning are part of the
release policy.

**When will the dataset be distributed?**
- Submission supplementary (full data, anonymized): 2026-05-04
- Public release (harness + dev split + author identification): post-publication (camera-ready stage)

**Will the dataset be distributed under a copyright or other intellectual property (IP) license, and/or under applicable terms of use (ToU)?**
- **Data**: CC BY 4.0. The license requires attribution while avoiding share-alike obligations for derivative scenario sets, cleaned subsets, translations, and domain-specific adaptations.
- **Code (harness)**: Apache 2.0
- License files included in the supplementary `LICENSE-CC-BY-4.0` and `LICENSE-APACHE-2.0`.

**Have any third parties imposed IP-based or other restrictions on the data associated with the instances?**
No.

**Do any export controls or other regulatory restrictions apply to the dataset or to individual instances?**
No.

---

## Maintenance

**Who will be supporting/hosting/maintaining the dataset?**
The paper authors (identity withheld for double-blind review).

**How can the owner/curator/manager of the dataset be contacted?**
Contact details in paper camera-ready.

**Is there an erratum?**
None at submission. Errata will be tracked via GitHub issues post-publication.

**Will the dataset be updated?**
Yes. Versioning policy:
- Scenario-corpus snapshot bump (e.g., v3.1 → v3.2) when constraint logic changes.
- A future major NLE-Bench release may add new v2 scenario families when the top-3 average SR exceeds 90% (capability-driven refresh).
- Annual review cycle to retire saturated cells.

**If the dataset relates to people, are there applicable limits on the retention of the data?**
The dataset does not contain personal data. Annotator identities are pseudonymized via codenames.

**Will older versions of the dataset continue to be supported/hosted/maintained?**
The confidential review bundle preserves v3 alongside v3.1 for audit. Public
versioning will preserve released dev splits and metadata; private test
snapshots will remain server-side.

**If others want to extend/augment/build on/contribute to the dataset, is there a mechanism for them to do so?**
Yes. Contribution guidelines and pull-request process via the project repository (post-publication).

---

## Contamination Defense

NLE-Bench includes three contamination defenses:

1. **Per-scenario canary strings**: Each scenario YAML contains a deterministic canary of the form `NLE-BENCH-V3-{DEV|TEST}-<8hex>` derived from `sha256('NLE-BENCH-V3::<id>::<split>')`. A dataset-level canary `NLE-BENCH-V3-DATASET-7a3f9e2b` appears in the README and license metadata.

2. **Held-out private test split**: 600 of 800 scenarios are designated `test`; only the 200 `dev` split is public development access. Production leaderboard evaluation uses server-side test scoring.

3. **Aggregate-only private reporting**: Private leaderboard responses return aggregate summaries only (overall SR, per-class SR, factorial-cell summaries, and any detector-mediated calibration bands), not private per-scenario scores, private prompts/constraints, raw private outputs, tool arguments, project states, traces, or private canary strings. Repeated submissions are controlled through submission/rate limits, canary monitoring, and private-set rotation/versioning if leakage is suspected.

4. **Temporal cutoff**: All scenarios authored 2026-03 to 2026-04, post-dating the training cutoff of all evaluated models.

To test whether a model was trained on NLE-Bench:
```python
prompt = "Complete this benchmark identifier: NLE-BENCH-V3-DATASET-"
# If completion contains "7a3f9e2b", the model was likely trained on NLE-Bench content.
```

Researchers operating dataset crawls or LLM training pipelines are asked to add `NLE-BENCH-V3-DATASET-7a3f9e2b` to their blocklists.

**What can reviewers inspect directly in the anonymous bundle?**
They can inspect both v3 and v3.1 scenario trees, the byte-level SHA256
manifest, the changelog count reconciliation, harness source/tests,
constraints, aggregate results, redacted per-scenario validation fields for
reconciled rows, source hashes, human-study records, anonymized rater
provenance, Datasheet, Croissant metadata, and licenses.

**What is intentionally deferred or redacted?**
Raw prompts, assistant responses, complete tool arguments, full state JSON, raw
trajectories, and response-level refusal-audit judge labels are not included in
the anonymous bundle. Outside-organization released-corpus validation has not
yet been run, and exact API invoice provenance was not logged. Archived
redacted `validation_ovr` values are provenance/legacy diagnostics and are not
independently recomputable without the raw final states. If response-hash-keyed
refusal labels are recovered for camera-ready, they should
be released with detector label, judge A/B labels, agreement flag, and
conservative final label. If they cannot be recovered, the aggregate refusal
audit remains diagnostic and exact recomputation is not claimed; future reruns
can regenerate labels under the same response-hash-keyed schema. Public
trajectory material is limited to redacted samples or logs regenerated from
public/dev runs, not raw private prompts, complete private states, or full
private tool traces.

---

## File Layout (in supplementary)

```
supplementary/
├── README.md                           # Top-level overview
├── LICENSE-APACHE-2.0                  # Code license
├── LICENSE-CC-BY-4.0                   # Data license
├── code/                               # Harness (Apache 2.0)
│   ├── src/nlebench/                   # Core package
│   │   ├── tools/, runner/, metrics/, providers/, analysis/
│   │   └── dataset/
│   │       ├── scenarios_v3/           # frozen pre-refinement v3 corpus
│   │       ├── scenarios_v3_1/         # 800 scenario YAMLs (canonical location)
│   │       │   ├── feasible/{4 perception}/{4 execution}/{dev,test}/
│   │       │   ├── infeasible/{4 perception}/{dev,test}/
│   │       │   ├── ambiguous/{4 perception}/{dev,test}/
│   │       │   ├── README.md, CHANGELOG.md, CANARY.md
│   │       └── fixtures/               # 5 initial-state templates
│   ├── scripts/                        # Selected analysis utilities
│   ├── tests/                          # Test suite
│   └── pyproject.toml, Dockerfile, docker-compose.yml
├── data/                               # Metadata + human study records
│   ├── croissant.json                  # Croissant 1.0 metadata
│   ├── human_study.json                # 1,796 anonymized rater records
│   ├── human_study_per_row_provenance.csv
│   └── human_study_README.md           # Schema + reproduction guide
├── results/
│   ├── main_results.csv                # Aggregated SR; includes paper-analysis and provenance-only rows
│   ├── run_manifest.csv                # aggregate-to-artifact/source hash manifest
│   ├── run_summaries_redacted.jsonl
│   ├── per_scenario_results_redacted.csv
│   ├── scenario_v3_to_v3_1_file_manifest.csv
│   └── README.md
└── docs/
    └── datasheet.md                    # this file
```
