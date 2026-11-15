"""
NLEBench Error Taxonomy (E1-E5)

Automated classification of constraint failures into five error categories.

E1: Parameter Error  - Correct target & operation, wrong parameter value
E2: Target Error     - Wrong entity targeted
E3: Operation Error  - Wrong operation type applied
E4: Omission Error   - Required change was not made
E5: Side Effect Error - Unintended change to non-target entity
"""

from __future__ import annotations

import re
from enum import Enum
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from nlebench.models import ExecutionResult, Scenario


class ErrorCategory(str, Enum):
    """Error taxonomy categories."""

    E1_PARAMETER = "E1"  # Wrong value
    E2_TARGET = "E2"  # Wrong entity
    E3_OPERATION = "E3"  # Wrong action
    E4_OMISSION = "E4"  # Missing change
    E5_SIDE_EFFECT = "E5"  # Unintended change (generic)
    E5a_ADJACENT = "E5a"  # Adjacent entity modification (same track)
    E5b_CROSS_TRACK = "E5b"  # Cross-track contamination
    E5c_GLOBAL = "E5c"  # Global state corruption (project level)
    E5d_REFERENCE = "E5d"  # Reference/link break


@dataclass
class ErrorClassification:
    """Classification of a single constraint failure."""

    category: ErrorCategory
    constraint_name: str
    detail: str = ""


@dataclass
class ErrorAnalysis:
    """Aggregated error analysis for a set of results."""

    total_errors: int = 0
    by_category: dict[str, int] = field(default_factory=lambda: {
        "E1": 0, "E2": 0, "E3": 0, "E4": 0,
        "E5": 0, "E5a": 0, "E5b": 0, "E5c": 0, "E5d": 0,
    })
    by_level: dict[str, dict[str, int]] = field(default_factory=dict)
    classifications: list[ErrorClassification] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "total_errors": self.total_errors,
            "by_category": self.by_category,
            "by_level": self.by_level,
        }


def classify_constraint_failure(constraint_name: str) -> ErrorCategory:
    """
    Classify a single constraint failure into an error category.

    Heuristic rules based on constraint naming conventions:
    - "required:field.equals" with value mismatch -> E1 (parameter)
    - "required:field.exists" / "not_exists" -> E4 (omission) or E2 (target)
    - "required:field.count" -> E4 (omission, missing items)
    - "validity:*" -> E3 (operation error, structural issue)
    - "specified:*" with .equals -> E1 (parameter)
    - Contains "overlap" or OVR-related -> E5 (side effect)

    Args:
        constraint_name: Constraint identifier (e.g., "required:caption.text.equals")

    Returns:
        ErrorCategory classification
    """
    name_lower = constraint_name.lower()

    # Side effects with subcategories
    if "adjacent" in name_lower:
        return ErrorCategory.E5a_ADJACENT
    if "cross_track" in name_lower or "cross-track" in name_lower:
        return ErrorCategory.E5b_CROSS_TRACK
    if "global" in name_lower or "project" in name_lower:
        return ErrorCategory.E5c_GLOBAL
    if "reference" in name_lower or "link" in name_lower or "parent" in name_lower:
        return ErrorCategory.E5d_REFERENCE
    if "overlap" in name_lower or "side_effect" in name_lower:
        return ErrorCategory.E5_SIDE_EFFECT

    # Validity constraints -> operation error
    if name_lower.startswith("validity:"):
        return ErrorCategory.E3_OPERATION

    # Existence checks -> omission
    if ".exists" in name_lower or ".not_exists" in name_lower:
        return ErrorCategory.E4_OMISSION

    # Count constraints -> omission (missing items)
    if ".count" in name_lower or ".count_changed" in name_lower:
        return ErrorCategory.E4_OMISSION

    # Equality constraints -> parameter error (wrong value)
    if ".equals" in name_lower or ".pattern" in name_lower:
        return ErrorCategory.E1_PARAMETER

    # Range constraints (gte, lte, gt, lt) -> parameter error
    if any(op in name_lower for op in [".gte", ".lte", ".gt", ".lt"]):
        return ErrorCategory.E1_PARAMETER

    # Contains -> parameter error
    if ".contains" in name_lower:
        return ErrorCategory.E1_PARAMETER

    # Default: operation error
    return ErrorCategory.E3_OPERATION


