"""
NLEBench Visualization

Generates charts and visualizations for benchmark results.
"""

import json
from pathlib import Path
from typing import Optional

from nlebench.models import MetricResults
from nlebench.metrics.error_taxonomy import ErrorAnalysis


def generate_ascii_bar(value: float, max_width: int = 40, char: str = "█") -> str:
    """Generate ASCII bar for value (0-1)."""
    filled = int(value * max_width)
    return char * filled + "░" * (max_width - filled)


def generate_tsr_by_level_chart(by_level: dict[str, MetricResults]) -> str:
    """Generate ASCII chart for TSR by level."""
    lines = [
        "",
        "TSR by Level",
        "─" * 60,
    ]

    for level in ["L1", "L2", "L3", "L4"]:
        if level in by_level:
            tsr = by_level[level].tsr
            bar = generate_ascii_bar(tsr)
            lines.append(f"  {level}: {bar} {tsr:.1%}")

    lines.append("")
    return "\n".join(lines)


def generate_metrics_radar_ascii(metrics: MetricResults) -> str:
    """Generate ASCII radar-like display of metrics."""
    lines = [
        "",
        "Metrics Overview",
        "-" * 60,
        "",
        f"  Correctness:",
        f"    TSR: {generate_ascii_bar(metrics.tsr, 30)} {metrics.tsr:.1%}",
        "",
        f"  Calibration:",
        f"    RAR: {generate_ascii_bar(metrics.rar, 30)} {metrics.rar:.1%}",
        f"    CQS: {generate_ascii_bar(metrics.cqs, 30)} {metrics.cqs:.1%}",
        "",
        f"  Reliability:",
        f"    CSR: {generate_ascii_bar(metrics.csr, 30)} {metrics.csr:.1%}",
        f"    OVR: {generate_ascii_bar(1-metrics.ovr, 30)} {1-metrics.ovr:.1%} (inverted)",
        "",
        f"  Efficiency:",
        f"    P50: {metrics.p50_latency_ms:.0f}ms",
        f"    P95: {metrics.p95_latency_ms:.0f}ms",
        f"    CPR: ${metrics.cpr:.4f}",
        "",
    ]
    return "\n".join(lines)


def generate_failure_breakdown_ascii(failure_analysis: dict) -> str:
    """Generate ASCII chart for failure breakdown."""
    lines = [
        "",
        "Failure Breakdown",
        "─" * 60,
        f"  Total Failures: {failure_analysis['total_failures']}",
        f"  Failure Rate: {failure_analysis['failure_rate']:.1%}",
        "",
        "  By Level:",
    ]

    for level, data in sorted(failure_analysis.get("failures_by_level", {}).items()):
        rate = data["rate"]
        bar = generate_ascii_bar(rate, 20, "▓")
        lines.append(f"    {level}: {bar} {rate:.1%} ({data['count']} failures)")

    constraint_failures = failure_analysis.get("constraint_failures", {})
    if constraint_failures:
        lines.append("")
        lines.append("  Top Failed Constraints:")
        for constraint, count in sorted(
            constraint_failures.items(),
            key=lambda x: x[1],
            reverse=True
        )[:5]:
            lines.append(f"    • {constraint}: {count}")

    lines.append("")
    return "\n".join(lines)


