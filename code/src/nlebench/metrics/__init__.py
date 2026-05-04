"""
NLEBench Metrics

Metric calculation modules.
"""

from nlebench.metrics.correctness import calculate_tsr
from nlebench.metrics.reliability import (
    calculate_csr,
    calculate_ovr,
    calculate_ovr_entity_diff,
    validate_edit_project,
)
from nlebench.metrics.efficiency import calculate_p95, calculate_cpr
from nlebench.metrics.calibration import calculate_rar, calculate_cqs, calculate_cqs_single
from nlebench.metrics.nos import calculate_nos, calculate_all_metrics, format_metrics_report
from nlebench.metrics.error_taxonomy import analyze_errors, format_error_analysis

__all__ = [
    "calculate_tsr",
    "calculate_csr",
    "calculate_ovr",
    "calculate_ovr_entity_diff",
    "validate_edit_project",
    "calculate_cqs_single",
    "calculate_p95",
    "calculate_cpr",
    "calculate_rar",
    "calculate_cqs",
    "calculate_nos",
    "calculate_all_metrics",
    "format_metrics_report",
    "analyze_errors",
    "format_error_analysis",
]
