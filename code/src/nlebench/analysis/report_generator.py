"""
NLEBench Report Generator

Generates comprehensive reports from benchmark results.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from nlebench.models import ExecutionResult, MetricResults
from nlebench.analysis.aggregator import MetricAggregator
from nlebench.analysis.visualization import (
    generate_full_report,
    save_json_report,
    save_markdown_report,
)
from nlebench.metrics.error_taxonomy import ErrorAnalysis, analyze_errors


class ReportGenerator:
    """
    Generates reports from NLEBench execution results.

    Supports multiple output formats:
    - Console (ASCII)
    - JSON
    - Markdown
    """

    def __init__(self, results: list[ExecutionResult]):
        self.results = results
        self.aggregator = MetricAggregator(results)
        self._overall: Optional[MetricResults] = None
        self._by_level: Optional[dict[str, MetricResults]] = None
        self._by_category: Optional[dict[str, MetricResults]] = None
        self._failure_analysis: Optional[dict] = None
        self._error_analysis: Optional[ErrorAnalysis] = None

    @property
    def overall(self) -> MetricResults:
        """Get overall metrics (cached)."""
        if self._overall is None:
            self._overall = self.aggregator.calculate_overall()
        return self._overall

    @property
    def by_level(self) -> dict[str, MetricResults]:
        """Get metrics by level (cached)."""
        if self._by_level is None:
            self._by_level = self.aggregator.calculate_by_level()
        return self._by_level

    @property
    def by_category(self) -> dict[str, MetricResults]:
        """Get metrics by category (cached)."""
        if self._by_category is None:
            self._by_category = self.aggregator.calculate_by_category()
        return self._by_category

    @property
    def failure_analysis(self) -> dict:
        """Get failure analysis (cached)."""
        if self._failure_analysis is None:
            self._failure_analysis = self.aggregator.get_failure_analysis()
        return self._failure_analysis

    @property
    def error_analysis(self) -> ErrorAnalysis:
        """Get error taxonomy analysis (cached)."""
        if self._error_analysis is None:
            self._error_analysis = analyze_errors(self.results)
        return self._error_analysis

    def generate_console_report(self) -> str:
        """Generate ASCII report for console output."""
        return generate_full_report(
            self.overall,
            self.by_level,
            self.failure_analysis,
            error_analysis=self.error_analysis,
        )

    def save_json_report(self, output_path: Path) -> None:
        """Save JSON report."""
        save_json_report(
            output_path,
            self.overall,
            self.by_level,
            self.by_category,
            self.failure_analysis,
            error_analysis=self.error_analysis,
        )

    def save_markdown_report(self, output_path: Path) -> None:
        """Save Markdown report."""
        save_markdown_report(
            output_path,
            self.overall,
            self.by_level,
            self.failure_analysis,
            error_analysis=self.error_analysis,
        )

    def save_all(self, output_dir: Path) -> None:
        """Save all report formats."""
        output_dir.mkdir(parents=True, exist_ok=True)

        # Console report
        console_report = self.generate_console_report()
        with open(output_dir / "report.txt", "w", encoding="utf-8") as f:
            f.write(console_report)

        # JSON report
        self.save_json_report(output_dir / "report.json")

        # Markdown report
        self.save_markdown_report(output_dir / "report.md")

        print(f"Reports saved to {output_dir}")

    @classmethod
    def from_results_file(cls, results_path: Path) -> "ReportGenerator":
        """Create ReportGenerator from saved results file."""
        results = []

        if results_path.suffix == ".jsonl":
            with open(results_path, encoding="utf-8") as f:
                for line in f:
                    data = json.loads(line)
                    results.append(cls._dict_to_result(data))
        else:
            with open(results_path, encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    results = [cls._dict_to_result(d) for d in data]
                else:
                    results = [cls._dict_to_result(data)]

        return cls(results)

    @staticmethod
    def _dict_to_result(data: dict) -> ExecutionResult:
        """Convert dictionary to ExecutionResult."""
        from nlebench.models import ValidationResult

        validation_data = data.get("validation", {})
        validation = ValidationResult(
            tsr=validation_data.get("tsr", False),
            csr=validation_data.get("csr", False),
            ovr=validation_data.get("ovr", 0.0),
            refusal_appropriate=validation_data.get("refusal_appropriate"),
            state_changed=validation_data.get("state_changed"),
            asked_clarification=validation_data.get("asked_clarification"),
            failed_constraints=validation_data.get("failed_constraints", []),
            error_message=validation_data.get("error_message"),
        )

        return ExecutionResult(
            scenario_id=data["scenario_id"],
            run_number=data["run_number"],
            success=data["success"],
            validation=validation,
            latency_ms=data.get("latency_ms", 0.0),
            token_usage=data.get("token_usage", 0),
            input_tokens=data.get("input_tokens", 0),
            output_tokens=data.get("output_tokens", 0),
            cost_usd=data.get("cost_usd", 0.0),
            tool_calls=data.get("tool_calls", []),
            agent_response=data.get("agent_response", ""),
            error_message=data.get("error_message"),
        )
