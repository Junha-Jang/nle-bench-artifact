#!/usr/bin/env python3
"""Recompute the inter-rater agreement statistics reported in the paper.

Inputs
------
data/human_study.json  (1,796 anonymized rater records)

Outputs (printed to stdout)
---------------------------
- L1 Fleiss kappa (feasibility), pooled and stratified by v3.1 modification status
- L1 Krippendorff alpha (feasibility, nominal)
- L2 Krippendorff alpha (full scenario-side design, model_a_score,
  model_b_score, A/B-averaged)
- L3 Cohen / Fleiss kappa (decision label) on overlap subset

Usage
-----
    python compute_iaa.py [--data DATA] [--scenarios SCENARIOS]

Notes
-----
- For each (rater, scenario, layer) tuple, the latest `updated_at` submission is canonical.
- Pilot/sanity rows are already excluded from the released JSON.
- This script is intentionally self-contained (no scipy/numpy dependency) so reviewers
  can run it without extra installation.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path


# ---------- Statistics helpers ----------

def fleiss_kappa(items, key, labels):
    """Fleiss' kappa over `items` (list of (sid, {rater: response})) for category `key`."""
    P_i, col_sums, total = [], {l: 0 for l in labels}, 0
    for sid, ratings in items:
        cs = Counter()
        for resp in ratings.values():
            v = resp.get(key)
            if v in labels:
                cs[v] += 1
        n = sum(cs.values())
        if n < 2:
            continue
        P_i.append(sum(c * (c - 1) for c in cs.values()) / (n * (n - 1)))
        for l in labels:
            col_sums[l] += cs[l]
        total += n
    if not P_i or total == 0:
        return None
    P_bar = sum(P_i) / len(P_i)
    p_j = {l: col_sums[l] / total for l in labels}
    Pe = sum(v * v for v in p_j.values())
    if Pe >= 1:
        return None
    return (P_bar - Pe) / (1 - Pe), len(P_i)


def krippendorff_nominal(items, key, labels):
    """Krippendorff's alpha (nominal metric)."""
    Do_sum, label_counts = 0, Counter()
    for sid, ratings in items:
        vs = [r.get(key) for r in ratings.values() if r.get(key) in labels]
        m = len(vs)
        if m < 2:
            continue
        label_counts.update(vs)
        cs = Counter(vs)
        dis = m * (m - 1) - sum(c * (c - 1) for c in cs.values())
        Do_sum += dis / (m - 1)
    n_total = sum(label_counts.values())
    if n_total < 2:
        return None
    De_num = n_total * (n_total - 1) - sum(c * (c - 1) for c in label_counts.values())
    if De_num == 0:
        return None
    return 1 - ((n_total - 1) * Do_sum) / De_num


def krippendorff_interval(items, key):
    """Krippendorff's alpha (interval metric) for a numeric Likert field."""
    Do_sum, all_vals = 0, []
    for sid, ratings in items:
        vs = [r.get(key) for r in ratings.values() if isinstance(r.get(key), (int, float))]
        m = len(vs)
        if m < 2:
            continue
        all_vals.extend(vs)
        s = sum((vs[i] - vs[j]) ** 2 for i in range(m) for j in range(m) if i != j)
        Do_sum += s / (m - 1)
    n = len(all_vals)
    if n < 2:
        return None
    total_sq = sum((all_vals[i] - all_vals[j]) ** 2
                   for i in range(n) for j in range(n) if i != j)
    if total_sq == 0:
        return None
    return 1 - ((n - 1) * Do_sum) / total_sq


def cohen_kappa_pairs(pairs, labels):
    """Average pairwise Cohen's kappa across all rater pairs on overlapping items.

    pairs: list of dicts {rater: label} (one per scenario in overlap set).
    """
    raters = sorted({r for p in pairs for r in p})
    kappas = []
    for i in range(len(raters)):
        for j in range(i + 1, len(raters)):
            ra, rb = raters[i], raters[j]
            x = [(p[ra], p[rb]) for p in pairs if ra in p and rb in p
                 and p[ra] in labels and p[rb] in labels]
            if len(x) < 2:
                continue
            agree = sum(1 for a, b in x if a == b) / len(x)
            ca = Counter(a for a, b in x)
            cb = Counter(b for a, b in x)
            n = len(x)
            pe = sum((ca[l] / n) * (cb[l] / n) for l in labels)
            if pe < 1:
                kappas.append((agree - pe) / (1 - pe))
    return sum(kappas) / len(kappas) if kappas else None


# ---------- Data loading ----------

def latest_per_tuple(records):
    """Reduce to the latest (rater, scenario, layer) tuple."""
    latest = {}
    for r in records:
        key = (r["layer"], r["scenario_id"], r["rater"])
        if key not in latest or r["updated_at"] > latest[key]["updated_at"]:
            latest[key] = r
    return list(latest.values())


