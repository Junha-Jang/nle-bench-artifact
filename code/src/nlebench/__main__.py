"""
NLE-Bench CLI

Run the NLE-Bench benchmark from the command line.

Usage:
    # Run with Anthropic (default)
    python -m nlebench --provider anthropic --model claude-sonnet-4-6-2026-02-17

    # Run with OpenAI GPT-5.x via Responses API
    python -m nlebench --provider openai --model gpt-5.4 --reasoning-effort medium

    # Run with vLLM (local model)
    python -m nlebench --provider vllm --model Qwen/Qwen3-32B \\
        --vllm-url http://localhost:8000/v1

    # Quick mode (subset of scenarios)
    python -m nlebench --quick

    # Specific levels
    python -m nlebench --levels L1 L2
"""

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

from nlebench import __version__
from nlebench.config import NLEBenchConfig, LLMConfig, OutputConfig


def parse_args():
    parser = argparse.ArgumentParser(
        description="NLE-Bench: Non-Linear Editing Agent Benchmark",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument(
        "--version", "-v",
        action="version",
        version=f"nlebench {__version__}",
    )

    # Provider settings
    provider_group = parser.add_argument_group("LLM Provider")
    provider_group.add_argument(
        "--provider", "-p",
        choices=["anthropic", "openai", "google", "vllm"],
        default="anthropic",
        help="LLM provider (default: anthropic)",
    )
    provider_group.add_argument(
        "--model", "-m",
        help="Model identifier (e.g., gpt-5.4, claude-sonnet-4-6-2026-02-17, Qwen/Qwen3-32B)",
    )
    provider_group.add_argument(
        "--reasoning-effort",
        choices=["low", "medium", "high"],
        default=os.environ.get("OPENAI_REASONING_EFFORT"),
        help=(
            "OpenAI reasoning effort for o-series/GPT-5.x models. "
            "Defaults to $OPENAI_REASONING_EFFORT; GPT-5.x paper rows use medium."
        ),
    )
    provider_group.add_argument(
        "--vllm-url",
        default=os.environ.get("VLLM_BASE_URL", "http://localhost:8000/v1"),
        help="vLLM server URL (default: $VLLM_BASE_URL or http://localhost:8000/v1)",
    )
    provider_group.add_argument(
        "--api-key",
        help="API key (uses environment variable if not set)",
    )
    provider_group.add_argument(
        "--tool-mode",
        choices=["native", "text", "auto"],
        default="auto",
        help="Tool calling mode for vLLM: native (use server-side tool parser), "
             "text (prompt-based JSON), auto (try native, fallback to text). "
             "Default: auto",
    )
    provider_group.add_argument(
        "--temperature",
        type=float,
        default=0.0,
        help="Sampling temperature (default: 0.0)",
    )
    provider_group.add_argument(
        "--max-tokens",
        type=int,
        default=4096,
        help="Max tokens for response (default: 4096)",
    )

    # Benchmark track
    track_group = parser.add_argument_group("Benchmark Track")
    track_group.add_argument(
        "--track",
        choices=["canonical", "open"],
        default="canonical",
        help="Benchmark track (default: canonical)",
    )

    # Scenario filtering
    filter_group = parser.add_argument_group("Scenario Filtering")
    filter_group.add_argument(
        "--levels",
        nargs="+",
        default=["L1", "L2", "L3"],
        help="Scale levels to run (default: L1 L2 L3)",
    )
    filter_group.add_argument(
        "--categories",
        nargs="+",
        help="Categories to run (default: all)",
    )
    filter_group.add_argument(
        "--scenarios",
        nargs="+",
        help="Specific scenario IDs to run",
    )
    filter_group.add_argument(
        "--feasibilities",
        nargs="+",
        choices=["feasible", "infeasible", "ambiguous"],
        help="Feasibility types to run (default: all)",
    )
    filter_group.add_argument(
        "--scenarios-dir",
        type=Path,
        default=None,
        help="Override scenarios root directory (e.g., to run scenarios_v3)",
    )

    # Run settings
    run_group = parser.add_argument_group("Run Settings")
    run_group.add_argument(
        "--runs", "-r",
        type=int,
        default=3,
        help="Runs per scenario (default: 3)",
    )
    run_group.add_argument(
        "--quick", "-q",
        action="store_true",
        help="Quick mode: run subset of scenarios",
    )
    run_group.add_argument(
        "--quick-count",
        type=int,
        default=10,
        help="Number of scenarios in quick mode (default: 10)",
    )
    run_group.add_argument(
        "--timeout",
        type=float,
        default=120.0,
        help="Timeout per scenario in seconds (default: 120)",
    )
    run_group.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed (default: 42)",
    )
    run_group.add_argument(
        "--concurrency",
        type=int,
        default=8,
        help="Number of concurrent scenario executions (default: 8)",
    )

    # Output settings
    output_group = parser.add_argument_group("Output")
    output_group.add_argument(
        "--output", "-o",
        type=Path,
        default=Path("results"),
        help="Output directory (default: results)",
    )
    output_group.add_argument(
        "--no-save-states",
        action="store_true",
        help="Don't save initial/final states (saves disk space)",
    )

    # Experiment tracking
    tracking_group = parser.add_argument_group("Experiment Tracking")
    tracking_group.add_argument(
        "--clearml",
        action="store_true",
        help="Log experiment to ClearML (requires clearml package)",
    )
    tracking_group.add_argument(
        "--clearml-project",
        default="nle-bench",
        help="ClearML project name (default: nle-bench)",
    )
    tracking_group.add_argument(
        "--clearml-intent",
        choices=["pilot", "sanity", "debug", "regression", "ablation", "paper"],
        default="pilot",
        help="Purpose of this run — becomes the ClearML intent tag",
    )
    tracking_group.add_argument(
        "--clearml-note",
        type=str,
        default=None,
        help="Free-text context for this run (stored in task comment, not tags)",
    )

    # Logging
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )

    return parser.parse_args()


