"""Tests for per-turn constraint validation (Phase 1)."""

import pytest

from nlebench.models import (
    Constraint,
    ConstraintType,
    Level,
    Operator,
    Scenario,
    Turn,
)
from nlebench.runner.validator import ConstraintValidator
from nlebench.dataset.cas_linter import lint_scenario


class TestTurnDataclass:
    """Test Turn dataclass serialization."""

    def test_to_dict_minimal(self):
        turn = Turn(user="자막 추가해줘")
        d = turn.to_dict()
        assert d == {"user": "자막 추가해줘"}

    def test_to_dict_full(self):
        turn = Turn(
            user="이전 자막과 같은 스타일로 추가해줘",
            fallback="자막 추가해줘",
            extract={"caption_id": r"caption_(\d+)"},
            constraints_after_turn=[
                Constraint(
                    type=ConstraintType.REQUIRED,
                    field="captions[-1].text",
                    operator=Operator.EXISTS,
                    value=True,
                )
            ],
        )
        d = turn.to_dict()
        assert d["user"] == "이전 자막과 같은 스타일로 추가해줘"
        assert d["fallback"] == "자막 추가해줘"
        assert d["extract"] == {"caption_id": r"caption_(\d+)"}
        assert len(d["constraints_after_turn"]) == 1

    def test_from_dict_roundtrip(self):
        original = Turn(
            user="텍스트 변경해줘",
            extract={"id": r"(\w+_\d+)"},
            constraints_after_turn=[
                Constraint(
                    type=ConstraintType.REQUIRED,
                    field="captions[0].text",
                    operator=Operator.EQUALS,
                    value="hello",
                )
            ],
        )
        d = original.to_dict()
        restored = Turn.from_dict(d)
        assert restored.user == original.user
        assert restored.extract == original.extract
        assert len(restored.constraints_after_turn) == 1
        assert restored.constraints_after_turn[0].operator == Operator.EQUALS


class TestScenarioWithTurns:
    """Test Scenario with turns format."""

    def test_from_dict_with_turns(self):
        data = {
            "id": "L4a_anaphoric_001",
            "name": "Anaphoric Ref",
            "level": "L4a",
            "category": "caption",
            "description": "Test anaphoric reference",
            "fixture": "basic_sequence",
            "turns": [
                {"user": "자막 추가해줘"},
                {
                    "user": "{caption_id}의 텍스트를 변경해줘",
                    "fallback": "자막 텍스트 변경해줘",
                    "extract": {"caption_id": r"caption_\d+"},
                },
            ],
            "constraints": {"required": [], "specified": [], "validity": []},
        }
        scenario = Scenario.from_dict(data)
        assert scenario.turns is not None
        assert len(scenario.turns) == 2
        assert scenario.user_messages == ["자막 추가해줘", "{caption_id}의 텍스트를 변경해줘"]

    def test_from_dict_without_turns_backward_compat(self):
        data = {
            "id": "L1_caption_001",
            "name": "Basic",
            "level": "L1",
            "category": "caption",
            "description": "Test",
            "fixture": "basic_sequence",
            "user_messages": ["자막 추가해줘"],
            "constraints": {"required": [], "specified": [], "validity": []},
        }
        scenario = Scenario.from_dict(data)
        assert scenario.turns is None
        assert scenario.user_messages == ["자막 추가해줘"]

    def test_to_dict_includes_turns(self):
        scenario = Scenario(
            id="L4b_refine_001",
            name="Refine",
            level=Level.L4b,
            category="caption",
            description="Test",
            fixture="basic_sequence",
            user_messages=["a", "b"],
            turns=[Turn(user="a"), Turn(user="b")],
        )
        d = scenario.to_dict()
        assert "turns" in d
        assert len(d["turns"]) == 2


class TestPerTurnOperators:
    """Test the 4 new per-turn comparison operators."""

    def test_new_operator_values(self):
        assert Operator.UNCHANGED_FROM_PREVIOUS.value == "unchanged_from_previous"
        assert Operator.COUNT_INCREASED.value == "count_increased"
        assert Operator.GREATER_THAN_PREVIOUS.value == "greater_than_previous"
        assert Operator.LESS_THAN_PREVIOUS.value == "less_than_previous"


class TestCASLinterTurns:
    """Test CAS linter rules for turns."""

    def test_l4a_without_turns_warns(self):
        scenario = Scenario(
            id="L4a_test_001",
            name="Test",
            level=Level.L4a,
            category="caption",
            description="Test",
            fixture="basic_sequence",
            user_messages=["a", "b"],
            turns=None,
        )
        errors = lint_scenario(scenario)
        warnings = [e for e in errors if e.severity == "warning" and e.rule == "l4_missing_turns"]
        assert len(warnings) == 1
        assert "L4a" in warnings[0].message

    def test_l4b_without_turns_warns(self):
        scenario = Scenario(
            id="L4b_test_001",
            name="Test",
            level=Level.L4b,
            category="caption",
            description="Test",
            fixture="basic_sequence",
            user_messages=["a", "b"],
            turns=None,
        )
        errors = lint_scenario(scenario)
        warnings = [e for e in errors if e.severity == "warning" and e.rule == "l4_missing_turns"]
        assert len(warnings) == 1

    def test_empty_turn_user_errors(self):
        scenario = Scenario(
            id="L4a_test_001",
            name="Test",
            level=Level.L4a,
            category="caption",
            description="Test",
            fixture="basic_sequence",
            user_messages=["", "b"],
            turns=[Turn(user=""), Turn(user="b")],
        )
        errors = lint_scenario(scenario)
        err_rules = [e for e in errors if e.rule == "empty_turn_user"]
        assert len(err_rules) == 1
        assert "Turn 0" in err_rules[0].message

    def test_valid_turns_no_extra_errors(self):
        scenario = Scenario(
            id="L4a_test_001",
            name="Test",
            level=Level.L4a,
            category="caption",
            description="Test",
            fixture="basic_sequence",
            user_messages=["a", "b"],
            turns=[Turn(user="a"), Turn(user="b")],
            max_turns=3,
        )
        errors = lint_scenario(scenario)
        turn_errors = [e for e in errors if e.rule in ("l4_missing_turns", "empty_turn_user")]
        assert len(turn_errors) == 0
