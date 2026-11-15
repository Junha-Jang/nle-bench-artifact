"""Tests for NLEBench calibration metrics (RAR, CQS)."""

import pytest

from nlebench.metrics.calibration import (
    calculate_clarification_coverage,
    calculate_cqs,
    calculate_rar,
    check_clarification,
    check_refusal,
    check_state_unchanged,
)
from nlebench.models import ExecutionResult, Scenario, ValidationResult


def _make_scenario(
    id: str,
    feasibility: str = "feasible",
    required_clarifications: list[str] | None = None,
) -> Scenario:
    """Helper to create a minimal Scenario."""
    return Scenario(
        id=id,
        name="Test",
        level="L1",
        category="test",
        description="test",
        fixture="basic_sequence",
        user_messages=["test"],
        feasibility=feasibility,
        required_clarifications=required_clarifications or [],
    )


def _make_result(
    scenario_id: str,
    refusal_appropriate: bool | None = None,
    state_changed: bool | None = None,
    asked_clarification: bool | None = None,
    agent_response: str = "",
) -> ExecutionResult:
    """Helper to create a minimal ExecutionResult."""
    return ExecutionResult(
        scenario_id=scenario_id,
        run_number=0,
        success=False,
        validation=ValidationResult(
            tsr=False,
            csr=True,
            ovr=0.0,
            refusal_appropriate=refusal_appropriate,
            state_changed=state_changed,
            asked_clarification=asked_clarification,
        ),
        agent_response=agent_response,
    )


class TestCheckRefusal:
    """Test refusal detection."""

    def test_korean_refusal(self):
        assert check_refusal("이 작업은 불가능합니다") is True
        assert check_refusal("지원하지 않는 기능입니다") is True
        assert check_refusal("처리할 수 없는 요청입니다") is True

    def test_english_refusal(self):
        assert check_refusal("I cannot perform this task") is True
        assert check_refusal("This is not possible with current capabilities") is True
        assert check_refusal("I'm unable to analyze visual content") is True

    def test_no_refusal(self):
        assert check_refusal("자막을 추가했습니다") is False
        assert check_refusal("Done! I added the caption") is False


class TestCheckStateUnchanged:
    """Test state comparison."""

    def test_unchanged(self):
        state = '{"project": "test"}'
        assert check_state_unchanged(state, state) is True

    def test_changed(self):
        assert check_state_unchanged('{"a": 1}', '{"a": 2}') is False


class TestCheckClarification:
    """Test clarification detection."""

    def test_question_mark(self):
        assert check_clarification("어떤 자막을 추가할까요?") is True
        assert check_clarification("Which clip do you want?") is True

    def test_korean_keywords(self):
        assert check_clarification("어떤 트랙에 추가할까요") is True
        assert check_clarification("정확히 몇 초부터 시작하나요") is True

    def test_english_keywords(self):
        assert check_clarification("Could you specify which track") is True
        assert check_clarification("please clarify the time range") is True

    def test_no_clarification(self):
        assert check_clarification("자막을 추가했습니다.") is False


class TestCalculateRar:
    """Test RAR (Refusal Accuracy Rate) calculation."""

    def test_all_appropriate_refusals(self):
        scenarios = {
            "inf_1": _make_scenario("inf_1", "infeasible"),
            "inf_2": _make_scenario("inf_2", "infeasible"),
        }
        results = [
            _make_result("inf_1", refusal_appropriate=True, state_changed=False),
            _make_result("inf_2", refusal_appropriate=True, state_changed=False),
        ]

        assert calculate_rar(results, scenarios) == 1.0

    def test_one_hallucination(self):
        scenarios = {
            "inf_1": _make_scenario("inf_1", "infeasible"),
            "inf_2": _make_scenario("inf_2", "infeasible"),
        }
        results = [
            _make_result("inf_1", refusal_appropriate=True, state_changed=False),
            _make_result("inf_2", refusal_appropriate=False, state_changed=True),
        ]

        assert calculate_rar(results, scenarios) == 0.5

    def test_no_infeasible_scenarios(self):
        scenarios = {"f_1": _make_scenario("f_1", "feasible")}
        results = [_make_result("f_1")]

        # Vacuously true
        assert calculate_rar(results, scenarios) == 1.0

    def test_refused_but_state_changed(self):
        """Agent refused verbally but still modified state - not appropriate."""
        scenarios = {"inf_1": _make_scenario("inf_1", "infeasible")}
        results = [
            _make_result("inf_1", refusal_appropriate=True, state_changed=True),
        ]

        assert calculate_rar(results, scenarios) == 0.0


