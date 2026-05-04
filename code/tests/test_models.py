"""Tests for NLEBench models - Scenario, ValidationResult, MetricResults."""

import pytest

from nlebench.models import (
    Constraint,
    ConstraintType,
    Level,
    MetricResults,
    Operator,
    Scenario,
    ValidationResult,
)


class TestScenarioFromDict:
    """Test Scenario.from_dict() with new and legacy formats."""

    def test_full_new_format(self):
        """Test loading a scenario with all new fields."""
        data = {
            "id": "infeasible_vision_001",
            "name": "Filter by Red",
            "level": "L1",
            "category": "clip_editing",
            "description": "Vision required",
            "fixture": "basic_sequence",
            "user_messages": ["빨간색 비율 10% 이상 프레임만 남겨줘"],
            "constraints": {"required": [], "specified": [], "validity": []},
            "scope": "sequence",
            "feasibility": "infeasible",
            "required_capability": "vision",
            "tags": ["infeasible", "vision"],
        }

        scenario = Scenario.from_dict(data)

        assert scenario.id == "infeasible_vision_001"
        assert scenario.scope == "sequence"
        assert scenario.feasibility == "infeasible"
        assert scenario.required_capability == "vision"
        assert scenario.ambiguity_type is None
        assert scenario.required_clarifications == []

    def test_ambiguous_format(self):
        """Test loading an ambiguous scenario."""
        data = {
            "id": "ambiguous_missing_param_001",
            "name": "Add Caption Without Details",
            "level": "L1",
            "category": "caption_editing",
            "description": "Missing params",
            "fixture": "basic_sequence",
            "user_messages": ["자막 추가해줘"],
            "constraints": {"required": [], "specified": [], "validity": []},
            "feasibility": "ambiguous",
            "ambiguity_type": "missing_required_params",
            "required_clarifications": ["text_content", "time_range"],
            "optional_clarifications": ["caption_style"],
        }

        scenario = Scenario.from_dict(data)

        assert scenario.feasibility == "ambiguous"
        assert scenario.ambiguity_type == "missing_required_params"
        assert scenario.required_clarifications == ["text_content", "time_range"]
        assert scenario.optional_clarifications == ["caption_style"]

    def test_backwards_compatible_legacy_format(self):
        """Test that legacy YAML without new fields loads fine."""
        data = {
            "id": "L1_caption_001",
            "name": "Add Basic Caption",
            "level": "L1",
            "category": "caption_editing",
            "description": "Basic caption",
            "fixture": "basic_sequence",
            "user_messages": ["자막 추가해줘"],
            "constraints": {
                "required": [
                    {
                        "type": "required",
                        "field": "captions",
                        "operator": "exists",
                        "value": True,
                    }
                ],
                "specified": [],
                "validity": [],
            },
            "tags": ["caption"],
        }

        scenario = Scenario.from_dict(data)

        # New fields should have defaults
        assert scenario.scope == "sequence"
        assert scenario.feasibility == "feasible"
        assert scenario.required_capability is None
        assert scenario.ambiguity_type is None
        assert scenario.required_clarifications == []
        assert scenario.optional_clarifications == []

        # Original fields intact
        assert scenario.id == "L1_caption_001"
        assert len(scenario.required_constraints) == 1

    def test_to_dict_roundtrip(self):
        """Test Scenario -> dict -> Scenario roundtrip."""
        original = Scenario(
            id="test_001",
            name="Test Scenario",
            level=Level.L2,
            category="clip_editing",
            description="Test",
            fixture="basic_sequence",
            user_messages=["테스트"],
            scope="project",
            feasibility="ambiguous",
            ambiguity_type="vague_intent",
            required_clarifications=["target", "criteria"],
        )

        data = original.to_dict()
        restored = Scenario.from_dict(data)

        assert restored.id == original.id
        assert restored.scope == original.scope
        assert restored.feasibility == original.feasibility
        assert restored.ambiguity_type == original.ambiguity_type
        assert restored.required_clarifications == original.required_clarifications


class TestLevel:
    """Test Level enum including L4a/L4b."""

    def test_l4_sublevel_values(self):
        assert Level.L4a.value == "L4a"
        assert Level.L4b.value == "L4b"

    def test_base_level(self):
        assert Level.L1.base_level == "L1"
        assert Level.L4.base_level == "L4"
        assert Level.L4a.base_level == "L4"
        assert Level.L4b.base_level == "L4"

    def test_l4a_scenario_from_dict(self):
        data = {
            "id": "L4a_anaphoric_001",
            "name": "Anaphoric Reference",
            "level": "L4a",
            "category": "caption",
            "description": "test",
            "fixture": "basic_sequence",
            "user_messages": ["이전 자막과 같은 스타일로 추가해줘", "그거 좀 더 크게"],
            "constraints": {"required": [], "specified": [], "validity": []},
            "max_turns": 3,
        }
        scenario = Scenario.from_dict(data)
        assert scenario.level == Level.L4a
        assert scenario.level.base_level == "L4"
        assert len(scenario.user_messages) == 2


class TestValidationResult:
    """Test ValidationResult with calibration fields."""

    def test_calibration_fields_default_none(self):
        """Test that calibration fields default to None."""
        vr = ValidationResult(tsr=True, csr=True, ovr=0.0)

        assert vr.refusal_appropriate is None
        assert vr.state_changed is None
        assert vr.asked_clarification is None

    def test_calibration_fields_set(self):
        """Test setting calibration fields."""
        vr = ValidationResult(
            tsr=True,
            csr=True,
            ovr=0.0,
            refusal_appropriate=True,
            state_changed=False,
        )

        assert vr.refusal_appropriate is True
        assert vr.state_changed is False
        assert vr.asked_clarification is None


class TestMetricResults:
    """Test MetricResults with new calibration fields."""

    def test_calibration_defaults(self):
        """Test RAR/CQS default to 0.0."""
        mr = MetricResults()

        assert mr.rar == 0.0
        assert mr.cqs == 0.0
        assert mr.tsr_by_feasibility == {}

    def test_to_dict_includes_calibration(self):
        """Test that to_dict includes calibration metrics."""
        mr = MetricResults(rar=0.85, cqs=0.72, tsr_by_feasibility={"feasible": 0.9})
        d = mr.to_dict()

        assert d["rar"] == 0.85
        assert d["cqs"] == 0.72
        assert d["tsr_by_feasibility"] == {"feasible": 0.9}
