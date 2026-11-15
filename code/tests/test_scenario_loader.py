"""Tests for the scenario loader (Phase 5)."""

import pytest
from pathlib import Path

from nlebench.models import Scenario, Taxonomy, Scale, CogType, Feasibility
from nlebench.runner.scenario_loader import (
    load_scenario,
    load_scenarios,
    validate_scenario_yaml,
    SCENARIOS_DIR,
)


# ── Tests: Scenario Loading ──

class TestLoadScenarios:
    def test_load_from_default_dir(self):
        """Load all scenarios from default directory."""
        scenarios = load_scenarios()
        assert len(scenarios) == 800

    def test_default_dir_is_v3_1_release(self):
        assert SCENARIOS_DIR.name == "scenarios_v3_1"
        assert SCENARIOS_DIR.exists()

    def test_v3_1_split_counts(self):
        scenarios = load_scenarios()
        by_split = {split: load_scenarios(split=split) for split in ("dev", "test")}

        assert len(scenarios) == 800
        assert len(by_split["dev"]) == 200
        assert len(by_split["test"]) == 600

    def test_load_l1_only(self):
        scenarios = load_scenarios(levels=["L1"], include_infeasible=False, include_ambiguous=False)
        assert len(scenarios) > 0
        for s in scenarios:
            assert s.level.value in ("L1",)

    def test_filter_by_category(self):
        scenarios = load_scenarios(categories=["clip_management"])
        for s in scenarios:
            assert s.category == "clip_management"

    def test_filter_by_scenario_id(self):
        # Load one scenario to get a valid ID
        all_scenarios = load_scenarios()
        if not all_scenarios:
            pytest.skip("No scenarios available")
        target_id = all_scenarios[0].id
        filtered = load_scenarios(scenario_ids=[target_id])
        assert len(filtered) == 1
        assert filtered[0].id == target_id


class TestLoadSingleScenario:
    def test_load_legacy_format(self):
        """Load a legacy-format YAML scenario."""
        yaml_dir = SCENARIOS_DIR / "L1"
        if not yaml_dir.exists():
            pytest.skip("L1 scenarios not found")
        yaml_files = sorted(yaml_dir.glob("*.yaml"))
        if not yaml_files:
            pytest.skip("No L1 YAML files")
        scenario = load_scenario(yaml_files[0])
        assert scenario.id
        assert len(scenario.user_messages) > 0


class TestNewFormatParsing:
    def test_parse_new_format(self):
        """Test parsing a scenario in the new unified format."""
        data = {
            "id": "NLB-042",
            "version": 2,
            "taxonomy": {
                "scale": "L2",
                "cognitive_type": "R",
                "feasibility": "feasible",
            },
            "split": "dev",
            "fixture": "complex_sequence",
            "turns": [
                {"instruction": "Lower the background music by 6dB"},
            ],
            "constraints": {
                "required": [
                    {"attribute_in_range": {
                        "entity": "$audio_1",
                        "field": "volume",
                        "min": -8.0,
                        "max": -4.0,
                    }},
                    {"unchanged_except": {
                        "changed": ["$audio_1"],
                    }},
                ],
                "specified": [],
                "tolerance_override": {"volume": 0.1},
            },
            "expected_changed_entities": ["$audio_1"],
            "expected_behavior": None,
            "gold_intent": {
                "target_entities": ["$audio_1"],
                "expected_ops": [{"tool": "update_audio", "params": {"field": "volume"}}],
            },
            "reference_solution": [
                {"tool": "get_entities", "params": {"type": "audio"}},
                {"tool": "update_audio", "params": {"entity_id": "$audio_1", "volume": -6.0}},
            ],
            "metadata": {"author": "test"},
        }

        scenario = Scenario.from_dict(data)
        assert scenario.id == "NLB-042"
        assert scenario.taxonomy is not None
        assert scenario.taxonomy.scale == Scale.L2
        assert scenario.taxonomy.cognitive_type == CogType.R
        assert scenario.taxonomy.feasibility == Feasibility.FEASIBLE
        assert scenario.split == "dev"
        assert scenario.version == 2
        assert len(scenario.user_messages) == 1
        assert scenario.user_messages[0] == "Lower the background music by 6dB"
        assert len(scenario.named_constraints_required) == 2
        assert scenario.tolerance_override == {"volume": 0.1}
        assert scenario.gold_intent is not None
        assert scenario.reference_solution is not None

    def test_parse_infeasible_format(self):
        data = {
            "id": "NLB-501",
            "taxonomy": {
                "scale": "L1",
                "cognitive_type": None,
                "feasibility": "infeasible",
            },
            "fixture": "simple_sequence",
            "turns": [
                {"instruction": "Use AI to remove the background from the video"},
            ],
            "constraints": {"required": [], "specified": []},
            "expected_behavior": "refuse",
            "required_capability": "content_understanding",
        }

        scenario = Scenario.from_dict(data)
        assert scenario.feasibility == "infeasible"
        assert scenario.expected_behavior == "refuse"
        assert scenario.taxonomy.feasibility == Feasibility.INFEASIBLE

    def test_parse_ambiguous_format(self):
        data = {
            "id": "NLB-601",
            "taxonomy": {
                "scale": "L1",
                "feasibility": "ambiguous",
            },
            "fixture": "simple_sequence",
            "turns": [
                {"instruction": "Add a caption"},
            ],
            "constraints": {"required": [], "specified": []},
            "expected_behavior": "clarify",
            "missing_parameters": ["text", "position", "duration"],
        }

        scenario = Scenario.from_dict(data)
        assert scenario.feasibility == "ambiguous"
        assert scenario.missing_parameters == ["text", "position", "duration"]

    def test_effective_taxonomy_from_legacy(self):
        """Legacy scenarios without taxonomy get effective_taxonomy from level."""
        data = {
            "id": "legacy_001",
            "level": "L2",
            "category": "test",
            "description": "test",
            "fixture": "simple_sequence",
            "user_messages": ["Do something"],
            "constraints": {"required": [], "specified": [], "validity": []},
        }
        scenario = Scenario.from_dict(data)
        assert scenario.taxonomy is None
        tax = scenario.effective_taxonomy
        assert tax.scale == Scale.L2
        assert tax.feasibility == Feasibility.FEASIBLE

    def test_fixture_with_patch(self):
        """Test fixture spec with base + patch."""
        data = {
            "id": "patch_001",
            "taxonomy": {"scale": "L1", "feasibility": "feasible"},
            "fixture": {
                "base": "simple_sequence",
                "patch": [
                    {"op": "set_attribute", "params": {"entity": "$clip_1", "field": "volume", "value": 0.0}},
                ],
            },
            "turns": [{"instruction": "Trim the first clip"}],
            "constraints": {"required": []},
        }
        scenario = Scenario.from_dict(data)
        assert isinstance(scenario.fixture, dict)
        assert scenario.fixture["base"] == "simple_sequence"


