"""
NLEBench Metric Aggregator

Aggregates execution results into comprehensive metrics.
"""

from collections import defaultdict
from typing import Optional

from nlebench.models import (
    ExecutionResult,
    Level,
    MetricResults,
)
from nlebench.metrics import calculate_all_metrics


class MetricAggregator:
    """
    Aggregates execution results into metrics.

    Provides:
    - Overall metrics
    - Breakdown by level (L1-L4)
    - Breakdown by category
    - Failure analysis
    """

    def __init__(self, results: list[ExecutionResult]):
        self.results = results
        self._by_level: dict[str, list[ExecutionResult]] = self._group_by_level()
        self._by_category: dict[str, list[ExecutionResult]] = self._group_by_category()
        self._by_scenario: dict[str, list[ExecutionResult]] = self._group_by_scenario()

    def _group_by_level(self) -> dict[str, list[ExecutionResult]]:
        """Group results by complexity level (L4a/L4b grouped under both L4 and sub-level)."""
        groups: dict[str, list[ExecutionResult]] = defaultdict(list)
        for result in self.results:
            level = result.scenario_id.split("_")[0]  # L1, L2, L3, L4, L4a, L4b
            groups[level].append(result)
            # Also group L4a/L4b under aggregate L4
            if level in ("L4a", "L4b"):
                groups["L4"].append(result)
        return dict(groups)

    def _group_by_category(self) -> dict[str, list[ExecutionResult]]:
        """Group results by task category."""
        groups: dict[str, list[ExecutionResult]] = defaultdict(list)
        for result in self.results:
            parts = result.scenario_id.split("_")
            category = parts[1] if len(parts) > 1 else "unknown"
            groups[category].append(result)
        return dict(groups)

    def _group_by_scenario(self) -> dict[str, list[ExecutionResult]]:
        """Group results by scenario ID (for run variance analysis)."""
        groups: dict[str, list[ExecutionResult]] = defaultdict(list)
        for result in self.results:
            groups[result.scenario_id].append(result)
        return dict(groups)

    def calculate_overall(self) -> MetricResults:
        """Calculate overall metrics."""
        return calculate_all_metrics(self.results)

    def calculate_by_level(self) -> dict[str, MetricResults]:
        """Calculate metrics for each level."""
        return {
            level: calculate_all_metrics(results)
            for level, results in sorted(self._by_level.items())
        }

    def calculate_by_category(self) -> dict[str, MetricResults]:
        """Calculate metrics for each category."""
        return {
            category: calculate_all_metrics(results)
            for category, results in sorted(self._by_category.items())
        }

    def get_failure_analysis(self) -> dict:
        """
        Analyze failure patterns.

        Returns:
            Dictionary with failure statistics and patterns
        """
        failed_results = [r for r in self.results if not r.success]

        if not failed_results:
            return {
                "total_failures": 0,
                "failure_rate": 0.0,
                "failures_by_level": {},
                "constraint_failures": {},
                "patterns": [],
            }

        # Collect failed constraints
        constraint_failures: dict[str, int] = defaultdict(int)
        for result in failed_results:
            for constraint in result.validation.failed_constraints:
                constraint_failures[constraint] += 1

        # Group by level
        failures_by_level = {}
        for level, results in self._by_level.items():
            level_failures = [r for r in results if not r.success]
            failures_by_level[level] = {
                "count": len(level_failures),
                "rate": len(level_failures) / len(results) if results else 0,
            }

        # Top failing scenarios
        scenario_failure_counts = {}
        for scenario_id, results in self._by_scenario.items():
            failures = sum(1 for r in results if not r.success)
            if failures > 0:
                scenario_failure_counts[scenario_id] = failures

        top_failing = sorted(
            scenario_failure_counts.items(),
            key=lambda x: x[1],
            reverse=True
        )[:10]

        return {
            "total_failures": len(failed_results),
            "failure_rate": len(failed_results) / len(self.results) if self.results else 0,
            "failures_by_level": failures_by_level,
            "constraint_failures": dict(constraint_failures),
            "top_failing_scenarios": top_failing,
        }

    def get_variance_analysis(self) -> dict:
        """
        Analyze variance across multiple runs of the same scenario.

        Returns:
            Dictionary with variance statistics
        """
        variance_data = {}

        for scenario_id, results in self._by_scenario.items():
            if len(results) < 2:
                continue

            successes = [r.success for r in results]
            latencies = [r.latency_ms for r in results]

            # Calculate variance metrics
            success_rate = sum(successes) / len(successes)
            latency_mean = sum(latencies) / len(latencies)
            latency_variance = sum((l - latency_mean) ** 2 for l in latencies) / len(latencies)
            latency_std = latency_variance ** 0.5

            variance_data[scenario_id] = {
                "runs": len(results),
                "success_rate": success_rate,
                "latency_mean": latency_mean,
                "latency_std": latency_std,
                "consistent": success_rate in (0.0, 1.0),  # All pass or all fail
            }

        # Summary stats
        consistent_count = sum(1 for v in variance_data.values() if v["consistent"])
        inconsistent = [
            (sid, v) for sid, v in variance_data.items()
            if not v["consistent"]
        ]

        return {
            "total_scenarios": len(variance_data),
            "consistent_scenarios": consistent_count,
            "inconsistent_scenarios": len(inconsistent),
            "inconsistent_details": sorted(
                inconsistent,
                key=lambda x: x[1]["success_rate"]
            ),
        }

    def to_summary(self) -> dict:
        """Generate a comprehensive summary."""
        overall = self.calculate_overall()
        by_level = self.calculate_by_level()

        return {
            "overall": overall.to_dict(),
            "by_level": {k: v.to_dict() for k, v in by_level.items()},
            "failure_analysis": self.get_failure_analysis(),
            "variance_analysis": self.get_variance_analysis(),
        }
