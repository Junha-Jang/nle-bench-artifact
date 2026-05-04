"""
Paper v4 analysis: ANOVA + BPM for all exp10 models.

Produces:
  1. BPM (Behavioral Profile Matrix) for each model
  2. Two-way ANOVA on SR-feasible (perception × execution, pooled across models)
  3. Per-model Kruskal-Wallis tests
  4. Logistic regression with model as covariate

Usage:
    cd /path/to/supplementary/code
    python scripts/paper_v4_analysis.py
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import yaml

SCENARIOS_ROOT = Path("src/nlebench/dataset/scenarios_v3_1")

# Map of model short name -> results.jsonl path (exp10 full-800 runs)
RESULT_PATHS = {
    # Frontier API
    "GPT-5.4": "results/v4_gpt54_canonical_full800/2026-04-07_08-43-17_gpt-5.4/results.jsonl",
    "Sonnet 4.6": "results/v4_sonnet46_canonical_full800/2026-04-07_10-11-43_claude-sonnet-4-6/results.jsonl",
    # Qwen 3.5 series
    "Qwen3.5-27B": "results/2026-04-07_18-09-46_Qwen_Qwen3.5-27B/results.jsonl",
    "Qwen3.5-9B": "results/2026-04-07_17-50-01_Qwen_Qwen3.5-9B/results.jsonl",
    "Qwen3.5-4B": "results/2026-04-07_17-36-00_Qwen_Qwen3.5-4B/results.jsonl",
    "Qwen3.5-2B": "results/2026-04-07_17-29-18_Qwen_Qwen3.5-2B/results.jsonl",
    "Qwen3.5-0.8B": "results/2026-04-07_17-24-11_Qwen_Qwen3.5-0.8B/results.jsonl",
    "Qwen3.5-35B-A3B": "results/2026-04-07_19-06-27_Qwen_Qwen3.5-35B-A3B/results.jsonl",
    # Qwen 2.5 series (rerun with scope prompt)
    "Qwen2.5-32B": "results/rerun_scope_2026-04-07/06_Qwen_Qwen2.5-32B-Instruct/2026-04-07_20-56-57_Qwen_Qwen2.5-32B-Instruct/results.jsonl",
    "Qwen2.5-14B": "results/rerun_scope_2026-04-07/03_Qwen_Qwen2.5-14B-Instruct/2026-04-07_20-11-28_Qwen_Qwen2.5-14B-Instruct/results.jsonl",
    "Qwen2.5-7B": "results/rerun_scope_2026-04-07/01_Qwen_Qwen2.5-7B-Instruct/2026-04-07_20-02-03_Qwen_Qwen2.5-7B-Instruct/results.jsonl",
    # DeepSeek
    "DS-R1-14B": "results/rerun_scope_2026-04-07/04_deepseek-ai_DeepSeek-R1-Distill-Qwen-14B/2026-04-07_20-18-39_deepseek-ai_DeepSeek-R1-Distill-Qwen-14B/results.jsonl",
    "DS-R1-32B": "results/rerun_scope_2026-04-07/07_deepseek-ai_DeepSeek-R1-Distill-Qwen-32B/2026-04-07_21-10-01_deepseek-ai_DeepSeek-R1-Distill-Qwen-32B/results.jsonl",
    # Gemma 4
    "Gemma4-31B": "results/gemma4_31b_full800/2026-04-07_16-00-11_google_gemma-4-31B-it/results.jsonl",
    "Gemma4-E4B": "results/2026-04-07_17-04-05_google_gemma-4-E4B-it/results.jsonl",
    "Gemma4-E2B": "results/2026-04-07_17-16-43_google_gemma-4-E2B-it/results.jsonl",
    "Gemma4-26B-A4B": "results/2026-04-07_16-57-07_google_gemma-4-26B-A4B-it/results.jsonl",
    # Llama
    "Llama-8B": "results/rerun_scope_2026-04-07/02_meta-llama_Llama-3.1-8B-Instruct/2026-04-07_20-06-18_meta-llama_Llama-3.1-8B-Instruct/results.jsonl",
    # Open track
    "GPT-5.4-Open": "results/v4_gpt54_open_full800/2026-04-07_18-33-10_gpt-5.4/results.jsonl",
}


def load_scenarios(root: Path) -> dict[str, dict]:
    """Load scenario metadata from YAML files."""
    meta = {}
    for p in root.rglob("*.yaml"):
        d = yaml.safe_load(p.read_text())
        t = d["taxonomy"]
        item = {
            "feasibility": t["feasibility"],
            "information": t.get("information"),
            "action": t.get("action"),
        }
        meta[d["id"]] = item
        if d.get("legacy_id"):
            meta[d["legacy_id"]] = item
    return meta


def load_results(path: str) -> list[dict]:
    """Load results.jsonl, taking run_number=0 (or first) per scenario."""
    p = Path(path)
    if not p.exists():
        return []
    rows = {}
    for line in p.read_text().splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        sid = r["scenario_id"]
        run = r.get("run_number", 0)
        if sid not in rows or run < rows[sid].get("run_number", 999):
            rows[sid] = r
    return list(rows.values())


def compute_bpm(results: list[dict], scenarios: dict) -> dict:
    """Compute BPM: feasibility x behavior counts."""
    bpm = defaultdict(Counter)
    for r in results:
        sid = r["scenario_id"]
        sc = scenarios.get(sid)
        if not sc:
            continue
        feas = sc["feasibility"]
        val = r.get("validation") or {}
        behavior = val.get("behavior", "noop")
        bpm[feas][behavior] += 1
    return dict(bpm)


def print_bpm(name: str, bpm: dict):
    """Print BPM as a formatted table."""
    print(f"\n### {name}")
    print(f"| Feasibility | Execute | Refuse | Clarify | Noop | n |")
    print(f"|---|---|---|---|---|---|")
    for feas in ["feasible", "infeasible", "ambiguous"]:
        c = bpm.get(feas, Counter())
        n = sum(c.values())
        if n == 0:
            continue
        print(f"| {feas} | {c['execute']} ({c['execute']/n*100:.0f}%) "
              f"| {c['refuse']} ({c['refuse']/n*100:.0f}%) "
              f"| {c['clarify']} ({c['clarify']/n*100:.0f}%) "
              f"| {c['noop']} ({c['noop']/n*100:.0f}%) "
              f"| {n} |")


def main():
    print("# Paper v4 Analysis: ANOVA + BPM\n")

    # Load scenario metadata
    scenarios = load_scenarios(SCENARIOS_ROOT)
    print(f"Loaded {len(scenarios)} scenarios\n")

    # ===== PART 1: BPM for all models =====
    print("## 1. Behavioral Profile Matrix (BPM)\n")

    all_feasible_data = []  # For ANOVA: (model, info, action, success)

    for name, path in sorted(RESULT_PATHS.items()):
        results = load_results(path)
        if not results:
            print(f"### {name}: NO DATA (file not found: {path})")
            continue

        bpm = compute_bpm(results, scenarios)
        print_bpm(name, bpm)

        # Collect feasible data for ANOVA
        for r in results:
            sid = r["scenario_id"]
            sc = scenarios.get(sid)
            if not sc or sc["feasibility"] != "feasible":
                continue
            info = sc["information"]
            action = sc["action"]
            success = 1 if r.get("success") else 0
            all_feasible_data.append((name, info, action, success))

    # ===== PART 2: Two-way ANOVA =====
    print("\n\n## 2. Two-way ANOVA on SR-feasible\n")

    try:
        import numpy as np
        import pandas as pd
        from scipy import stats
    except ImportError:
        print("ERROR: numpy, pandas, scipy required. Install with:")
        print("  pip install numpy pandas scipy")
        sys.exit(1)

    df = pd.DataFrame(all_feasible_data, columns=["model", "information", "action", "success"])
    print(f"Total feasible observations: N = {len(df)}")
    print(f"Models: {df['model'].nunique()}")
    print(f"Unique information levels: {sorted(df['information'].unique())}")
    print(f"Unique action levels: {sorted(df['action'].unique())}")

    # Overall two-way ANOVA (pooled across models)
    print("\n### 2a. Pooled two-way ANOVA (information × action)\n")

    # Create design matrix
    from itertools import product as iterprod

    info_levels = sorted(df["information"].unique())
    action_levels = sorted(df["action"].unique())

    # Compute cell means
    print("Cell means (SR-feasible %):")
    print(f"{'':15s}", end="")
    for a in action_levels:
        print(f"{a:>12s}", end="")
    print(f"{'Row Mean':>12s}")

    for i in info_levels:
        print(f"{i:15s}", end="")
        row_vals = []
        for a in action_levels:
            mask = (df["information"] == i) & (df["action"] == a)
            val = df.loc[mask, "success"].mean() * 100
            row_vals.append(val)
            print(f"{val:11.1f}%", end="")
        print(f"{sum(row_vals)/len(row_vals):11.1f}%")

    print(f"{'Col Mean':15s}", end="")
    for a in action_levels:
        mask = df["action"] == a
        val = df.loc[mask, "success"].mean() * 100
        print(f"{val:11.1f}%", end="")
    print(f"{df['success'].mean()*100:11.1f}%")

    # Two-way ANOVA using OLS
    # Since scipy doesn't have built-in 2-way ANOVA, use manual SS decomposition
    grand_mean = df["success"].mean()
    N = len(df)

    # SS for information
    ss_info = 0
    for i in info_levels:
        mask = df["information"] == i
        ni = mask.sum()
        mi = df.loc[mask, "success"].mean()
        ss_info += ni * (mi - grand_mean) ** 2

    # SS for action
    ss_action = 0
    for a in action_levels:
        mask = df["action"] == a
        na = mask.sum()
        ma = df.loc[mask, "success"].mean()
        ss_action += na * (ma - grand_mean) ** 2

    # SS total
    ss_total = ((df["success"] - grand_mean) ** 2).sum()

    # SS for cells (interaction + main)
    ss_cells = 0
    for i in info_levels:
        for a in action_levels:
            mask = (df["information"] == i) & (df["action"] == a)
            nc = mask.sum()
            if nc > 0:
                mc = df.loc[mask, "success"].mean()
                ss_cells += nc * (mc - grand_mean) ** 2

    ss_interaction = ss_cells - ss_info - ss_action
    ss_residual = ss_total - ss_cells

    df_info = len(info_levels) - 1
    df_action = len(action_levels) - 1
    df_interaction = df_info * df_action
    df_residual = N - len(info_levels) * len(action_levels)

    ms_info = ss_info / df_info
    ms_action = ss_action / df_action
    ms_interaction = ss_interaction / df_interaction
    ms_residual = ss_residual / df_residual

    f_info = ms_info / ms_residual
    f_action = ms_action / ms_residual
    f_interaction = ms_interaction / ms_residual

    p_info = 1 - stats.f.cdf(f_info, df_info, df_residual)
    p_action = 1 - stats.f.cdf(f_action, df_action, df_residual)
    p_interaction = 1 - stats.f.cdf(f_interaction, df_interaction, df_residual)

    eta2_info = ss_info / ss_total
    eta2_action = ss_action / ss_total
    eta2_interaction = ss_interaction / ss_total

    print(f"\nANOVA Table:")
    print(f"{'Source':20s} {'SS':>10s} {'df':>5s} {'MS':>10s} {'F':>10s} {'p':>12s} {'η²':>8s}")
    print("-" * 80)
    print(f"{'Information':20s} {ss_info:10.2f} {df_info:5d} {ms_info:10.4f} {f_info:10.2f} {p_info:12.2e} {eta2_info:8.4f}")
    print(f"{'Action':20s} {ss_action:10.2f} {df_action:5d} {ms_action:10.4f} {f_action:10.2f} {p_action:12.2e} {eta2_action:8.4f}")
    print(f"{'Info×Action':20s} {ss_interaction:10.2f} {df_interaction:5d} {ms_interaction:10.4f} {f_interaction:10.2f} {p_interaction:12.2e} {eta2_interaction:8.4f}")
    print(f"{'Residual':20s} {ss_residual:10.2f} {df_residual:5d} {ms_residual:10.4f}")
    print(f"{'Total':20s} {ss_total:10.2f} {N-1:5d}")

    # ===== PART 3: Per-model Kruskal-Wallis =====
    print("\n\n### 2b. Per-model Kruskal-Wallis tests\n")
    print(f"{'Model':20s} {'H(info)':>10s} {'p(info)':>12s} {'H(action)':>10s} {'p(action)':>12s}")
    print("-" * 70)

    for model in sorted(df["model"].unique()):
        mdf = df[df["model"] == model]
        if len(mdf) < 40:
            continue

        # Info axis
        groups_info = [mdf.loc[mdf["information"] == i, "success"].values for i in info_levels]
        groups_info = [g for g in groups_info if len(g) > 0]
        if len(groups_info) >= 2:
            h_info, p_info_kw = stats.kruskal(*groups_info)
        else:
            h_info, p_info_kw = 0, 1

        # Action axis
        groups_action = [mdf.loc[mdf["action"] == a, "success"].values for a in action_levels]
        groups_action = [g for g in groups_action if len(g) > 0]
        if len(groups_action) >= 2:
            h_action, p_action_kw = stats.kruskal(*groups_action)
        else:
            h_action, p_action_kw = 0, 1

        sig_info = "*" if p_info_kw < 0.05 else " "
        sig_action = "*" if p_action_kw < 0.05 else " "
        print(f"{model:20s} {h_info:10.1f} {p_info_kw:12.2e}{sig_info} {h_action:10.1f} {p_action_kw:12.2e}{sig_action}")

    # ===== PART 4: Logistic regression =====
    print("\n\n### 2c. Logistic regression (info + action + model)\n")
    try:
        from sklearn.linear_model import LogisticRegression
        from sklearn.preprocessing import LabelEncoder

        le_info = LabelEncoder().fit(df["information"])
        le_action = LabelEncoder().fit(df["action"])
        le_model = LabelEncoder().fit(df["model"])

        # One-hot encode
        X_info = pd.get_dummies(df["information"], prefix="info")
        X_action = pd.get_dummies(df["action"], prefix="action")
        X_model = pd.get_dummies(df["model"], prefix="model")
        X = pd.concat([X_info, X_action, X_model], axis=1)
        y = df["success"].values

        lr = LogisticRegression(max_iter=1000, solver="lbfgs", C=1e6)
        lr.fit(X, y)

        print("Odds Ratios (reference: first alphabetical level):")
        for fname, coef in zip(X.columns, lr.coef_[0]):
            or_val = 2.718281828 ** coef
            print(f"  {fname:40s}  OR = {or_val:.3f}  (coef = {coef:.4f})")

    except ImportError:
        print("sklearn not available, skipping logistic regression")

    print("\n\nDone.")


if __name__ == "__main__":
    main()