def generate_error_taxonomy_chart(error_analysis: ErrorAnalysis) -> str:
    """Generate ASCII stacked bar chart for E1-E5 error distribution by level."""
    lines = [
        "",
        "Error Taxonomy (E1-E5)",
        "─" * 60,
    ]

    if error_analysis.total_errors == 0:
        lines.append("  No errors to analyze.")
        lines.append("")
        return "\n".join(lines)

    # Overall distribution
    cats = ["E1", "E2", "E3", "E4", "E5"]
    cat_chars = {"E1": "1", "E2": "2", "E3": "3", "E4": "4", "E5": "5"}
    cat_labels = {
        "E1": "Parameter", "E2": "Target", "E3": "Operation",
        "E4": "Omission", "E5": "Side Effect",
    }

    lines.append("  Overall:")
    total = error_analysis.total_errors
    bar_width = 40
    bar = ""
    for cat in cats:
        count = error_analysis.by_category.get(cat, 0)
        width = int(count / total * bar_width) if total > 0 else 0
        bar += cat_chars[cat] * width
    bar = bar.ljust(bar_width, "░")
    lines.append(f"    [{bar}] (n={total})")

    for cat in cats:
        count = error_analysis.by_category.get(cat, 0)
        if count > 0:
            pct = count / total * 100
            lines.append(f"    {cat_chars[cat]}={cat}: {cat_labels[cat]} ({count}, {pct:.0f}%)")

    # By level
    if error_analysis.by_level:
        lines.append("")
        lines.append("  By Level:")
        for level in sorted(error_analysis.by_level.keys()):
            level_data = error_analysis.by_level[level]
            level_total = sum(level_data.get(c, 0) for c in cats)
            if level_total == 0:
                continue
            bar = ""
            for cat in cats:
                count = level_data.get(cat, 0)
                width = int(count / level_total * bar_width) if level_total > 0 else 0
                bar += cat_chars[cat] * width
            bar = bar.ljust(bar_width, "░")
            lines.append(f"    {level}: [{bar}] (n={level_total})")

    lines.append("")
    return "\n".join(lines)


def generate_qualitative_examples(
    error_analysis: ErrorAnalysis,
    max_per_category: int = 3,
) -> str:
    """Generate representative failure examples per error category."""
    lines = [
        "",
        "Representative Failure Examples",
        "─" * 60,
    ]

    if not error_analysis.classifications:
        lines.append("  No failures to display.")
        lines.append("")
        return "\n".join(lines)

    cat_labels = {
        "E1": "E1 Parameter Error",
        "E2": "E2 Target Error",
        "E3": "E3 Operation Error",
        "E4": "E4 Omission Error",
        "E5": "E5 Side Effect",
        "E5a": "E5a Adjacent Modification",
        "E5b": "E5b Cross-track Contamination",
        "E5c": "E5c Global Corruption",
        "E5d": "E5d Reference Break",
    }

    # Group by category
    by_cat: dict[str, list] = {}
    for cls in error_analysis.classifications:
        key = cls.category.value
        if key not in by_cat:
            by_cat[key] = []
        by_cat[key].append(cls)

    for cat in ["E1", "E2", "E3", "E4", "E5", "E5a", "E5b", "E5c", "E5d"]:
        examples = by_cat.get(cat, [])
        if not examples:
            continue
        lines.append(f"  {cat_labels[cat]}:")
        for ex in examples[:max_per_category]:
            detail = f" — {ex.detail}" if ex.detail else ""
            lines.append(f"    • {ex.constraint_name}{detail}")
        if len(examples) > max_per_category:
            lines.append(f"    ... and {len(examples) - max_per_category} more")
        lines.append("")

    return "\n".join(lines)


def generate_full_report(
    metrics: MetricResults,
    by_level: dict[str, MetricResults],
    failure_analysis: dict,
    error_analysis: Optional[ErrorAnalysis] = None,
) -> str:
    """Generate full ASCII report."""
    lines = [
        "=" * 70,
        "                    NLEBench Results Report",
        "=" * 70,
        "",
        f"  NLEBench Overall Score (NOS): {metrics.nos:.2f} / 100",
        "",
        "=" * 70,
    ]

    lines.append(generate_metrics_radar_ascii(metrics))
    lines.append(generate_tsr_by_level_chart(by_level))
    lines.append(generate_failure_breakdown_ascii(failure_analysis))

    if error_analysis is not None:
        lines.append(generate_error_taxonomy_chart(error_analysis))
        lines.append(generate_qualitative_examples(error_analysis))

    lines.extend([
        "=" * 70,
        "                           Summary",
        "=" * 70,
        f"  Total Runs: {metrics.total_runs}",
        f"  Successful: {metrics.successful_runs}",
        f"  Success Rate: {metrics.successful_runs/metrics.total_runs:.1%}" if metrics.total_runs > 0 else "  Success Rate: N/A",
        f"  Total Cost: ${metrics.cpr * metrics.total_runs:.2f}",
        "=" * 70,
    ])

    return "\n".join(lines)


