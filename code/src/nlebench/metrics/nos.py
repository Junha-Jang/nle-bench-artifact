"""
NLEBench Overall Score (NOS) Calculation

Combines all metrics into a single overall score (0-100).
"""

from typing import Optional

from nlebench.models import ExecutionResult, MetricResults, Scenario
from nlebench.metrics.correctness import (
    calculate_tsr,
    calculate_tsr_by_level,
)
from nlebench.metrics.reliability import (
    calculate_csr,
    calculate_ovr,
    calculate_reliability_score,
)
from nlebench.metrics.efficiency import (
    calculate_p50,
    calculate_p95,
    calculate_cpr,
    calculate_efficiency_score,
)
from nlebench.metrics.calibration import calculate_rar, calculate_cqs


def calculate_nos(
    results: list[ExecutionResult],
    scenarios: Optional[dict[str, Scenario]] = None,
    latency_threshold_ms: float = 30000.0,
    cost_threshold_usd: float = 1.0,
) -> float:
    """
    Calculate NLEBench Overall Score (NOS).

    Formula:
    NOS = (TSR*0.40 + RAR*0.15 + CQS*0.10 + CSR*0.15 + (1-OVR)*0.05
           + Efficiency*0.15) * 100

    Where:
    - TSR = Task Success Rate (feasible scenarios only)
    - RAR = Refusal Accuracy Rate (infeasible scenarios)
    - CQS = Clarification Quality Score (ambiguous scenarios)
    - CSR = Compile Success Rate
    - OVR = Over-edit Violation Rate
    - Efficiency = weighted(latency_score, cost_score)

    If no scenarios dict is provided, falls back to legacy formula
    (TSR*0.50 + Reliability*0.35 + Efficiency*0.15) for backwards compatibility.

    Args:
        results: List of execution results
        scenarios: Optional dict mapping scenario_id -> Scenario
        latency_threshold_ms: Maximum acceptable latency for scoring
        cost_threshold_usd: Maximum acceptable cost per request

    Returns:
        NOS score between 0 and 100
    """
    if not results:
        return 0.0

    # Efficiency (15% weight in both formulas)
    efficiency = calculate_efficiency_score(
        results,
        latency_threshold_ms=latency_threshold_ms,
        cost_threshold_usd=cost_threshold_usd,
    )

    if scenarios is not None:
        # New formula with calibration metrics
        tsr = calculate_tsr(results)
        rar = calculate_rar(results, scenarios)
        cqs = calculate_cqs(results, scenarios)
        csr = calculate_csr(results)
        ovr = calculate_ovr(results)

        nos = (
            tsr * 0.40
            + rar * 0.15
            + cqs * 0.10
            + csr * 0.15
            + (1.0 - ovr) * 0.05
            + efficiency * 0.15
        ) * 100
    else:
        # Legacy formula (backwards compatible)
        correctness = calculate_tsr(results)
        reliability = calculate_reliability_score(results)

        nos = (
            correctness * 0.50 +
            reliability * 0.35 +
            efficiency * 0.15
        ) * 100

    return round(nos, 2)


def calculate_all_metrics(
    results: list[ExecutionResult],
    scenarios: Optional[dict[str, Scenario]] = None,
) -> MetricResults:
    """
    Calculate all metrics from execution results.

    Args:
        results: List of execution results
        scenarios: Optional dict mapping scenario_id -> Scenario
                   (needed for RAR/CQS calibration metrics)

    Returns:
        MetricResults with all calculated metrics
    """
    if not results:
        return MetricResults()

    # Calibration metrics (default to 1.0 if no scenarios provided)
    rar = calculate_rar(results, scenarios) if scenarios else 1.0
    cqs = calculate_cqs(results, scenarios) if scenarios else 1.0

    # TSR by feasibility
    tsr_by_feasibility: dict[str, float] = {}
    if scenarios:
        for feas in ("feasible", "infeasible", "ambiguous"):
            feas_results = [
                r for r in results
                if r.scenario_id in scenarios
                and scenarios[r.scenario_id].feasibility == feas
            ]
            if feas_results:
                tsr_by_feasibility[feas] = sum(
                    1 for r in feas_results if r.success
                ) / len(feas_results)

    return MetricResults(
        # Correctness
        tsr=calculate_tsr(results),

        # Calibration
        rar=rar,
        cqs=cqs,

        # Reliability
        csr=calculate_csr(results),
        ovr=calculate_ovr(results),

        # Efficiency
        p50_latency_ms=calculate_p50(results),
        p95_latency_ms=calculate_p95(results),
        cpr=calculate_cpr(results),

        # Overall
        nos=calculate_nos(results, scenarios=scenarios),

        # Counts
        total_runs=len(results),
        successful_runs=sum(1 for r in results if r.success),

        # Breakdown
        tsr_by_level=calculate_tsr_by_level(results),
        tsr_by_feasibility=tsr_by_feasibility,
    )


def format_metrics_report(metrics: MetricResults) -> str:
    """
    Format metrics as a human-readable report.

    Args:
        metrics: MetricResults to format

    Returns:
        Formatted string report
    """
    lines = [
        "=" * 60,
        "NLEBench Results Summary",
        "=" * 60,
        "",
        f"Overall Score (NOS): {metrics.nos:.2f} / 100",
        "",
        "-" * 60,
        "Correctness",
        "-" * 60,
        f"  TSR (Task Success Rate): {metrics.tsr:.2%}",
        "",
    ]

    # Add TSR by level
    if metrics.tsr_by_level:
        lines.append("  TSR by Level:")
        for level, tsr in sorted(metrics.tsr_by_level.items()):
            lines.append(f"    {level}: {tsr:.2%}")
        lines.append("")

    # Add TSR by feasibility
    if metrics.tsr_by_feasibility:
        lines.append("  TSR by Feasibility:")
        for feas, tsr in sorted(metrics.tsr_by_feasibility.items()):
            lines.append(f"    {feas}: {tsr:.2%}")
        lines.append("")

    lines.extend([
        "-" * 60,
        "Calibration",
        "-" * 60,
        f"  RAR (Refusal Accuracy Rate): {metrics.rar:.2%}",
        f"  CQS (Clarification Quality Score): {metrics.cqs:.2%}",
        "",
        "-" * 60,
        "Reliability",
        "-" * 60,
        f"  CSR (Compile Success Rate): {metrics.csr:.2%}",
        f"  OVR (Over-edit Violation Rate): {metrics.ovr:.2%}",
        "",
        "-" * 60,
        "Efficiency",
        "-" * 60,
        f"  P50 Latency: {metrics.p50_latency_ms:.0f} ms",
        f"  P95 Latency: {metrics.p95_latency_ms:.0f} ms",
        f"  Cost Per Request: ${metrics.cpr:.4f}",
        "",
        "-" * 60,
        "Summary",
        "-" * 60,
        f"  Total Runs: {metrics.total_runs}",
        f"  Successful Runs: {metrics.successful_runs}",
        f"  Success Rate: {metrics.successful_runs / metrics.total_runs:.2%}" if metrics.total_runs > 0 else "  Success Rate: N/A",
        "",
        "=" * 60,
    ])

    return "\n".join(lines)