def get_default_model(provider: str) -> str:
    """Get default model for provider."""
    defaults = {
        "anthropic": "claude-sonnet-4-6-2026-02-17",
        "openai": "gpt-5.4",
        "google": "gemini-3-flash-preview",
        "vllm": "Qwen/Qwen3-32B",
    }
    return defaults.get(provider, "gpt-5.4")


async def run_benchmark(args):
    """Run the benchmark with given arguments."""
    from nlebench.providers import get_provider
    from nlebench.runner import TrackRunner
    from nlebench.runner.scenario_loader import load_scenarios
    from nlebench.models import ExecutionResult

    # ClearML integration (optional)
    mode = "quick" if args.quick else "full"
    clearml_task = None
    if args.clearml:
        try:
            from nlebench.tracking import register_task
            model_name = args.model or get_default_model(args.provider)
            clearml_reasoning_effort = args.reasoning_effort
            if args.provider == "openai" and model_name.startswith("gpt-5") and clearml_reasoning_effort is None:
                clearml_reasoning_effort = "medium"
            scenario_count = args.quick_count if args.quick else 800
            run_label = f"{mode}-{scenario_count}" if args.runs == 1 else f"{mode}-{scenario_count}x{args.runs}"
            display_name = f"{args.provider}({model_name})" if args.provider not in ("openai", "anthropic", "google", "vllm") else model_name
            clearml_task = register_task(
                project_name=args.clearml_project,
                task_name=f"{display_name} / {args.track} / {run_label}",
                intent=args.clearml_intent,
                note=args.clearml_note,
                hyperparameters={
                    "model": model_name,
                    "provider": args.provider,
                    "track": args.track,
                    "mode": mode,
                    "reasoning_effort": clearml_reasoning_effort,
                    "runs_per_scenario": args.runs,
                    "timeout_seconds": args.timeout,
                    "seed": getattr(args, "seed", None),
                },
            )
        except ImportError:
            print("Warning: --clearml flag set but clearml package not installed. Skipping.")

    # Build config
    model = args.model or get_default_model(args.provider)
    reasoning_effort = args.reasoning_effort
    if args.provider == "openai" and model.startswith("gpt-5") and reasoning_effort is None:
        reasoning_effort = "medium"

    # Determine base_url
    base_url = None
    if args.provider == "vllm":
        base_url = args.vllm_url

    config = NLEBenchConfig(
        runs_per_scenario=args.runs,
        random_seed=args.seed,
        timeout_seconds=args.timeout,
        levels=args.levels,
        categories=args.categories,
        scenario_ids=args.scenarios,
        feasibilities=args.feasibilities,
        quick_mode=args.quick,
        quick_scenario_count=args.quick_count,
        llm=LLMConfig(
            provider=args.provider,
            model=model,
            temperature=args.temperature,
            max_tokens=args.max_tokens,
            base_url=base_url,
            api_key=args.api_key,
            reasoning_effort=reasoning_effort,
        ),
        output=OutputConfig(
            base_dir=args.output,
            save_states=not args.no_save_states,
        ),
    )

    # Create provider
    provider = get_provider(
        provider_name=args.provider,
        model=model,
        temperature=args.temperature,
        max_tokens=args.max_tokens,
        base_url=base_url,
        api_key=args.api_key,
        tool_mode=getattr(args, "tool_mode", "auto"),
        reasoning_effort=reasoning_effort,
    )

    print(f"NLE-Bench v{__version__}")
    print(f"Provider: {args.provider}")
    print(f"Model: {model}")
    if args.provider == "openai" and reasoning_effort:
        print(f"Reasoning effort: {reasoning_effort}")
    print(f"Track: {args.track}")
    print()

    # Load scenarios
    scenarios = load_scenarios(
        scenarios_dir=args.scenarios_dir,
        levels=args.levels,
        categories=args.categories,
        scenario_ids=args.scenarios,
        feasibilities=args.feasibilities,
    )

    if args.quick:
        # Quick mode sampling
        import random
        rng = random.Random(args.seed)
        scenarios = rng.sample(scenarios, min(args.quick_count, len(scenarios)))

    # Compute taxonomy distribution on the v3 (Information × Action) grid,
    # with a separate row for infeasible/ambiguous calibration scenarios.
    from collections import Counter
    v3_dist = Counter()
    calib_dist = Counter()
    for sc in scenarios:
        t = sc.effective_taxonomy
        feas = t.feasibility.value
        if feas in ("infeasible", "ambiguous"):
            calib_dist[feas] += 1
        else:
            info = t.information or "-"
            action = t.action or "-"
            v3_dist[(info, action)] += 1

    print(f"Loaded {len(scenarios)} scenarios")
    print()
    print("  Feasible (Information × Action)")
    info_axis = ["explicit", "state", "context", "diagnosis"]
    action_axis = ["atomic", "compound", "dependent", "cumulative"]
    col_w = 12
    header = " " * 12 + "".join(f"{a:>{col_w}}" for a in action_axis)
    print(header)
    for info in info_axis:
        row = f"  {info:<10}" + "".join(
            f"{v3_dist.get((info, a), 0):>{col_w}}" for a in action_axis
        )
        print(row)
    if calib_dist:
        print()
        print("  Calibration")
        total_calib = sum(calib_dist.values())
        for feas in ("infeasible", "ambiguous"):
            if calib_dist.get(feas):
                print(f"    {feas:<12} {calib_dist[feas]}")
        print(f"    {'total':<12} {total_calib}")
    print()

    # Log config + taxonomy to ClearML
    if clearml_task:
        clearml_task.connect({
            "provider": args.provider,
            "model": model,
            "track": args.track,
            "reasoning_effort": reasoning_effort,
            "temperature": args.temperature,
            "max_tokens": args.max_tokens,
            "runs_per_scenario": args.runs,
            "quick_mode": args.quick,
            "scales": ["L1", "L2", "L3"],
            "scenario_count": len(scenarios),
            "v3_distribution": {
                f"{info}.{action}": v3_dist.get((info, action), 0)
                for info in ("explicit", "state", "context", "diagnosis")
                for action in ("atomic", "compound", "dependent", "cumulative")
            },
            "calibration_counts": dict(calib_dist),
            "timeout_seconds": args.timeout,
        })

    # Shuffle scenarios for unbiased Live SR
    import random
    rng = random.Random(args.seed)
    rng.shuffle(scenarios)

    # Run benchmark
    runner = TrackRunner()
    results: list[ExecutionResult] = []

    try:
        from tqdm import tqdm
        progress = tqdm(
            total=len(scenarios) * args.runs,
            desc="Running",
            ncols=100,
        )
    except ImportError:
        progress = None

    success_count = 0
    total_count = 0

    # ClearML live logger (for real-time scalar updates)
    clearml_logger = None
    if clearml_task:
        from clearml import Logger
        clearml_logger = Logger.current_logger()

    # Per-axis live tracking
    from collections import Counter, defaultdict
    live_info_stats = defaultdict(lambda: {"success": 0, "total": 0})
    live_action_stats = defaultdict(lambda: {"success": 0, "total": 0})

    # Running means for efficiency cumulative_mean series (updated per scenario)
    _eff_run = {"latency": 0.0, "tokens": 0.0, "tc": 0.0}

    # Tool-call protocol compliance tracking. The agent is told about a fixed
    # set of tools via the JSON schema, but models sometimes invent names
    # (e.g. `find_longest_audio_clip`, `match_grade`). Those hallucinated
    # calls are still recorded on the ExecutionResult; the runner just
    # skips execution and logs a WARNING. Here we count how often that
    # happens so ClearML shows a live unknown-tool rate curve and the
    # post-run summary reports a final percentage + top offenders.
    from nlebench.tools.executor import TOOL_HANDLERS as _TOOL_HANDLERS
    KNOWN_TOOL_NAMES = frozenset(_TOOL_HANDLERS.keys())
    _tool_total = 0
    _tool_unknown = 0
    _unknown_tool_names: Counter = Counter()

    # Create output directory and results file early for streaming writes
    import json as _json
    from datetime import datetime as _dt
    _output_dir = args.output / f"{_dt.now().strftime('%Y-%m-%d_%H-%M-%S')}_{model.replace('/', '_')}"
    _output_dir.mkdir(parents=True, exist_ok=True)
    _results_file = _output_dir / "results.jsonl"
    _results_fh = open(_results_file, "w", encoding="utf-8")

    semaphore = asyncio.Semaphore(args.concurrency)
    lock = asyncio.Lock()

    async def _run_one(scenario, run_number):
        nonlocal success_count, total_count, _tool_total, _tool_unknown
        async with semaphore:
            try:
                result = await runner.run_scenario(
                    scenario=scenario,
                    agent=provider,
                    track=args.track,
                    run_number=run_number,
                    timeout_seconds=args.timeout,
                )
            except Exception as e:
                async with lock:
                    total_count += 1
                    if progress:
                        progress.update(1)
                print(f"Error in {scenario.id}: {e}")
                return

            async with lock:
                results.append(result)
                _results_fh.write(_json.dumps(result.to_dict(), ensure_ascii=False) + "\n")
                _results_fh.flush()

                if result.success:
                    success_count += 1
                total_count += 1

                # Live ClearML updates
                if clearml_logger and total_count % 5 == 0:
                    tsr = success_count / total_count * 100
                    clearml_logger.report_scalar("02_Live/sr", "overall", value=tsr, iteration=total_count)

                if clearml_logger:
                    _lat_s = result.latency_ms / 1000.0
                    _tok_total = result.input_tokens + result.output_tokens
                    _tc = len(result.tool_calls or [])
                    clearml_logger.report_scalar("06_Efficiency/latency_s", "per_scenario", value=_lat_s, iteration=total_count)
                    clearml_logger.report_scalar("06_Efficiency/tokens_total", "per_scenario", value=_tok_total, iteration=total_count)
                    clearml_logger.report_scalar("06_Efficiency/tool_calls", "per_scenario", value=_tc, iteration=total_count)
                    _eff_run["latency"] += (_lat_s    - _eff_run["latency"]) / total_count
                    _eff_run["tokens"]  += (_tok_total - _eff_run["tokens"])  / total_count
                    _eff_run["tc"]      += (_tc        - _eff_run["tc"])      / total_count
                    clearml_logger.report_scalar("06_Efficiency/latency_s", "cumulative_mean", value=round(_eff_run["latency"], 2), iteration=total_count)
                    clearml_logger.report_scalar("06_Efficiency/tokens_total", "cumulative_mean", value=round(_eff_run["tokens"], 1), iteration=total_count)
                    clearml_logger.report_scalar("06_Efficiency/tool_calls", "cumulative_mean", value=round(_eff_run["tc"], 2), iteration=total_count)

                t = scenario.effective_taxonomy
                info = t.information or "calibration"
                action = t.action or "calibration"
                live_info_stats[info]["total"] += 1
                live_action_stats[action]["total"] += 1
                if result.success:
                    live_info_stats[info]["success"] += 1
                    live_action_stats[action]["success"] += 1

                for _tc_obj in result.tool_calls or []:
                    _tool_total += 1
                    _tc_name = getattr(_tc_obj, "name", None) or (
                        _tc_obj.get("name") if isinstance(_tc_obj, dict) else None
                    )
                    if _tc_name and _tc_name not in KNOWN_TOOL_NAMES:
                        _tool_unknown += 1
                        _unknown_tool_names[_tc_name] += 1

                if clearml_logger and total_count % 20 == 0 and _tool_total > 0:
                    clearml_logger.report_scalar("07_Diagnostics/unknown_tool_rate", "percent", value=_tool_unknown / _tool_total * 100, iteration=total_count)

                if clearml_logger and total_count % 20 == 0:
                    for chart_suffix, stats in [("information", live_info_stats), ("action", live_action_stats)]:
                        for level, s in stats.items():
                            if s["total"] > 0:
                                level_tsr = s["success"] / s["total"] * 100
                                clearml_logger.report_scalar(f"02_Live/{chart_suffix}", level, value=level_tsr, iteration=total_count)

                    import numpy as np
                    _infos = ["explicit", "state", "context", "diagnosis"]
                    _actions = ["atomic", "compound", "dependent", "cumulative"]
                    _live_cell = defaultdict(lambda: {"success": 0, "total": 0})
                    for _r in results:
                        _sid = _r.scenario_id if hasattr(_r, "scenario_id") else _r.get("scenario_id", "")
                        _parts = _sid.split("-")
                        if len(_parts) >= 5:
                            _info_map = {"EX": "explicit", "ST": "state", "CX": "context", "DI": "diagnosis"}
                            _act_map = {"AT": "atomic", "CO": "compound", "DE": "dependent", "CU": "cumulative"}
                            _ci = _info_map.get(_parts[2])
                            _ca = _act_map.get(_parts[3])
                            if _ci and _ca:
                                _live_cell[f"{_ci}/{_ca}"]["total"] += 1
                                _succ = _r.success if hasattr(_r, "success") else _r.get("success", False)
                                if _succ:
                                    _live_cell[f"{_ci}/{_ca}"]["success"] += 1
                    _live_matrix = np.full((4, 4), 0.0)
                    for _i, _inf in enumerate(_infos):
                        for _j, _act in enumerate(_actions):
                            _s = _live_cell.get(f"{_inf}/{_act}", {"success": 0, "total": 0})
                            _live_matrix[_i][_j] = _s["success"] / _s["total"] * 100 if _s["total"] > 0 else 0
                    clearml_logger.report_confusion_matrix("02_Live/cell_heatmap", "SR (%)", matrix=_live_matrix, xlabels=_actions, ylabels=_infos, iteration=total_count)

                    _feas_types = ["feasible", "infeasible", "ambiguous"]
                    _behaviors = ["execute", "refuse", "clarify", "noop"]
                    _live_bpm = defaultdict(lambda: Counter())
                    for _r in results:
                        _v = _r.validation if hasattr(_r, "validation") else type("", (), _r.get("validation", {}))()
                        _feas = getattr(_v, "feasibility", None) or (_r.get("validation", {}).get("feasibility", "?"))
                        _beh = getattr(_v, "behavior", None) or (_r.get("validation", {}).get("behavior", "?"))
                        if _feas in _feas_types and _beh in _behaviors:
                            _live_bpm[_feas][_beh] += 1
                    _bpm_matrix = np.full((3, 4), 0.0)
                    for _i, _ft in enumerate(_feas_types):
                        _row_total = sum(_live_bpm[_ft].values())
                        if _row_total > 0:
                            for _j, _bh in enumerate(_behaviors):
                                _bpm_matrix[_i][_j] = _live_bpm[_ft][_bh] / _row_total * 100
                    clearml_logger.report_confusion_matrix("02_Live/behavioral_profile", "% within feasibility", matrix=_bpm_matrix, xlabels=_behaviors, ylabels=_feas_types, iteration=total_count)

                if progress:
                    sr = success_count / total_count * 100
                    progress.set_postfix_str(f"SR={sr:.0f}% ({success_count}/{total_count})")
                    progress.update(1)

    await asyncio.gather(*[
        _run_one(scenario, run_number)
        for scenario in scenarios
        for run_number in range(args.runs)
    ])

    if progress:
        progress.close()

    # Summary
    print()
    print("=" * 60)
    print("RESULTS SUMMARY")
    print("=" * 60)
    print(f"Total runs: {total_count}")
    print(f"Successful: {success_count}")
    print(f"SR: {success_count / total_count * 100:.1f}%")

    # ──────────────────────────────────────────────────────────────────
    # ClearML reporting
    #
    # Scalar titles use an "NN_Section/chart" convention so ClearML's
    # Scalars tab groups related charts into labeled sections. Ordering:
    #   01_Headline   — final SR and run counts
    #   02_Live       — (written inside the scenario loop above) live
    #                   curves by iteration
    #   03_SR         — final SR broken out by each taxonomy axis
    #   04_Cell       — v3 Information × Action heatmap is a confusion
    #                   matrix, not a scalar, so it goes to the Plots tab
    #   05_BPM        — feasibility × behavior distribution
    #   06_Efficiency — (written live above) latency / tokens / tool_calls
    #   07_Diagnostics — secondary metrics (TSR-only, CSR, Mean OVR)
    # ──────────────────────────────────────────────────────────────────
    if clearml_task:
        from clearml import Logger
        logger = Logger.current_logger()
        sr = success_count / total_count * 100 if total_count > 0 else 0

        # --- 01_Headline: overall SR and run counts ---
        logger.report_scalar("01_Headline/sr", "final", value=sr, iteration=0)
        logger.report_scalar("01_Headline/runs", "total", value=total_count, iteration=0)
        logger.report_scalar("01_Headline/runs", "successful", value=success_count, iteration=0)

        # --- 07_Diagnostics: secondary validator signals ---
        tsr_only_pass = sum(1 for r in results if r.validation.tsr)
        csr_pass = sum(1 for r in results if r.validation.csr)
        ovr_values = [r.validation.ovr for r in results if r.validation.ovr is not None]
        logger.report_scalar(
            "07_Diagnostics/tsr_only", "value",
            value=tsr_only_pass / total_count * 100 if total_count else 0, iteration=0,
        )
        logger.report_scalar(
            "07_Diagnostics/csr", "value",
            value=csr_pass / total_count * 100 if total_count else 0, iteration=0,
        )
        logger.report_scalar(
            "07_Diagnostics/mean_ovr", "value",
            value=sum(ovr_values) / len(ovr_values) if ovr_values else 0, iteration=0,
        )

        # Final unknown-tool rate (tool protocol compliance signal)
        _unknown_rate_pct = (_tool_unknown / _tool_total * 100) if _tool_total else 0.0
        logger.report_scalar(
            "07_Diagnostics/unknown_tool_rate", "final",
            value=_unknown_rate_pct, iteration=total_count,
        )
        logger.report_single_value(
            "unknown_tool_rate", value=round(_unknown_rate_pct, 2),
        )
        if _unknown_tool_names:
            import pandas as pd
            top_unknown = _unknown_tool_names.most_common(20)
            logger.report_table(
                "Unknown Tool Names", "Top hallucinated tool names",
                table_plot=pd.DataFrame(
                    [{"name": n, "count": c} for n, c in top_unknown],
                ),
            )

        # Load scenario metadata for taxonomy mapping
        from collections import defaultdict
        from nlebench.runner.scenario_loader import load_scenarios as _load_scenarios

        all_scenarios = _load_scenarios(
            scenarios_dir=args.scenarios_dir,
        )
        scenario_meta = {}
        for sc in all_scenarios:
            t = sc.effective_taxonomy
            item = {
                "scale": t.scale.value,
                "feasibility": t.feasibility.value,
                "information": t.information,
                "action": t.action,
            }
            scenario_meta[sc.id] = item
            if sc.legacy_id:
                scenario_meta[sc.legacy_id] = item

        # Per-axis stats
        scale_stats = defaultdict(lambda: {"success": 0, "total": 0})
        feas_stats = defaultdict(lambda: {"success": 0, "total": 0})
        info_stats = defaultdict(lambda: {"success": 0, "total": 0})
        action_stats = defaultdict(lambda: {"success": 0, "total": 0})
        v3_cell_stats = defaultdict(lambda: {"success": 0, "total": 0})

        for result in results:
            meta = scenario_meta.get(result.scenario_id, {})
            scale = meta.get("scale", "unknown")
            feas = meta.get("feasibility", "unknown")
            info = meta.get("information") or "calibration"
            action = meta.get("action") or "calibration"

            scale_stats[scale]["total"] += 1
            feas_stats[feas]["total"] += 1
            info_stats[info]["total"] += 1
            action_stats[action]["total"] += 1
            v3_cell_stats[f"{info}×{action}"]["total"] += 1

            if result.success:
                scale_stats[scale]["success"] += 1
                feas_stats[feas]["success"] += 1
                info_stats[info]["success"] += 1
                action_stats[action]["success"] += 1
                v3_cell_stats[f"{info}×{action}"]["success"] += 1

        # --- Single-value headline row in the ClearML Summary table ---
        logger.report_single_value("SR", value=round(sr, 1))
        for feas, s in feas_stats.items():
            if s["total"] > 0:
                val = s["success"] / s["total"] * 100
                logger.report_single_value(f"SR-{feas}", value=round(val, 1))

        # --- 03_SR: SR by each taxonomy axis ---
        import pandas as pd
        import numpy as np

        for feas in ("feasible", "infeasible", "ambiguous"):
            s = feas_stats.get(feas)
            if s and s["total"] > 0:
                val = s["success"] / s["total"] * 100
                logger.report_scalar("03_SR/by_feasibility", feas, value=val, iteration=0)

        scale_rows = []
        for scale in ("L1", "L2", "L3"):
            s = scale_stats.get(scale)
            if s and s["total"] > 0:
                val = s["success"] / s["total"] * 100
                logger.report_scalar("03_SR/by_scale", scale, value=val, iteration=0)
                scale_rows.append({
                    "Scale": scale, "SR (%)": round(val, 1),
                    "n": s["total"], "pass": s["success"],
                })
        if scale_rows:
            logger.report_table(
                "Scale Results", "SR by Scale",
                table_plot=pd.DataFrame(scale_rows),
            )

        info_rows = []
        for info in ("explicit", "state", "context", "diagnosis"):
            s = info_stats.get(info)
            if s and s["total"] > 0:
                val = s["success"] / s["total"] * 100
                logger.report_scalar("03_SR/by_information", info, value=val, iteration=0)
                info_rows.append({
                    "Information": info, "SR (%)": round(val, 1),
                    "n": s["total"], "pass": s["success"],
                })
        if info_rows:
            logger.report_table(
                "v3 Information Results", "SR by Information Gap",
                table_plot=pd.DataFrame(info_rows),
            )

        action_rows = []
        for action in ("atomic", "compound", "dependent", "cumulative"):
            s = action_stats.get(action)
            if s and s["total"] > 0:
                val = s["success"] / s["total"] * 100
                logger.report_scalar("03_SR/by_action", action, value=val, iteration=0)
                action_rows.append({
                    "Action": action, "SR (%)": round(val, 1),
                    "n": s["total"], "pass": s["success"],
                })
        if action_rows:
            logger.report_table(
                "v3 Action Results", "SR by Action Structure",
                table_plot=pd.DataFrame(action_rows),
            )

        # --- 04_Cell: v3 Information × Action heatmap (confusion matrix
        #     goes to the Plots tab, not Scalars — but we emit the 16
        #     per-cell values as scalars too so they're sortable). ---
        infos = ["explicit", "state", "context", "diagnosis"]
        actions = ["atomic", "compound", "dependent", "cumulative"]
        v3_matrix = np.full((len(infos), len(actions)), 0.0)
        v3_table_rows = []
        for i, info in enumerate(infos):
            for j, action in enumerate(actions):
                key = f"{info}×{action}"
                s = v3_cell_stats.get(key)
                if s and s["total"] > 0:
                    val = round(s["success"] / s["total"] * 100, 1)
                    v3_matrix[i][j] = val
                    v3_table_rows.append({
                        "Cell": key, "SR (%)": val,
                        "n": s["total"], "pass": s["success"],
                    })
                    logger.report_scalar(
                        f"04_Cell/{info}", action, value=val, iteration=0,
                    )

        logger.report_confusion_matrix(
            "v3 Information x Action SR", "SR (%)",
            matrix=v3_matrix, xlabels=actions, ylabels=infos,
        )
        if v3_table_rows:
            logger.report_table(
                "v3 Cell Results", "SR by Information x Action",
                table_plot=pd.DataFrame(v3_table_rows),
            )

        # --- 05_BPM: Behavioral Profile Matrix (feasibility × behavior) ---
        behaviors = ["execute", "refuse", "clarify", "noop"]
        feas_types = ["feasible", "infeasible", "ambiguous"]
        bpm_counts = defaultdict(lambda: defaultdict(int))
        bpm_totals = defaultdict(int)
        for result in results:
            feas = scenario_meta.get(result.scenario_id, {}).get("feasibility", "unknown")
            behavior = result.validation.behavior or "noop"
            bpm_counts[feas][behavior] += 1
            bpm_totals[feas] += 1

        bpm_matrix = np.zeros((len(feas_types), len(behaviors)))
        bpm_rows = []
        for i, feas in enumerate(feas_types):
            total = bpm_totals.get(feas, 0)
            row = {"Feasibility": feas, "n": total}
            for j, beh in enumerate(behaviors):
                count = bpm_counts[feas].get(beh, 0)
                pct = (count / total * 100) if total > 0 else 0.0
                bpm_matrix[i][j] = round(pct, 1)
                row[beh] = f"{count} ({pct:.0f}%)"
                logger.report_scalar(f"05_BPM/{feas}", beh, value=pct, iteration=0)
            bpm_rows.append(row)

        logger.report_confusion_matrix(
            "Behavioral Profile Matrix", "% within feasibility",
            matrix=bpm_matrix, xlabels=behaviors, ylabels=feas_types,
        )
        logger.report_table(
            "Behavioral Profile", "Feasibility x Behavior",
            table_plot=pd.DataFrame(bpm_rows),
        )

        # --- Efficiency aggregates ---
        # A. Headline single values + C. group breakdowns + D. histograms.
        import statistics as _stats

        def _pct(values: list[float], p: float) -> float:
            if not values:
                return 0.0
            s = sorted(values)
            k = max(0, min(len(s) - 1, int(round((p / 100.0) * (len(s) - 1)))))
            return s[k]

        latencies = [r.latency_ms for r in results]
        in_tokens = [r.input_tokens for r in results]
        out_tokens = [r.output_tokens for r in results]
        total_tokens = [r.input_tokens + r.output_tokens for r in results]
        tool_call_counts = [len(r.tool_calls or []) for r in results]
        costs = [r.cost_usd for r in results]

        def _safe_mean(xs):
            return _stats.mean(xs) if xs else 0.0

        # A. Single-value headline metrics — keep the set small (~2 efficiency
        # headlines) so ClearML's flat Summary row stays readable. All detail
        # numbers live in the Efficiency Summary table below, grouped by
        # category.
        latency_s = [v / 1000.0 for v in latencies]
        logger.report_single_value("latency_s_mean", round(_safe_mean(latency_s), 2))
        logger.report_single_value("total_tokens_mean", round(_safe_mean(total_tokens), 0))

        # C. Group breakdowns — box plots (per-group distributions) rather
        # than scalar-at-iteration-0, which ClearML's time-series Scalars tab
        # renders poorly. Box plots live in the Plots tab and scale gracefully
        # from small n (show raw outliers) to large n (show proper quartiles).
        # Group by feasibility and by v3 information axis.
        feas_eff: dict[str, dict[str, list[float]]] = defaultdict(lambda: {"lat": [], "tok": [], "tc": []})
        info_eff: dict[str, dict[str, list[float]]] = defaultdict(lambda: {"lat": [], "tok": [], "tc": []})
        for r in results:
            meta = scenario_meta.get(r.scenario_id, {})
            feas = meta.get("feasibility", "unknown")
            info = meta.get("information") or "unknown"
            lat_s = r.latency_ms / 1000.0   # box plots + summary use seconds
            tok_total = r.input_tokens + r.output_tokens
            tc_count = len(r.tool_calls or [])
            feas_eff[feas]["lat"].append(lat_s)
            feas_eff[feas]["tok"].append(tok_total)
            feas_eff[feas]["tc"].append(tc_count)
            info_eff[info]["lat"].append(lat_s)
            info_eff[info]["tok"].append(tok_total)
            info_eff[info]["tc"].append(tc_count)

        try:
            import plotly.graph_objects as go

            def _box_plot(
                title: str,
                group_data: dict[str, dict[str, list[float]]],
                key: str,
                y_label: str,
                group_order: list[str],
            ) -> None:
                fig = go.Figure()
                any_data = False
                for grp in group_order:
                    buckets = group_data.get(grp)
                    if not buckets or not buckets[key]:
                        continue
                    fig.add_trace(go.Box(
                        y=buckets[key],
                        name=grp,
                        boxpoints="all",       # show every sample as a dot
                        jitter=0.3,
                        pointpos=-1.8,
                        boxmean=True,          # overlay mean marker
                    ))
                    any_data = True
                if not any_data:
                    return
                fig.update_layout(
                    title=title,
                    yaxis_title=y_label,
                    xaxis_title="group",
                    showlegend=False,
                    margin=dict(l=50, r=20, t=50, b=40),
                )
                logger.report_plotly(title=title, series="box", figure=fig)

            # 3 metrics × 2 breakdowns = 6 box plots
            feas_order = ["feasible", "infeasible", "ambiguous"]
            info_order = ["explicit", "state", "context", "diagnosis"]
            _box_plot("Latency by Feasibility",   feas_eff, "lat", "latency (s)", feas_order)
            _box_plot("Latency by Information",   info_eff, "lat", "latency (s)", info_order)
            _box_plot("Tokens by Feasibility",    feas_eff, "tok", "total tokens", feas_order)
            _box_plot("Tokens by Information",    info_eff, "tok", "total tokens", info_order)
            _box_plot("ToolCalls by Feasibility", feas_eff, "tc",  "tool calls",   feas_order)
            _box_plot("ToolCalls by Information", info_eff, "tc",  "tool calls",   info_order)
        except ImportError:
            # plotly not installed — box plots are a nice-to-have, skip quietly
            pass

        # D. Histograms (distribution shape). Each metric gets its OWN chart
        # because their value ranges differ by orders of magnitude (latency
        # in seconds, tokens in thousands, tool calls in single digits) and
        # overlaying them on one x-axis makes the smaller-range metrics
        # invisible.
        if latency_s:
            logger.report_histogram(
                title="Latency Distribution", series="latency_s",
                values=np.array(latency_s), iteration=0, xaxis="latency (s)",
            )
        if total_tokens:
            logger.report_histogram(
                title="Tokens Distribution", series="total_tokens",
                values=np.array(total_tokens), iteration=0, xaxis="tokens",
            )
        if tool_call_counts:
            logger.report_histogram(
                title="Tool Calls Distribution", series="tool_calls_per_scenario",
                values=np.array(tool_call_counts), iteration=0, xaxis="tool calls",
            )

        # Efficiency summary table — three-column grouped layout (Category /
        # Metric / Value) so rows are short and readable instead of one wide
        # row of 10+ columns. ClearML renders each table as its own card.
        eff_rows = [
            {"Category": "Latency",    "Metric": "mean (s)",        "Value": round(_safe_mean(latency_s), 2)},
            {"Category": "Latency",    "Metric": "p50 (s)",         "Value": round(_pct(latency_s, 50), 2)},
            {"Category": "Latency",    "Metric": "p95 (s)",         "Value": round(_pct(latency_s, 95), 2)},
            {"Category": "Latency",    "Metric": "total (s)",       "Value": round(sum(latency_s), 2)},
            {"Category": "Tokens",     "Metric": "input mean",      "Value": round(_safe_mean(in_tokens), 0)},
            {"Category": "Tokens",     "Metric": "output mean",     "Value": round(_safe_mean(out_tokens), 0)},
            {"Category": "Tokens",     "Metric": "total mean",      "Value": round(_safe_mean(total_tokens), 0)},
            {"Category": "Tokens",     "Metric": "total sum",       "Value": int(sum(total_tokens))},
            {"Category": "Tool calls", "Metric": "mean per run",    "Value": round(_safe_mean(tool_call_counts), 2)},
            {"Category": "Tool calls", "Metric": "total",           "Value": int(sum(tool_call_counts))},
        ]
        if any(c > 0 for c in costs):
            eff_rows.append(
                {"Category": "Cost", "Metric": "total (USD)", "Value": round(sum(costs), 4)}
            )
        eff_table = pd.DataFrame(eff_rows)
        logger.report_table("Efficiency Summary", "Latency / Tokens / Tool calls",
                            table_plot=eff_table)
        # (cumulative_mean series are reported live inside the scenario loop
        # alongside the per_scenario series, so both show up on the same chart.)

    # Close streaming results file
    _results_fh.close()

    # Save results
    import json
    from datetime import datetime

    output_dir = _output_dir
    results_file = _results_file

    # Save config
    config.to_yaml(output_dir / "config.yaml")

    # Save summary
    summary = {
        "model": model,
        "provider": args.provider,
        "track": args.track,
        "total_runs": total_count,
        "successful_runs": success_count,
        "sr": round(success_count / total_count, 4) if total_count > 0 else 0,
        "timestamp": datetime.now().isoformat(),
    }
    with open(output_dir / "summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print(f"\nResults saved to: {output_dir}")

    # Upload artifacts to ClearML
    if clearml_task:
        clearml_task.upload_artifact("results", artifact_object=str(results_file))
        clearml_task.upload_artifact("summary", artifact_object=summary)
        clearml_task.close()

    return results


def main():
    args = parse_args()

    # Configure logging
    level = logging.DEBUG if args.verbose else logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Run benchmark
    try:
        asyncio.run(run_benchmark(args))
    except KeyboardInterrupt:
        print("\nInterrupted")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