def analyze_errors(
    results: list[ExecutionResult],
    scenarios: dict[str, Scenario] | None = None,
) -> ErrorAnalysis:
    """
    Analyze all constraint failures across results and classify them.

    Args:
        results: List of execution results
        scenarios: Optional scenario dict for level-based grouping

    Returns:
        ErrorAnalysis with category breakdown
    """
    analysis = ErrorAnalysis()

    for result in results:
        if result.validation.tsr:
            continue  # No errors

        for constraint_name in result.validation.failed_constraints:
            category = classify_constraint_failure(constraint_name)
            classification = ErrorClassification(
                category=category,
                constraint_name=constraint_name,
            )
            analysis.classifications.append(classification)
            analysis.total_errors += 1
            analysis.by_category[category.value] += 1

            # Group by level if scenarios provided
            if scenarios and result.scenario_id in scenarios:
                level = scenarios[result.scenario_id].level.value
                if level not in analysis.by_level:
                    analysis.by_level[level] = {
                        "E1": 0, "E2": 0, "E3": 0, "E4": 0,
                        "E5": 0, "E5a": 0, "E5b": 0, "E5c": 0, "E5d": 0,
                    }
                analysis.by_level[level][category.value] += 1

        # Check for side effects via OVR
        if result.validation.ovr > 0.0:
            classification = ErrorClassification(
                category=ErrorCategory.E5_SIDE_EFFECT,
                constraint_name="ovr:unintended_change",
                detail=f"OVR={result.validation.ovr:.3f}",
            )
            analysis.classifications.append(classification)
            analysis.total_errors += 1
            analysis.by_category["E5"] += 1

            if scenarios and result.scenario_id in scenarios:
                level = scenarios[result.scenario_id].level.value
                if level not in analysis.by_level:
                    analysis.by_level[level] = {
                        "E1": 0, "E2": 0, "E3": 0, "E4": 0,
                        "E5": 0, "E5a": 0, "E5b": 0, "E5c": 0, "E5d": 0,
                    }
                analysis.by_level[level]["E5"] += 1

    return analysis


def format_error_analysis(analysis: ErrorAnalysis) -> str:
    """Format error analysis as a human-readable report."""
    lines = [
        "",
        "Error Taxonomy Analysis (E1-E5)",
        "-" * 50,
        f"  Total Errors: {analysis.total_errors}",
        "",
    ]

    category_labels = {
        "E1": "Parameter Error (wrong value)",
        "E2": "Target Error (wrong entity)",
        "E3": "Operation Error (wrong action)",
        "E4": "Omission Error (missing change)",
        "E5": "Side Effect Error (unintended change)",
    }

    subcategory_labels = {
        "E5a": "Adjacent entity modification",
        "E5b": "Cross-track contamination",
        "E5c": "Global state corruption",
        "E5d": "Reference/link break",
    }

    for cat in ["E1", "E2", "E3", "E4", "E5"]:
        count = analysis.by_category[cat]
        pct = (count / analysis.total_errors * 100) if analysis.total_errors > 0 else 0
        lines.append(f"  {cat}: {count:>4} ({pct:>5.1f}%)  {category_labels[cat]}")

    # E5 subcategories
    e5_subs = {k: analysis.by_category[k] for k in ["E5a", "E5b", "E5c", "E5d"] if analysis.by_category[k] > 0}
    if e5_subs:
        for sub, count in e5_subs.items():
            pct = (count / analysis.total_errors * 100) if analysis.total_errors > 0 else 0
            lines.append(f"    {sub}: {count:>4} ({pct:>5.1f}%)  {subcategory_labels[sub]}")

    if analysis.by_level:
        lines.extend(["", "  By Level:"])
        all_cats = ["E1", "E2", "E3", "E4", "E5", "E5a", "E5b", "E5c", "E5d"]
        for level in sorted(analysis.by_level.keys()):
            level_counts = analysis.by_level[level]
            parts = [f"{cat}={level_counts[cat]}" for cat in all_cats if level_counts.get(cat, 0) > 0]
            lines.append(f"    {level}: {', '.join(parts)}")

    lines.append("")
    return "\n".join(lines)
