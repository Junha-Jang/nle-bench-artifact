"""
Analyze tool-name hallucinations from a run's results.jsonl.

The track runner logs `Unknown tool: X` warnings but still records the
invented tool_call in the result record. This script:

1. Classifies every tool call from results.jsonl as known / unknown
2. Aggregates unknown-call rate per scenario, per v3 cell, and per
   information/action axis
3. Lists the most frequent hallucinated names with counts and example
   scenarios, broken down by pattern type (primitive-bundle DSL vs
   pro-domain vocabulary)

Usage:
    python scripts/analyze_tool_hallucinations.py <results_dir>

Example:
    python scripts/analyze_tool_hallucinations.py results/v3_qwen7b_pilot
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import yaml

# Canonical tool set — mirrors TOOL_HANDLERS in src/nlebench/tools/executor.py
KNOWN_TOOLS: set[str] = {
    "add_clip", "update_clip", "remove_clip", "split_clip",
    "add_caption", "update_caption", "remove_caption",
    "add_effect", "update_effect", "remove_effect",
    "add_transition", "update_transition", "remove_transition",
    "add_track", "update_track", "remove_track",
    "import_media", "update_media", "remove_media",
    "add_sequence", "add_timeline", "update_sequence", "update_timeline",
    "manage_bin", "link_clips", "unlink_clips", "query_state",
}

SCENARIOS_ROOT = Path("src/nlebench/dataset/scenarios_v3")


def load_scenario_meta() -> dict[str, dict]:
    meta: dict[str, dict] = {}
    for p in SCENARIOS_ROOT.rglob("*.yaml"):
        d = yaml.safe_load(p.read_text())
        t = d["taxonomy"]
        feas = t["feasibility"]
        if feas == "feasible":
            cell = f"{t['information']}×{t['action']}"
        else:
            cell = f"{feas}/{t['information']}"
        item = {
            "feasibility": feas,
            "information": t.get("information"),
            "action": t.get("action"),
            "scale": t["scale"],
            "cell": cell,
        }
        meta[d["id"]] = item
        if d.get("legacy_id"):
            meta[d["legacy_id"]] = item
    return meta


def classify_pattern(name: str) -> str:
    """Categorize an unknown tool name by naming pattern.

    - primitive_dsl: combines verb+object into one call (find_longest_X,
      boost_Y_volume, mute_audio_clip). Suggests the model collapses a
      query+update sequence into a single imagined high-level API.
    - pro_domain: professional editing vocabulary that isn't in our
      canonical toolset (match_grade, apply_lut, denoise, stabilize,
      speech_to_text).
    - other: anything else (typos, dotted names, etc.)
    """
    n = name.lower()
    pro_domain = {
        "match_grade", "apply_lut", "color_grade", "color_correct",
        "denoise", "noise_reduction", "stabilize", "deshake",
        "speech_to_text", "transcribe", "auto_caption",
        "chroma_key", "green_screen", "remove_background",
        "beat_detect", "tempo_detect", "auto_sync",
        "face_detect", "object_detect", "track_object",
        "deflicker", "de_moire", "rolling_shutter",
    }
    if n in pro_domain:
        return "pro_domain"
    # Common DSL-ish verb prefixes
    dsl_verbs = (
        "find_", "get_", "list_", "boost_", "lower_", "raise_", "mute_",
        "unmute_", "fade_", "trim_", "cut_", "shift_", "move_", "scale_",
        "rotate_", "set_", "change_",
    )
    if any(n.startswith(v) for v in dsl_verbs):
        return "primitive_dsl"
    return "other"


def main(results_dir: Path) -> None:
    # Find the results.jsonl
    candidates = list(results_dir.rglob("results.jsonl"))
    if not candidates:
        print(f"No results.jsonl found under {results_dir}")
        sys.exit(1)
    results_path = candidates[0]
    print(f"Reading {results_path}")

    meta = load_scenario_meta()

    results = [json.loads(line) for line in results_path.open()]
    print(f"Total result records: {len(results)}")

    # Aggregate
    total_calls = 0
    unknown_calls = 0
    unknown_names = Counter()
    unknown_by_cell: dict[str, list[int]] = defaultdict(lambda: [0, 0])  # [unknown, total]
    unknown_by_info: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    unknown_by_action: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    unknown_by_feasibility: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    scenarios_with_any_unknown: set[str] = set()
    example_scenarios_per_name: dict[str, list[str]] = defaultdict(list)
    pattern_counts = Counter()
    pattern_names: dict[str, set[str]] = defaultdict(set)

    for r in results:
        sid = r.get("scenario_id")
        m = meta.get(sid, {})
        cell = m.get("cell", "unknown")
        info = m.get("information") or "-"
        action = m.get("action") or "-"
        feas = m.get("feasibility", "unknown")

        scenario_had_unknown = False
        for tc in r.get("tool_calls") or []:
            name = tc.get("name", "")
            total_calls += 1
            unknown_by_cell[cell][1] += 1
            unknown_by_info[info][1] += 1
            unknown_by_action[action][1] += 1
            unknown_by_feasibility[feas][1] += 1
            if name and name not in KNOWN_TOOLS:
                unknown_calls += 1
                unknown_names[name] += 1
                unknown_by_cell[cell][0] += 1
                unknown_by_info[info][0] += 1
                unknown_by_action[action][0] += 1
                unknown_by_feasibility[feas][0] += 1
                scenario_had_unknown = True
                if len(example_scenarios_per_name[name]) < 3:
                    example_scenarios_per_name[name].append(sid)
                pat = classify_pattern(name)
                pattern_counts[pat] += 1
                pattern_names[pat].add(name)

        if scenario_had_unknown:
            scenarios_with_any_unknown.add(sid)

    # ---------- Report ----------
    print()
    print("=" * 60)
    print("TOOL-CALL HALLUCINATION REPORT")
    print("=" * 60)
    print(f"Total tool calls issued:          {total_calls}")
    print(f"Unknown (hallucinated) calls:     {unknown_calls}")
    rate = (unknown_calls / total_calls * 100) if total_calls else 0
    print(f"Call-level hallucination rate:    {rate:.1f}%")
    print(f"Scenarios with ≥1 unknown call:   {len(scenarios_with_any_unknown)}"
          f" / {len(results)} ({len(scenarios_with_any_unknown)/len(results)*100:.1f}%)")
    print(f"Unique hallucinated names:        {len(unknown_names)}")

    print()
    print("--- Pattern breakdown ---")
    for pat in ("primitive_dsl", "pro_domain", "other"):
        c = pattern_counts.get(pat, 0)
        share = (c / unknown_calls * 100) if unknown_calls else 0
        n_unique = len(pattern_names.get(pat, set()))
        print(f"  {pat:<15}  calls={c:>4} ({share:5.1f}%)  unique_names={n_unique}")

    print()
    print("--- Top 20 hallucinated names ---")
    for name, count in unknown_names.most_common(20):
        pat = classify_pattern(name)
        examples = ", ".join(example_scenarios_per_name[name][:2])
        print(f"  {count:>3}x [{pat:<14}] {name:<40} (e.g. {examples})")

    def print_section(title: str, data: dict[str, list[int]], order: list[str] | None = None):
        print()
        print(f"--- {title} ---")
        keys = order if order else sorted(data.keys())
        for k in keys:
            if k not in data:
                continue
            unk, tot = data[k]
            pct = (unk / tot * 100) if tot else 0
            print(f"  {k:<22}  {unk:>4} / {tot:>4}  ({pct:5.1f}%)")

    print_section(
        "By feasibility",
        unknown_by_feasibility,
        order=["feasible", "infeasible", "ambiguous"],
    )
    print_section(
        "By information axis",
        unknown_by_info,
        order=["explicit", "state", "context", "diagnosis"],
    )
    print_section(
        "By action axis",
        unknown_by_action,
        order=["atomic", "compound", "dependent", "cumulative"],
    )

    # v3 cells — feasible only, sorted
    print()
    print("--- By v3 feasible cell (unknown / total tool calls) ---")
    info_order = ["explicit", "state", "context", "diagnosis"]
    action_order = ["atomic", "compound", "dependent", "cumulative"]
    col_w = 14
    header = " " * 12 + "".join(f"{a:>{col_w}}" for a in action_order)
    print(header)
    for info in info_order:
        cells = []
        for action in action_order:
            key = f"{info}×{action}"
            unk, tot = unknown_by_cell.get(key, [0, 0])
            pct = (unk / tot * 100) if tot else 0
            cells.append(f"{unk}/{tot} ({pct:.0f}%)")
        print(f"  {info:<10}" + "".join(f"{c:>{col_w}}" for c in cells))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)
    main(Path(sys.argv[1]))