def save_json_report(
    output_path: Path,
    metrics: MetricResults,
    by_level: dict[str, MetricResults],
    by_category: dict[str, MetricResults],
    failure_analysis: dict,
    error_analysis: Optional[ErrorAnalysis] = None,
) -> None:
    """Save detailed JSON report."""
    report = {
        "overall": metrics.to_dict(),
        "by_level": {k: v.to_dict() for k, v in by_level.items()},
        "by_category": {k: v.to_dict() for k, v in by_category.items()},
        "failure_analysis": failure_analysis,
    }

    if error_analysis is not None:
        report["error_taxonomy"] = error_analysis.to_dict()

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)


def save_markdown_report(
    output_path: Path,
    metrics: MetricResults,
    by_level: dict[str, MetricResults],
    failure_analysis: dict,
    error_analysis: Optional[ErrorAnalysis] = None,
) -> None:
    """Save Markdown report."""
    lines = [
        "# NLEBench Results Report",
        "",
        f"**NLEBench Overall Score (NOS): {metrics.nos:.2f} / 100**",
        "",
        "## Overall Metrics",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| TSR (Task Success Rate) | {metrics.tsr:.2%} |",
        f"| RAR (Refusal Accuracy Rate) | {metrics.rar:.2%} |",
        f"| CQS (Clarification Quality Score) | {metrics.cqs:.2%} |",
        f"| CSR (Compile Success Rate) | {metrics.csr:.2%} |",
        f"| OVR (Over-edit Violation Rate) | {metrics.ovr:.2%} |",
        f"| P50 Latency | {metrics.p50_latency_ms:.0f}ms |",
        f"| P95 Latency | {metrics.p95_latency_ms:.0f}ms |",
        f"| Cost Per Request | ${metrics.cpr:.4f} |",
        "",
        "## Results by Level",
        "",
        "| Level | TSR | CSR | P95 | Runs |",
        "|-------|-----|-----|-----|------|",
    ]

    for level in ["L1", "L2", "L3", "L4"]:
        if level in by_level:
            m = by_level[level]
            lines.append(
                f"| {level} | {m.tsr:.2%} | {m.csr:.2%} | {m.p95_latency_ms:.0f}ms | {m.total_runs} |"
            )

    lines.extend([
        "",
        "## Failure Analysis",
        "",
        f"- Total Failures: {failure_analysis['total_failures']}",
        f"- Failure Rate: {failure_analysis['failure_rate']:.2%}",
        "",
    ])

    top_failures = failure_analysis.get("top_failing_scenarios", [])
    if top_failures:
        lines.append("### Top Failing Scenarios")
        lines.append("")
        for scenario_id, count in top_failures[:5]:
            lines.append(f"- `{scenario_id}`: {count} failures")
        lines.append("")

    if error_analysis is not None and error_analysis.total_errors > 0:
        lines.extend([
            "## Error Taxonomy (E1-E5)",
            "",
            "| Category | Count | % |",
            "|----------|-------|---|",
        ])
        cat_labels = {
            "E1": "Parameter Error",
            "E2": "Target Error",
            "E3": "Operation Error",
            "E4": "Omission Error",
            "E5": "Side Effect Error",
        }
        for cat in ["E1", "E2", "E3", "E4", "E5"]:
            count = error_analysis.by_category.get(cat, 0)
            pct = count / error_analysis.total_errors * 100 if error_analysis.total_errors > 0 else 0
            lines.append(f"| {cat}: {cat_labels[cat]} | {count} | {pct:.1f}% |")
        lines.append("")

    lines.extend([
        "---",
        "",
        "*Generated by NLEBench*",
    ])

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
