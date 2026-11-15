"""
Paper-ready post-run analysis for NLE-Bench v3 runs.

Beyond what ClearML shows, this script produces:
  1. Overall SR with a 95% Wilson confidence interval
  2. Per-axis SR (feasibility, scale, information, action) with CIs
  3. Full 4x4 Information × Action cell table + CI widths
  4. Behavioral Profile Matrix (feasibility × behavior) raw counts
  5. Tool protocol compliance (unknown-tool rate, top offenders)
  6. Failure classification on the feasible subset, partitioning each
     wrong-behavior run into one of:
        TOOL_add_effect_for_transform   — wrong tool family
        AGENT_no_edits                  — query-only, never acted
        AGENT_wrong_target              — edited unrelated entities
        AGENT_partial_target            — missed some expected entities
        AGENT_extra_edits               — edited beyond what was asked
        OTHER_constraint_mismatch       — something else
  7. Calibration behavior (did the agent decline infeasible / clarify
     ambiguous?)

Outputs:
  - Markdown report to stdout (or --out)
  - Optional CSV with per-scenario rows (--csv) for spreadsheet work

Usage:
    python scripts/analyze_run.py <results_dir_or_jsonl>
    python scripts/analyze_run.py results/v3_qwen7b_pilot --out report.md

Requires: results.jsonl from a completed --clearml run, and the v3.1
scenarios directory on disk (for taxonomy lookups).
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

import yaml

SCENARIOS_ROOT = Path("src/nlebench/dataset/scenarios_v3_1")

# Mirrors TOOL_HANDLERS in src/nlebench/tools/executor.py. Kept as a
# static list so the analysis script runs without importing nlebench.
KNOWN_TOOL_NAMES: set[str] = {
    "add_clip", "update_clip", "remove_clip", "split_clip",
    "add_caption", "update_caption", "remove_caption",
    "add_effect", "update_effect", "remove_effect",
    "add_transition", "update_transition", "remove_transition",
    "add_track", "update_track", "remove_track",
    "import_media", "update_media", "remove_media",
    "add_sequence", "add_timeline", "update_sequence", "update_timeline",
    "manage_bin", "link_clips", "unlink_clips", "query_state",
}

EDIT_TOOLS = {
    "update_clip", "add_effect", "update_effect", "remove_effect",
    "add_clip", "remove_clip", "split_clip",
    "add_caption", "update_caption", "remove_caption",
    "add_transition", "update_transition", "remove_transition",
    "import_media", "update_media", "remove_media",
    "link_clips", "unlink_clips",
}


def wilson_ci(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson score interval for a proportion k/n."""
    if n == 0:
        return 0.0, 0.0
    p = k / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n) / denom
    return max(0.0, center - half), min(1.0, center + half)


def ci_str(k: int, n: int) -> str:
    if n == 0:
        return "n/a"
    lo, hi = wilson_ci(k, n)
    p = k / n * 100
    return f"{p:.1f}% [{lo*100:.1f}, {hi*100:.1f}]"


@dataclass
class ScenarioMeta:
    feasibility: str
    information: str | None
    action: str | None
    scale: str
    cell: str
    expected_entities: set[str]


def load_scenarios(root: Path) -> dict[str, ScenarioMeta]:
    meta: dict[str, ScenarioMeta] = {}
    for p in root.rglob("*.yaml"):
        d = yaml.safe_load(p.read_text())
        t = d["taxonomy"]
        feas = t["feasibility"]
        info = t.get("information")
        action = t.get("action")
        cell = f"{info}×{action}" if feas == "feasible" else f"{feas}/{info}"
        # Collect expected entity IDs from required constraints
        expected: set[str] = set()
        for c in (d.get("constraints", {}).get("required") or []):
            if isinstance(c, dict):
                body = next(iter(c.values()))
                if isinstance(body, dict):
                    ent = body.get("entity") or body.get("clip_id")
                    if ent:
                        expected.add(ent)
                    changed = body.get("changed")
                    if isinstance(changed, list):
                        for e in changed:
                            if isinstance(e, str):
                                expected.add(e)
        item = ScenarioMeta(
            feasibility=feas, information=info, action=action,
            scale=t["scale"], cell=cell, expected_entities=expected,
        )
        meta[d["id"]] = item
        if d.get("legacy_id"):
            meta[d["legacy_id"]] = item
    return meta


