#!/usr/bin/env python3
"""
Human Study L2/L3 Scenario Sampling Script

Produces two non-overlapping stratified sets:
  - Set A (L2): 80 scenarios for Human-Metric Correlation
  - Set B (L3): 80 scenarios for Human Baseline

Stratification:
  Feasible (48 each):  3 per cell in 4 perception × 4 execution grid
  Infeasible (16 each): 4 per perception level
  Ambiguous (16 each):  4 per perception level

For L2, also selects 2 model outputs per scenario from 4 profile models.

Usage:
    python scripts/sample_human_study.py [--seed 42]
"""
from __future__ import annotations

import argparse
import json
import random
from collections import defaultdict
from pathlib import Path

import yaml

SCENARIOS_ROOT = Path(__file__).parent.parent / "src/nlebench/dataset/scenarios_v3"
RESULTS_ROOT = Path(__file__).parent.parent / "results"

# L2 profile models (from user_study_plan)
PROFILE_MODELS = {
    "Distributed": {
        "name": "Qwen3.5-27B",
        "path": "2026-04-07_18-09-46_Qwen_Qwen3.5-27B/results.jsonl",
    },
    "Balanced": {
        "name": "Sonnet 4.6",
        "path": "v4_sonnet46_canonical_full800/2026-04-07_10-11-43_claude-sonnet-4-6/results.jsonl",
    },
    "Clarify-only": {
        "name": "GPT-5.4",
        "path": "v4_gpt54_canonical_full800/2026-04-07_08-43-17_gpt-5.4/results.jsonl",
    },
    "Execute-dominant": {
        "name": "Qwen2.5-32B",
        "path": "2026-04-08_08-31-37_Qwen_Qwen2.5-32B-Instruct/results.jsonl",
    },
}

PERCEPTION_LEVELS = ["explicit", "state", "context", "diagnosis"]
EXECUTION_LEVELS = ["atomic", "compound", "dependent", "cumulative"]


def load_all_scenarios() -> dict[str, dict]:
    """Load all v3 scenarios, return {id: metadata}."""
    scenarios = {}
    for p in SCENARIOS_ROOT.rglob("*.yaml"):
        d = yaml.safe_load(p.read_text())
        sid = d["id"]
        t = d["taxonomy"]
        scenarios[sid] = {
            "id": sid,
            "path": str(p),
            "feasibility": t["feasibility"],
            "perception": t["information"],
            "execution": t.get("action"),  # None for inf/amb
            "scale": t["scale"],
            "split": d.get("split", "test"),
        }
    return scenarios


def load_model_results(model_path: str) -> dict[str, dict]:
    """Load results for a model, return {scenario_id: result}."""
    full_path = RESULTS_ROOT / model_path
    results = {}
    if not full_path.exists():
        print(f"  WARNING: {full_path} not found")
        return results
    with open(full_path) as f:
        for line in f:
            r = json.loads(line.strip())
            results[r["scenario_id"]] = r
    return results


def bucket_scenarios(scenarios: dict[str, dict]) -> dict[str, list[str]]:
    """Group scenario IDs by stratification bucket."""
    buckets = defaultdict(list)
    for sid, meta in scenarios.items():
        feas = meta["feasibility"]
        perc = meta["perception"]
        if feas == "feasible":
            exe = meta["execution"]
            key = f"feasible/{perc}/{exe}"
        else:
            key = f"{feas}/{perc}"
        buckets[key].append(sid)
    # Sort within each bucket for reproducibility
    for k in buckets:
        buckets[k].sort()
    return dict(buckets)


def stratified_sample_two_sets(
    buckets: dict[str, list[str]], seed: int
) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    """Sample two non-overlapping sets from each bucket."""
    rng = random.Random(seed)
    set_a = {}  # L2
    set_b = {}  # L3

    for key, ids in sorted(buckets.items()):
        parts = key.split("/")
        feas = parts[0]
        if feas == "feasible":
            n_per_set = 3  # 3 per cell × 16 cells = 48
        else:
            n_per_set = 4  # 4 per perception × 4 = 16

        total_needed = n_per_set * 2
        if len(ids) < total_needed:
            print(
                f"  WARNING: {key} has {len(ids)} scenarios, need {total_needed}. "
                f"Using all available."
            )
            sampled = list(ids)
            rng.shuffle(sampled)
        else:
            sampled = rng.sample(ids, total_needed)

        set_a[key] = sorted(sampled[:n_per_set])
        set_b[key] = sorted(sampled[n_per_set : n_per_set * 2])

    return set_a, set_b


