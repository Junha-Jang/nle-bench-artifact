"""
NLEBench Efficiency Metrics

Measures latency and cost performance.
"""

from typing import Optional

from nlebench.models import ExecutionResult


def calculate_p50(results: list[ExecutionResult]) -> float:
    """
    Calculate 50th percentile (median) latency in milliseconds.

    Args:
        results: List of execution results

    Returns:
        P50 latency in milliseconds
    """
    latencies = [r.latency_ms for r in results if r.latency_ms > 0]

    if not latencies:
        return 0.0

    sorted_latencies = sorted(latencies)
    mid = len(sorted_latencies) // 2

    if len(sorted_latencies) % 2 == 0:
        return (sorted_latencies[mid - 1] + sorted_latencies[mid]) / 2
    else:
        return sorted_latencies[mid]


def calculate_p95(results: list[ExecutionResult]) -> float:
    """
    Calculate 95th percentile latency in milliseconds.

    Args:
        results: List of execution results

    Returns:
        P95 latency in milliseconds
    """
    latencies = [r.latency_ms for r in results if r.latency_ms > 0]

    if not latencies:
        return 0.0

    sorted_latencies = sorted(latencies)
    idx = int(len(sorted_latencies) * 0.95)
    idx = min(idx, len(sorted_latencies) - 1)

    return sorted_latencies[idx]


def calculate_p99(results: list[ExecutionResult]) -> float:
    """
    Calculate 99th percentile latency in milliseconds.

    Args:
        results: List of execution results

    Returns:
        P99 latency in milliseconds
    """
    latencies = [r.latency_ms for r in results if r.latency_ms > 0]

    if not latencies:
        return 0.0

    sorted_latencies = sorted(latencies)
    idx = int(len(sorted_latencies) * 0.99)
    idx = min(idx, len(sorted_latencies) - 1)

    return sorted_latencies[idx]


def calculate_cpr(results: list[ExecutionResult]) -> float:
    """
    Calculate average Cost Per Request (CPR) in USD.

    Args:
        results: List of execution results

    Returns:
        Average cost per request in USD
    """
    if not results:
        return 0.0

    total_cost = sum(r.cost_usd for r in results)
    return total_cost / len(results)


def calculate_total_cost(results: list[ExecutionResult]) -> float:
    """
    Calculate total cost across all results.

    Args:
        results: List of execution results

    Returns:
        Total cost in USD
    """
    return sum(r.cost_usd for r in results)


def calculate_average_tokens(results: list[ExecutionResult]) -> dict[str, float]:
    """
    Calculate average token usage.

    Args:
        results: List of execution results

    Returns:
        Dictionary with average input, output, and total tokens
    """
    if not results:
        return {"input": 0.0, "output": 0.0, "total": 0.0}

    total_input = sum(r.input_tokens for r in results)
    total_output = sum(r.output_tokens for r in results)
    total_tokens = sum(r.token_usage for r in results)

    n = len(results)
    return {
        "input": total_input / n,
        "output": total_output / n,
        "total": total_tokens / n,
    }


def calculate_efficiency_score(
    results: list[ExecutionResult],
    latency_threshold_ms: float = 30000.0,  # 30 seconds
    cost_threshold_usd: float = 1.0,  # $1 per request
) -> float:
    """
    Calculate combined efficiency score.

    Normalized scores:
    - Latency: 1 - (P95 / threshold), capped at 0
    - Cost: 1 - (CPR / threshold), capped at 0

    Combined with equal weights.

    Args:
        results: List of execution results
        latency_threshold_ms: Maximum acceptable latency
        cost_threshold_usd: Maximum acceptable cost per request

    Returns:
        Efficiency score between 0.0 and 1.0
    """
    p95 = calculate_p95(results)
    cpr = calculate_cpr(results)

    latency_score = max(0.0, 1.0 - (p95 / latency_threshold_ms))
    cost_score = max(0.0, 1.0 - (cpr / cost_threshold_usd))

    return latency_score * 0.5 + cost_score * 0.5
