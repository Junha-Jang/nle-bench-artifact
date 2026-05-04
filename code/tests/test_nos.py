"""Tests for NOS (NLEBench Overall Score) calculation."""

import pytest

from nlebench.metrics.nos import calculate_nos, calculate_all_metrics
from nlebench.models import ExecutionResult, Scenario, ValidationResult


def _make_result(
    scenario_id: str = "L1_test",
    success: bool = True,
    tsr: bool = True,
    csr: bool = True,
    ovr: float = 0.0,
    latency_ms: float = 1000.0,
    cost_usd: float = 0.01,
    refusal_appropriate: bool | None = None,
    state_changed: bool | None = None,
    asked_clarification: bool | None = None,
) -> ExecutionResult:
    return ExecutionResult(
        scenario_id=scenario_id,
        run_number=0,
        success=success,
        validation=ValidationResult(
            tsr=tsr,
            csr=csr,
            ovr=ovr,
            refusal_appropriate=refusal_appropriate,
            state_changed=state_changed,
            asked_clarification=asked_clarification,
        ),
        latency_ms=latency_ms,
        cost_usd=cost_usd,
        input_tokens=100,
        output_tokens=50,
    )


def _make_scenario(id: str, feasibility: str = "feasible") -> Scenario:
    return Scenario(
        id=id,
        name="Test",
        level="L1",
        category="test",
        description="test",
        fixture="basic_sequence",
        user_messages=["test"],
        feasibility=feasibility,
    )


class TestCalculateNos:
    """Test NOS calculation."""

    def test_empty_results(self):
        assert calculate_nos([]) == 0.0

    def test_legacy_formula_without_scenarios(self):
        """Without scenarios dict, use legacy formula."""
        results = [_make_result()]
        nos = calculate_nos(results)
        assert nos > 0
        assert nos <= 100

    def test_new_formula_with_scenarios(self):
        """With scenarios dict, use new formula with RAR/CQS."""
        scenarios = {"L1_test": _make_scenario("L1_test")}
        results = [_make_result()]
        nos = calculate_nos(results, scenarios=scenarios)
        assert nos > 0
        assert nos <= 100

    def test_perfect_score_components(self):
        """All perfect: TSR=1, RAR=1, CQS=1, CSR=1, OVR=0."""
        scenarios = {"L1_test": _make_scenario("L1_test")}
        results = [_make_result(latency_ms=100.0, cost_usd=0.001)]

        nos = calculate_nos(
            results,
            scenarios=scenarios,
            latency_threshold_ms=30000.0,
            cost_threshold_usd=1.0,
        )

        # With perfect metrics and good efficiency, should be close to 100
        assert nos > 90


class TestCalculateAllMetrics:
    """Test calculate_all_metrics with scenarios."""

    def test_empty_results(self):
        mr = calculate_all_metrics([])
        assert mr.tsr == 0.0
        assert mr.nos == 0.0

    def test_with_scenarios(self):
        scenarios = {
            "L1_test": _make_scenario("L1_test"),
            "inf_1": _make_scenario("inf_1", "infeasible"),
        }
        results = [
            _make_result("L1_test"),
            _make_result(
                "inf_1",
                success=False,
                tsr=False,
                refusal_appropriate=True,
                state_changed=False,
            ),
        ]

        mr = calculate_all_metrics(results, scenarios)

        assert mr.rar == 1.0  # Perfect refusal
        assert mr.cqs == 1.0  # No ambiguous scenarios
        assert "feasible" in mr.tsr_by_feasibility or "infeasible" in mr.tsr_by_feasibility

    def test_without_scenarios_defaults(self):
        """Without scenarios, RAR/CQS default to 1.0."""
        results = [_make_result()]
        mr = calculate_all_metrics(results)

        assert mr.rar == 1.0
        assert mr.cqs == 1.0