def classify_failure(result: dict, sc: ScenarioMeta) -> str:
    if result.get("success"):
        return "PASS"
    val = result.get("validation") or {}
    behavior = val.get("behavior")

    if sc.feasibility in ("infeasible", "ambiguous"):
        if behavior == "execute":
            return f"CALIB_wrong_behavior[{sc.feasibility}]"
        return f"CALIB_other[{sc.feasibility}]"

    tcs = result.get("tool_calls") or []
    edits = [
        tc for tc in tcs
        if (tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", None))
        in EDIT_TOOLS
    ]
    if not edits:
        return "AGENT_no_edits"

    # add_effect abuse for transform attributes
    transform_effect_types = {"opacity", "scale", "rotation", "position",
                               "translate", "speed", "volume"}
    for tc in edits:
        name = tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", None)
        if name == "add_effect":
            et = (tc.get("arguments") or {}).get("effect_type", "")
            if et in transform_effect_types:
                return "TOOL_add_effect_for_transform"

    touched: set[str] = set()
    for tc in edits:
        args = tc.get("arguments") or {}
        for k in ("clip_id", "entity_id", "caption_id", "track_id", "effect_id"):
            v = args.get(k)
            if v:
                touched.add(v)
    missing = sc.expected_entities - touched
    extra = touched - sc.expected_entities
    if missing and not (sc.expected_entities & touched):
        return "AGENT_wrong_target"
    if missing:
        return "AGENT_partial_target"
    if extra:
        return "AGENT_extra_edits"

    return "OTHER_constraint_mismatch"


def find_results_file(arg: Path) -> Path:
    if arg.is_file():
        return arg
    candidates = sorted(arg.rglob("results.jsonl"))
    if not candidates:
        raise SystemExit(f"No results.jsonl found under {arg}")
    return candidates[-1]  # newest by sort order (timestamps embedded in parent dir name)


def fmt_row(label: str, k: int, n: int) -> str:
    return f"| {label} | {k}/{n} | {ci_str(k, n)} |"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("results", type=Path, help="Path to results dir or results.jsonl")
    ap.add_argument("--out", type=Path, help="Write markdown report to this file instead of stdout")
    ap.add_argument("--csv", type=Path, help="Also emit per-scenario CSV to this path")
    ap.add_argument("--scenarios-dir", type=Path, default=SCENARIOS_ROOT)
    args = ap.parse_args()

    results_path = find_results_file(args.results)
    results = [json.loads(line) for line in results_path.open()]
    meta = load_scenarios(args.scenarios_dir)

    # ---------- Aggregations ----------
    n_total = len(results)
    n_success = sum(1 for r in results if r.get("success"))

    # Per-axis
    by_feas = defaultdict(lambda: [0, 0])           # [success, total]
    by_scale = defaultdict(lambda: [0, 0])
    by_info = defaultdict(lambda: [0, 0])
    by_action = defaultdict(lambda: [0, 0])
    by_cell = defaultdict(lambda: [0, 0])

    for r in results:
        m = meta.get(r["scenario_id"])
        if not m:
            continue
        ok = 1 if r.get("success") else 0
        by_feas[m.feasibility][0] += ok
        by_feas[m.feasibility][1] += 1
        by_scale[m.scale][0] += ok
        by_scale[m.scale][1] += 1
        if m.feasibility == "feasible":
            by_info[m.information][0] += ok
            by_info[m.information][1] += 1
            by_action[m.action][0] += ok
            by_action[m.action][1] += 1
            by_cell[m.cell][0] += ok
            by_cell[m.cell][1] += 1

    # BPM
    bpm = defaultdict(lambda: Counter())
    for r in results:
        m = meta.get(r["scenario_id"])
        if not m:
            continue
        beh = (r.get("validation") or {}).get("behavior") or "noop"
        bpm[m.feasibility][beh] += 1

    # Tool compliance
    tool_total = 0
    tool_unknown = 0
    unknown_names: Counter = Counter()
    for r in results:
        for tc in r.get("tool_calls") or []:
            name = tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", None)
            if not name:
                continue
            tool_total += 1
            if name not in KNOWN_TOOL_NAMES:
                tool_unknown += 1
                unknown_names[name] += 1

    # Failure classification (feasible + calibration both classified)
    failures: Counter = Counter()
    per_scenario_class: list[tuple[str, str]] = []
    for r in results:
        m = meta.get(r["scenario_id"])
        if not m:
            per_scenario_class.append((r["scenario_id"], "NO_META"))
            continue
        cls = classify_failure(r, m)
        failures[cls] += 1
        per_scenario_class.append((r["scenario_id"], cls))

    # ---------- Report ----------
    out = []
    w = out.append

    w(f"# NLE-Bench v3 run report")
    w("")
    w(f"Source: `{results_path}`")
    w(f"Records: {n_total}")
    w("")

    w("## 1. Overall SR")
    w("")
    w("| scope | pass/total | SR (95% CI) |")
    w("|---|---|---|")
    w(fmt_row("all runs", n_success, n_total))
    for feas in ("feasible", "infeasible", "ambiguous"):
        k, n = by_feas[feas]
        w(fmt_row(feas, k, n))
    w("")

    w("## 2. SR by scale (all feasibilities)")
    w("")
    w("| scale | pass/total | SR (95% CI) |")
    w("|---|---|---|")
    for sc_name in ("L1", "L2", "L3"):
        k, n = by_scale[sc_name]
        w(fmt_row(sc_name, k, n))
    w("")

    w("## 3. SR by v3 axis (feasible only)")
    w("")
    w("**Information axis**")
    w("")
    w("| information | pass/total | SR (95% CI) |")
    w("|---|---|---|")
    for info in ("explicit", "state", "context", "diagnosis"):
        k, n = by_info[info]
        w(fmt_row(info, k, n))
    w("")
    w("**Action axis**")
    w("")
    w("| action | pass/total | SR (95% CI) |")
    w("|---|---|---|")
    for action in ("atomic", "compound", "dependent", "cumulative"):
        k, n = by_action[action]
        w(fmt_row(action, k, n))
    w("")

    w("## 4. Full 4×4 Information × Action matrix (feasible)")
    w("")
    w("| info \\\\ action | atomic | compound | dependent | cumulative |")
    w("|---|---|---|---|---|")
    for info in ("explicit", "state", "context", "diagnosis"):
        cells = []
        for action in ("atomic", "compound", "dependent", "cumulative"):
            k, n = by_cell[f"{info}×{action}"]
            if n == 0:
                cells.append("n/a")
            else:
                cells.append(f"{k}/{n} ({k/n*100:.0f}%)")
        w(f"| **{info}** | " + " | ".join(cells) + " |")
    w("")

    w("## 5. Behavioral Profile Matrix")
    w("")
    w("Rows: feasibility. Cols: agent behavior (execute/refuse/clarify/noop).")
    w("Values: count (% within row).")
    w("")
    w("| feasibility | execute | refuse | clarify | noop | n |")
    w("|---|---|---|---|---|---|")
    for feas in ("feasible", "infeasible", "ambiguous"):
        counts = bpm.get(feas, Counter())
        total = sum(counts.values())
        cells = []
        for beh in ("execute", "refuse", "clarify", "noop"):
            c = counts.get(beh, 0)
            pct = (c / total * 100) if total else 0
            cells.append(f"{c} ({pct:.0f}%)")
        w(f"| {feas} | " + " | ".join(cells) + f" | {total} |")
    w("")

    w("## 6. Tool protocol compliance")
    w("")
    w(f"- Total tool calls recorded: **{tool_total}**")
    w(f"- Hallucinated (unknown) names: **{tool_unknown}** ({tool_unknown/tool_total*100:.1f}% of calls)" if tool_total else "- No tool calls recorded")
    w(f"- Unique unknown names: **{len(unknown_names)}**")
    w("")
    if unknown_names:
        w("**Top 15 hallucinated names**")
        w("")
        w("| name | count |")
        w("|---|---|")
        for name, cnt in unknown_names.most_common(15):
            w(f"| `{name}` | {cnt} |")
        w("")

    w("## 7. Failure classification")
    w("")
    w("| category | count | % of all runs |")
    w("|---|---|---|")
    for cat, cnt in failures.most_common():
        w(f"| {cat} | {cnt} | {cnt/n_total*100:.1f}% |")
    w("")

    report = "\n".join(out)
    if args.out:
        args.out.write_text(report)
        print(f"wrote {args.out} ({len(report)} chars)")
    else:
        print(report)

    if args.csv:
        import csv
        with args.csv.open("w", newline="") as f:
            wr = csv.writer(f)
            wr.writerow([
                "scenario_id", "feasibility", "information", "action", "scale",
                "success", "behavior", "tsr", "csr", "failure_class",
                "n_tool_calls", "latency_s", "total_tokens",
            ])
            cls_map = dict(per_scenario_class)
            for r in results:
                m = meta.get(r["scenario_id"])
                val = r.get("validation") or {}
                wr.writerow([
                    r["scenario_id"],
                    m.feasibility if m else "",
                    m.information if m else "",
                    m.action if m else "",
                    m.scale if m else "",
                    r.get("success"),
                    val.get("behavior"),
                    val.get("tsr"),
                    val.get("csr"),
                    cls_map.get(r["scenario_id"], ""),
                    len(r.get("tool_calls") or []),
                    round((r.get("latency_ms") or 0) / 1000, 2),
                    (r.get("input_tokens") or 0) + (r.get("output_tokens") or 0),
                ])
        print(f"wrote {args.csv}")


if __name__ == "__main__":
    main()
