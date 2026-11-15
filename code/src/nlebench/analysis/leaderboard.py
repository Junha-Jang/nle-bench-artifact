"""
NLEBench Leaderboard

Compares multiple model runs and generates ranked leaderboard tables.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from nlebench.models import MetricResults


@dataclass
class LeaderboardEntry:
    """A single entry on the leaderboard."""

    model_name: str
    provider: str
    metrics: MetricResults
    results_dir: Optional[Path] = None
    timestamp: Optional[str] = None


class Leaderboard:
    """
    Maintains a ranked list of model benchmark results.

    Usage:
        lb = Leaderboard()
        lb.add_entry(LeaderboardEntry(model_name="claude-sonnet-4-6-2026-02-17", ...))
        lb.add_from_results_dir(Path("results/2026-02-01"))
        print(lb.to_markdown_table())
    """

    def __init__(self) -> None:
        self.entries: list[LeaderboardEntry] = []

    def add_entry(self, entry: LeaderboardEntry) -> None:
        """Add a leaderboard entry."""
        self.entries.append(entry)

    def add_from_results_dir(self, results_dir: Path) -> Optional[LeaderboardEntry]:
        """
        Load results from a directory and add as a leaderboard entry.

        Expects:
        - results_dir/config.yaml or config.json (for model name)
        - results_dir/summary.json (for metrics)
        """
        summary_path = results_dir / "summary.json"
        if not summary_path.exists():
            return None

        with open(summary_path, encoding="utf-8") as f:
            summary = json.load(f)

        metrics_data = summary.get("metrics", {})

        # Try to load config for model name
        model_name = "unknown"
        provider = "unknown"
        config_path = results_dir / "config.yaml"
        if config_path.exists():
            import yaml
            with open(config_path, encoding="utf-8") as f:
                config = yaml.safe_load(f)
            llm = config.get("llm", {})
            model_name = llm.get("model", "unknown")
            provider = llm.get("provider", "unknown")

        metrics = MetricResults(
            tsr=metrics_data.get("tsr", 0.0),
            rar=metrics_data.get("rar", 0.0),
            cqs=metrics_data.get("cqs", 0.0),
            csr=metrics_data.get("csr", 0.0),
            ovr=metrics_data.get("ovr", 0.0),
            p50_latency_ms=metrics_data.get("p50_latency_ms", 0.0),
            p95_latency_ms=metrics_data.get("p95_latency_ms", 0.0),
            cpr=metrics_data.get("cpr", 0.0),
            nos=metrics_data.get("nos", 0.0),
            total_runs=summary.get("total_runs", 0),
            successful_runs=summary.get("successful_runs", 0),
        )

        entry = LeaderboardEntry(
            model_name=model_name,
            provider=provider,
            metrics=metrics,
            results_dir=results_dir,
            timestamp=summary.get("timestamp"),
        )

        self.add_entry(entry)
        return entry

    def rank_by_nos(self) -> list[LeaderboardEntry]:
        """Return entries ranked by NOS score (descending)."""
        return sorted(self.entries, key=lambda e: e.metrics.nos, reverse=True)

    def to_markdown_table(self) -> str:
        """Generate a Markdown leaderboard table."""
        ranked = self.rank_by_nos()

        lines = [
            "# NLEBench Leaderboard",
            "",
            "| Rank | Model | NOS | TSR | RAR | CQS | CSR | P95 | CPR |",
            "|------|-------|-----|-----|-----|-----|-----|-----|-----|",
        ]

        for i, entry in enumerate(ranked, 1):
            m = entry.metrics
            lines.append(
                f"| {i} | {entry.model_name} | {m.nos:.1f} | "
                f"{m.tsr:.0%} | {m.rar:.0%} | {m.cqs:.0%} | "
                f"{m.csr:.0%} | {m.p95_latency_ms:.0f}ms | "
                f"${m.cpr:.3f} |"
            )

        return "\n".join(lines)

    def to_console_table(self) -> str:
        """Generate ASCII table for console output."""
        ranked = self.rank_by_nos()

        header = f"{'Rank':<5} {'Model':<30} {'NOS':>6} {'TSR':>6} {'RAR':>6} {'CQS':>6} {'CSR':>6}"
        sep = "-" * len(header)

        lines = [
            "",
            "NLEBench Leaderboard",
            sep,
            header,
            sep,
        ]

        for i, entry in enumerate(ranked, 1):
            m = entry.metrics
            lines.append(
                f"{i:<5} {entry.model_name:<30} {m.nos:>5.1f} "
                f"{m.tsr:>5.0%} {m.rar:>5.0%} {m.cqs:>5.0%} {m.csr:>5.0%}"
            )

        lines.append(sep)
        return "\n".join(lines)