def by_scenario(records, layer):
    out = defaultdict(dict)
    for r in records:
        if r["layer"] != layer:
            continue
        out[r["scenario_id"]][r["rater"]] = r["responses"]
    return list(out.items())


def l2_full_design_items(records):
    """Return 160 output-items: 80 scenarios x {model_a, model_b}."""
    out = defaultdict(dict)
    for r in records:
        if r["layer"] != "l2":
            continue
        responses = r["responses"]
        for side, key in (("model_a", "model_a_score"), ("model_b", "model_b_score")):
            out[(r["scenario_id"], side)][r["rater"]] = {"score": responses.get(key)}
    return list(out.items())


# ---------- Main ----------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="../data/human_study.json",
                    help="Path to anonymized human study JSON.")
    args = ap.parse_args()

    path = Path(args.data)
    if not path.exists():
        path = Path(__file__).resolve().parent.parent.parent / "data" / "human_study.json"
    records = latest_per_tuple(json.loads(path.read_text()))
    print(f"Records (latest per (rater, scenario, layer)): {len(records)}")
    print(f"  L1: {sum(1 for r in records if r['layer'] == 'l1')}")
    print(f"  L2: {sum(1 for r in records if r['layer'] == 'l2')}")
    print(f"  L3: {sum(1 for r in records if r['layer'] == 'l3')}")

    # ---------- L1 ----------
    print("\n=== L1: Scenario Validation ===")
    l1_items = by_scenario(records, "l1")
    l1_3 = [(s, d) for s, d in l1_items if len(d) >= 3]
    fea_labels = ["feasible", "infeasible", "ambiguous"]

    fk = fleiss_kappa(l1_3, "feasibility", fea_labels)
    if fk:
        print(f"  Fleiss kappa (feasibility, n={fk[1]} 3-rated): {fk[0]:.3f}")
    ka = krippendorff_nominal(l1_3, "feasibility", fea_labels)
    if ka is not None:
        print(f"  Krippendorff alpha (feasibility, nominal): {ka:.3f}")

    realism_alpha = krippendorff_interval(l1_3, "realism")
    if realism_alpha is not None:
        print(f"  Krippendorff alpha (realism, interval): {realism_alpha:.3f}")

    # Per-scenario realism summary
    real_means = []
    for _, ratings in l1_3:
        vals = [r.get("realism") for r in ratings.values()
                if isinstance(r.get("realism"), (int, float))]
        if vals:
            real_means.append(sum(vals) / len(vals))
    if real_means:
        mu = sum(real_means) / len(real_means)
        sd = (sum((x - mu) ** 2 for x in real_means) / len(real_means)) ** 0.5
        print(f"  Realism per-scenario mean: mu={mu:.3f} SD={sd:.3f} n={len(real_means)}")

    # ---------- L2 ----------
    print("\n=== L2: Human-Metric Correlation ===")
    l2_items = by_scenario(records, "l2")
    l2_2 = [(s, d) for s, d in l2_items if len(d) >= 2]
    l2_full = l2_full_design_items(records)
    full_alpha = krippendorff_interval(l2_full, "score")
    if full_alpha is not None:
        print(
            "  Krippendorff alpha "
            f"(full 80 scenarios x 2 outputs x 3 raters, interval): {full_alpha:.3f}"
        )
    a_alpha = krippendorff_interval(l2_2, "model_a_score")
    b_alpha = krippendorff_interval(l2_2, "model_b_score")
    if a_alpha is not None and b_alpha is not None:
        print(f"  Krippendorff alpha (model_a_score): {a_alpha:.3f}")
        print(f"  Krippendorff alpha (model_b_score): {b_alpha:.3f}")
        print(f"  A/B averaged: {(a_alpha + b_alpha) / 2:.3f}")
        print(
            "  Note: paper App. I also reports Spearman rho=0.55 from the "
            "same-source SR join; this standard-library helper reports "
            "agreement statistics only."
        )

    # ---------- L3 ----------
    print("\n=== L3: Mixed-Expertise Decision Reference ===")
    l3_items = by_scenario(records, "l3")
    l3_overlap = [(s, d) for s, d in l3_items if len(d) >= 2]
    decision_labels = ["execute", "clarify", "refuse"]

    fk3 = fleiss_kappa(
        [(s, d) for s, d in l3_items if len(d) >= 3],
        "decision", decision_labels
    )
    if fk3:
        print(f"  Fleiss kappa (decision, n={fk3[1]} 3-rated): {fk3[0]:.3f}")

    pairs = [{r: resp.get("decision") for r, resp in d.items()} for s, d in l3_overlap]
    ck = cohen_kappa_pairs(pairs, decision_labels)
    if ck is not None:
        print(f"  Average pairwise Cohen kappa (decision, n={len(pairs)} overlap): {ck:.3f}")

    print("\nCross-reference: paper App. I reports the official numbers used in the paper.")


if __name__ == "__main__":
    main()