# ── Tests: Validation ──

class TestValidateScenarioYaml:
    def test_valid_new_format(self):
        data = {
            "id": "NLB-001",
            "taxonomy": {"scale": "L1", "cognitive_type": "B", "feasibility": "feasible"},
            "fixture": "single_clip",
            "turns": [{"instruction": "Trim clip to 3 seconds"}],
            "constraints": {
                "required": [
                    {"duration_equals": {"entity": "$clip_1", "value": 3.0}},
                ],
            },
        }
        errors = validate_scenario_yaml(data)
        assert errors == []

    def test_missing_id(self):
        data = {"turns": [{"instruction": "test"}]}
        errors = validate_scenario_yaml(data)
        assert any("id" in e for e in errors)

    def test_missing_turns_and_messages(self):
        data = {"id": "test"}
        errors = validate_scenario_yaml(data)
        assert any("turns" in e or "user_messages" in e for e in errors)

    def test_invalid_scale(self):
        data = {
            "id": "test",
            "taxonomy": {"scale": "L99"},
            "turns": [{"instruction": "test"}],
        }
        errors = validate_scenario_yaml(data)
        assert any("scale" in e for e in errors)

    def test_invalid_cognitive_type(self):
        data = {
            "id": "test",
            "taxonomy": {"scale": "L1", "cognitive_type": "X"},
            "turns": [{"instruction": "test"}],
        }
        errors = validate_scenario_yaml(data)
        assert any("cognitive_type" in e for e in errors)

    def test_invalid_attribute_changed_direction(self):
        data = {
            "id": "test",
            "taxonomy": {"scale": "L1", "feasibility": "feasible"},
            "turns": [{"instruction": "Raise the clip volume"}],
            "constraints": {
                "required": [
                    {
                        "attribute_changed": {
                            "entity": "audio_clip_1",
                            "field": "audio.volume",
                            "direction": "upward",
                        }
                    }
                ]
            },
        }
        errors = validate_scenario_yaml(data)
        assert any("attribute_changed.direction" in e for e in errors)

    def test_infeasible_legacy_behavior_slot_optional(self):
        data = {
            "id": "test",
            "taxonomy": {"scale": "L1", "feasibility": "infeasible"},
            "turns": [{"instruction": "test"}],
        }
        errors = validate_scenario_yaml(data)
        assert errors == []

    def test_ambiguous_legacy_missing_params_slot_optional(self):
        data = {
            "id": "test",
            "taxonomy": {"scale": "L1", "feasibility": "ambiguous"},
            "turns": [{"instruction": "test"}],
        }
        errors = validate_scenario_yaml(data)
        assert errors == []