def select_model_pairs(
    l2_ids: list[str], model_results: dict[str, dict[str, dict]]
) -> dict[str, list[str]]:
    """
    For each L2 scenario, pick 2 models balancing:
      1. Outcome diversity (one pass + one fail preferred)
      2. Profile coverage (all 4 profiles appear ~equally across 160 slots)

    Strategy: round-robin across profiles, with outcome-aware selection.
    """
    profiles = list(PROFILE_MODELS.keys())
    # Track usage counts to balance across profiles
    usage = {p: 0 for p in profiles}
    pairs = {}

    # Build per-scenario info
    scenario_info = {}
    for sid in l2_ids:
        info = {}
        for profile, mresults in model_results.items():
            if sid in mresults:
                r = mresults[sid]
                info[profile] = {
                    "model": PROFILE_MODELS[profile]["name"],
                    "success": r["success"],
                    "behavior": r["validation"].get("behavior", "unknown"),
                }
        scenario_info[sid] = info

    # Sort scenarios to process deterministically
    for sid in sorted(l2_ids):
        info = scenario_info[sid]
        available_profiles = [p for p in profiles if p in info]

        if len(available_profiles) < 2:
            selected = available_profiles[:2]
            pairs[sid] = [info[p]["model"] for p in selected] + ["MISSING"] * (
                2 - len(selected)
            )
            continue

        # Group by outcome
        passes = [p for p in available_profiles if info[p]["success"]]
        fails = [p for p in available_profiles if not info[p]["success"]]

        # Pick pair: prefer one pass + one fail, break ties by least-used profile
        def least_used(profile_list):
            return sorted(profile_list, key=lambda p: (usage[p], p))

        if passes and fails:
            p1 = least_used(passes)[0]
            p2 = least_used(fails)[0]
        else:
            # All same outcome: pick two least-used profiles
            ranked = least_used(available_profiles)
            p1, p2 = ranked[0], ranked[1]

        usage[p1] += 1
        usage[p2] += 1
        pairs[sid] = [info[p1]["model"], info[p2]["model"]]

    # Print profile usage stats
    print("  Profile usage across 160 slots:")
    for p, count in sorted(usage.items()):
        print(f"    {p:20s}: {count}")

    return pairs


def print_summary(
    set_a: dict[str, list[str]],
    set_b: dict[str, list[str]],
    model_pairs: dict[str, list[str]],
):
    """Print formatted summary."""
    a_ids = [sid for ids in set_a.values() for sid in ids]
    b_ids = [sid for ids in set_b.values() for sid in ids]

    print("=" * 70)
    print("HUMAN STUDY SCENARIO SAMPLING RESULT")
    print("=" * 70)

    print(f"\nSet A (L2 Human-Metric Correlation): {len(a_ids)} scenarios")
    print(f"Set B (L3 Human Baseline):            {len(b_ids)} scenarios")
    print(f"Overlap (should be 0):                {len(set(a_ids) & set(b_ids))}")

    for label, s in [("Set A (L2)", set_a), ("Set B (L3)", set_b)]:
        print(f"\n--- {label} ---")
        feas_count = sum(len(v) for k, v in s.items() if k.startswith("feasible"))
        inf_count = sum(len(v) for k, v in s.items() if k.startswith("infeasible"))
        amb_count = sum(len(v) for k, v in s.items() if k.startswith("ambiguous"))
        print(f"  Feasible: {feas_count}, Infeasible: {inf_count}, Ambiguous: {amb_count}")

        # Per-perception breakdown
        for perc in PERCEPTION_LEVELS:
            n = sum(
                len(v)
                for k, v in s.items()
                if perc in k
            )
            print(f"  {perc:>12}: {n}")

    # Model pair stats for L2
    if model_pairs:
        print("\n--- L2 Model Pair Stats ---")
        pair_types = defaultdict(int)
        for sid, pair in model_pairs.items():
            pair_types[tuple(sorted(pair))] += 1
        for pair, count in sorted(pair_types.items(), key=lambda x: -x[1]):
            print(f"  {pair[0]} + {pair[1]}: {count}")

        missing = sum(1 for p in model_pairs.values() if "MISSING" in p)
        if missing:
            print(f"  ⚠ {missing} scenarios with missing model data")


def export_json(
    set_a: dict[str, list[str]],
    set_b: dict[str, list[str]],
    model_pairs: dict[str, list[str]],
    scenarios: dict[str, dict],
    output_path: Path,
):
    """Export full sampling result as JSON."""
    def build_list(bucket_sets: dict[str, list[str]], with_pairs: bool = False):
        rows = []
        for bucket, ids in sorted(bucket_sets.items()):
            for sid in ids:
                meta = scenarios[sid]
                row = {
                    "scenario_id": sid,
                    "bucket": bucket,
                    "feasibility": meta["feasibility"],
                    "perception": meta["perception"],
                    "execution": meta["execution"],
                    "scale": meta["scale"],
                    "split": meta["split"],
                }
                if with_pairs and sid in model_pairs:
                    row["models"] = model_pairs[sid]
                rows.append(row)
        return rows

    result = {
        "seed": args.seed,
        "l2_set_a": build_list(set_a, with_pairs=True),
        "l3_set_b": build_list(set_b),
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(f"\nExported to {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--output",
        type=str,
        default="scripts/human_study_samples.json",
    )
    args = parser.parse_args()

    print("Loading scenarios...")
    scenarios = load_all_scenarios()
    print(f"  Total: {len(scenarios)} scenarios")

    print("\nBucketing...")
    buckets = bucket_scenarios(scenarios)
    for k, v in sorted(buckets.items()):
        print(f"  {k}: {len(v)}")

    print(f"\nSampling with seed={args.seed}...")
    set_a, set_b = stratified_sample_two_sets(buckets, args.seed)

    print("\nLoading model results for L2 pair selection...")
    model_results = {}
    for profile, info in PROFILE_MODELS.items():
        print(f"  Loading {profile} ({info['name']})...")
        model_results[profile] = load_model_results(info["path"])
        print(f"    → {len(model_results[profile])} results")

    l2_ids = [sid for ids in set_a.values() for sid in ids]
    print("\nSelecting model pairs for L2...")
    model_pairs = select_model_pairs(l2_ids, model_results)

    print_summary(set_a, set_b, model_pairs)

    output_path = Path(__file__).parent.parent / args.output
    export_json(set_a, set_b, model_pairs, scenarios, output_path)