class TestClarificationCoverage:
    """Test clarification coverage calculation."""

    def test_all_covered(self):
        response = "텍스트 내용은 무엇인가요? 시간 구간은 몇 초부터 몇 초까지인가요?"
        assert calculate_clarification_coverage(
            response, ["text_content", "time_range"]
        ) == 1.0

    def test_partial_coverage(self):
        response = "어떤 텍스트를 추가할까요?"
        coverage = calculate_clarification_coverage(
            response, ["text_content", "time_range"]
        )
        assert coverage == 0.5

    def test_empty_requirements(self):
        assert calculate_clarification_coverage("any response", []) == 1.0


class TestCalculateCqs:
    """Test CQS (Clarification Quality Score) calculation."""

    def test_perfect_clarification(self):
        scenarios = {
            "amb_1": _make_scenario(
                "amb_1", "ambiguous",
                required_clarifications=["text_content", "time_range"],
            ),
        }
        results = [
            _make_result(
                "amb_1",
                asked_clarification=True,
                state_changed=False,
                agent_response="어떤 텍스트를 추가할까요? 시간 구간은 몇 초부터?",
            ),
        ]

        cqs = calculate_cqs(results, scenarios)
        # F1-based: precision=2/2=1.0, recall=2/2=1.0, F1=1.0, no_change=1
        assert cqs == pytest.approx(1.0)

    def test_no_clarification_asked(self):
        scenarios = {
            "amb_1": _make_scenario("amb_1", "ambiguous", ["text_content"]),
        }
        results = [
            _make_result(
                "amb_1",
                asked_clarification=False,
                state_changed=True,
                agent_response="자막을 추가했습니다.",
            ),
        ]

        cqs = calculate_cqs(results, scenarios)
        # detection=0.0 -> gates entire score to 0.0
        assert cqs == pytest.approx(0.0)

    def test_clarification_but_state_changed(self):
        """Agent asked clarification but also modified state → CQS = 0 (F1-based)."""
        scenarios = {
            "amb_1": _make_scenario(
                "amb_1", "ambiguous",
                required_clarifications=["text_content"],
            ),
        }
        results = [
            _make_result(
                "amb_1",
                asked_clarification=True,
                state_changed=True,
                agent_response="어떤 텍스트를 추가할까요?",
            ),
        ]

        cqs = calculate_cqs(results, scenarios)
        # F1-based: state_changed=True → no_change gate → 0.0
        assert cqs == pytest.approx(0.0)

    def test_over_questioning_penalized(self):
        """Agent asks too many questions → precision drops, F1 drops."""
        scenarios = {
            "amb_1": _make_scenario(
                "amb_1", "ambiguous",
                required_clarifications=["text_content"],
            ),
        }
        results = [
            _make_result(
                "amb_1",
                asked_clarification=True,
                state_changed=False,
                # 3 questions but only 1 relevant (text_content)
                agent_response="어떤 텍스트를 추가할까요? 어디에 추가할까요? 크기는 어떻게 할까요?",
            ),
        ]

        cqs = calculate_cqs(results, scenarios)
        # F1-based: precision = 1/3, recall = 1/1 = 1.0
        # F1 = 2 * (1/3) * 1.0 / (1/3 + 1.0) = 0.5
        assert cqs == pytest.approx(0.5)

    def test_no_ambiguous_scenarios(self):
        scenarios = {"f_1": _make_scenario("f_1", "feasible")}
        results = [_make_result("f_1")]

        assert calculate_cqs(results, scenarios) == 1.0
