# NLE-Bench Scenarios v3

> **Status:** Frozen pre-refinement corpus preserved for review audit
> **Size:** 800 scenarios total (640 feasible + 160 calibration)
> **Split:** dev:test = 1:3 (per-cell n=40 → 10 dev / 30 test)

## Directory structure

```
scenarios_v3/
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
this corpus.

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

## Relation to v3.1

- `scenarios_v3/` (this directory): frozen pre-refinement corpus.
- `scenarios_v3_1/`: canonical review corpus using the same 2D cognitive
  demand grid (Information × Action × Feasibility), with targeted wording and
  constraint fixes.

The review artifact includes both v3 and v3.1 so reviewers can audit the
revision at the file-hash level.
