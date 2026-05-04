# NLE-Bench Scenarios v3.1

> **Status:** Canonical review corpus (2026-04-18 release snapshot)
> **Size:** 800 scenarios total (640 feasible + 160 calibration)
> **Split:** dev:test = 1:3 (per-cell n=40 → 10 dev / 30 test)

## Directory structure

```
scenarios_v3_1/
├── feasible/
│   ├── explicit/
│   │   ├── atomic/{dev,test}/       ← 10 dev + 30 test = 40 per cell
│   │   ├── compound/{dev,test}/
│   │   ├── dependent/{dev,test}/
│   │   └── cumulative/{dev,test}/
│   ├── state/
│   │   └── {atomic,compound,dependent,cumulative}/{dev,test}/
│   ├── context/
│   │   └── {atomic,compound,dependent,cumulative}/{dev,test}/
│   └── diagnosis/
│       └── {atomic,compound,dependent,cumulative}/{dev,test}/
├── infeasible/
│   └── {explicit,state,context,diagnosis}/{dev,test}/   ← 5 dev + 15 test = 20 per cell
└── ambiguous/
    └── {explicit,state,context,diagnosis}/{dev,test}/   ← 5 dev + 15 test = 20 per cell
```

- **Feasible**: 16 cells × 40 = **640 scenarios**
- **Infeasible**: 4 info types × 20 = **80 scenarios**
- **Ambiguous**: 4 info types × 20 = **80 scenarios**
- **Total**: **800 scenarios** (200 dev, 600 test)

## Taxonomy

Each scenario falls under the 2D cognitive demand grid:

- **Information Gap axis**: explicit / state / context / diagnosis
  - Where does the agent need to fetch missing info from?
- **Action Structure axis**: atomic / compound / dependent / cumulative
  - How do the required actions relate to each other?
- **Feasibility axis**: feasible / infeasible / ambiguous
  - Is the request achievable with the available tools?

The paper methods section and appendix define the axes and rationale used for
this release.

## Schema compatibility fields

The YAML schema retains `expected_behavior`, `required_capability`,
`missing_parameters`, `gold_intent.expected_ops`, `gold_intent.param_ranges`,
and `reference_solution` for compatibility with older authoring tools and
future richer labels. In this v3.1 corpus, all 800 scenarios leave these fields
null or empty. The active scoring contract is instead:

- feasible scenarios: final-state constraints and structural validity;
- infeasible scenarios: infeasible taxonomy class plus refusal detector and
  unchanged-state gate;
- ambiguous scenarios: ambiguous taxonomy class plus clarification detector and
  unchanged-state gate.

Accordingly, SR-ambiguous in the paper is a state-preserving clarification
proxy, not a correct-missing-parameter metric.

## Split policy

- **dev**: 200 scenarios (25%). Intended for public development access.
- **test**: 600 scenarios (75%). Included in the confidential review bundle
  for audit, but intended to remain server-evaluated/private in the public
  leaderboard release to limit contamination and overfitting. Reported
  benchmark numbers should come from server-side test evaluation.

## Canary strings

Each scenario carries a `canary` field of the form:

```
NLE-BENCH-V3-{SPLIT}-{8hex}
```

The dataset also has a top-level canary string (see `CANARY.md`) for
dataset-level contamination detection. If a language model is found to
generate any canary string verbatim, it is evidence that the model
was trained on NLE-Bench content.

## Relation to earlier corpora

- `scenarios_v1/` and `scenarios_v2/`: earlier authoring corpora used during
  benchmark development. They are not shipped in this anonymous review bundle.
- `scenarios_v3/`: frozen pre-refinement v3 corpus, included as a sibling
  directory for auditability of the v3→v3.1 revision.
- `scenarios_v3_1/` (this directory): canonical review corpus using the
  2D cognitive demand grid (Information × Action × Feasibility).

The v3→v3.1 refinement revised scenario wording and selected constraints based
on pilot/human-study feedback. The release includes file hashes comparing v3 and
v3.1 in `../../../../../results/scenario_v3_to_v3_1_file_manifest.csv`.
The v3.1 corpus has infrastructure validation and redacted evaluation artifacts;
it has not yet undergone a separate model-blind external re-rating pass.
