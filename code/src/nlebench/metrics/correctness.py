"""
NLEBench Correctness Metrics

Measures task completion accuracy.
"""

from typing import Optional

from nlebench.models import ExecutionResult, Level


def calculate_tsr(results: list[ExecutionResult]) -> float:
    """
    Calculate Task Success Rate (TSR).

    TSR = Number of successful tasks / Total number of tasks

    A task is successful if all constraints are satisfied.

    Args:
        results: List of execution results

    Returns:
        TSR as a float between 0.0 and 1.0
    """
    if not results:
        return 0.0

    successful = sum(1 for r in results if r.validation.tsr)
    return successful / len(results)


def calculate_tsr_by_level(results: list[ExecutionResult]) -> dict[str, float]:
    """
    Calculate TSR for each complexity level.

    Args:
        results: List of execution results

    Returns:
        Dictionary mapping level to TSR
    """
    tsr_by_level: dict[str, float] = {}

    for level in Level:
        level_results = [
            r for r in results
            if r.scenario_id.startswith(level.value)
        ]

        if level_results:
            tsr_by_level[level.value] = calculate_tsr(level_results)
        else:
            tsr_by_level[level.value] = 0.0

    return tsr_by_level


def calculate_tsr_by_category(
    results: list[ExecutionResult],
    category_map: Optional[dict[str, str]] = None,
) -> dict[str, float]:
    """
    Calculate TSR for each task category.

    Args:
        results: List of execution results
        category_map: Mapping from scenario_id to category name

    Returns:
        Dictionary mapping category to TSR
    """
    if category_map is None:
        # Default: extract category from scenario_id pattern
        # e.g., "L1_caption_001" -> "caption"
        category_map = {}
        for r in results:
            parts = r.scenario_id.split("_")
            if len(parts) >= 2:
                category_map[r.scenario_id] = parts[1]

    # Group by category
    categories: dict[str, list[ExecutionResult]] = {}
    for r in results:
        category = category_map.get(r.scenario_id, "unknown")
        if category not in categories:
            categories[category] = []
        categories[category].append(r)

    # Calculate TSR for each category
    tsr_by_category: dict[str, float] = {}
    for category, cat_results in categories.items():
        tsr_by_category[category] = calculate_tsr(cat_results)

    return tsr_by_category
