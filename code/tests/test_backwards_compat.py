"""Scenario corpus smoke tests for the submitted v3.1 YAML release."""

import pytest
from pathlib import Path

import yaml

from nlebench.models import Scenario


SCENARIOS_DIR = Path(__file__).parent.parent / "src" / "nlebench" / "dataset" / "scenarios_v3_1"


def _get_all_yaml_files() -> list[Path]:
    """Collect all YAML files from all scenario directories."""
    return sorted(SCENARIOS_DIR.rglob("*.yaml"))


class TestAllScenariosLoad:
    """Test that all scenario YAML files load without errors."""

    @pytest.fixture
    def all_yaml_files(self):
        return _get_all_yaml_files()

    def test_scenarios_dir_exists(self):
        assert SCENARIOS_DIR.exists(), f"Scenarios directory not found: {SCENARIOS_DIR}"

    def test_800_scenarios(self, all_yaml_files):
        """v3.1 ships exactly 800 scenarios."""
        assert len(all_yaml_files) == 800

    def test_split_counts(self, all_yaml_files):
        assert sum(1 for p in all_yaml_files if "/dev/" in p.as_posix()) == 200
        assert sum(1 for p in all_yaml_files if "/test/" in p.as_posix()) == 600

    def test_all_yamls_parse(self, all_yaml_files):
        """Every YAML file should parse without error."""
        for yaml_file in all_yaml_files:
            with open(yaml_file, encoding="utf-8") as f:
                data = yaml.safe_load(f)
            assert data is not None, f"Empty YAML: {yaml_file}"

    def test_all_yamls_load_as_scenario(self, all_yaml_files):
        """Every YAML file should load as a valid Scenario object."""
        errors = []
        for yaml_file in all_yaml_files:
            try:
                with open(yaml_file, encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                scenario = Scenario.from_dict(data)
                assert scenario.id, f"No id in {yaml_file}"
                assert scenario.user_messages, f"No user_messages in {yaml_file}"
            except Exception as e:
                errors.append(f"{yaml_file.name}: {e}")

        assert not errors, f"Failed to load scenarios:\n" + "\n".join(errors)


class TestLegacyScenariosDefaults:
    """Test that legacy scenarios (L1-L4) get correct default values for new fields."""

    @pytest.fixture
    def legacy_scenarios(self):
        """Load all L1-L4/L4a/L4b scenarios."""
        scenarios = []
        for level in ["L1", "L2", "L3", "L4", "L4a", "L4b"]:
            level_dir = SCENARIOS_DIR / level
            if level_dir.exists():
                for yaml_file in level_dir.glob("*.yaml"):
                    with open(yaml_file, encoding="utf-8") as f:
                        data = yaml.safe_load(f)
                    scenarios.append(Scenario.from_dict(data))
        return scenarios

    def test_feasibility_defaults_to_feasible(self, legacy_scenarios):
        for s in legacy_scenarios:
            assert s.feasibility == "feasible", (
                f"{s.id}: feasibility should default to 'feasible', got '{s.feasibility}'"
            )

    def test_scope_defaults_to_sequence(self, legacy_scenarios):
        for s in legacy_scenarios:
            assert s.scope == "sequence", (
                f"{s.id}: scope should default to 'sequence', got '{s.scope}'"
            )

    def test_no_required_capability(self, legacy_scenarios):
        for s in legacy_scenarios:
            assert s.required_capability is None, (
                f"{s.id}: required_capability should be None"
            )


class TestNewScenariosStructure:
    """Test that v3.1 infeasible/ambiguous scenarios have correct structure."""

    @pytest.fixture
    def infeasible_scenarios(self):
        infeasible_dir = SCENARIOS_DIR / "infeasible"
        if not infeasible_dir.exists():
            pytest.skip("No infeasible directory")
        scenarios = []
        for yaml_file in infeasible_dir.rglob("*.yaml"):
            with open(yaml_file, encoding="utf-8") as f:
                data = yaml.safe_load(f)
            scenarios.append(Scenario.from_dict(data))
        return scenarios

    @pytest.fixture
    def ambiguous_scenarios(self):
        ambiguous_dir = SCENARIOS_DIR / "ambiguous"
        if not ambiguous_dir.exists():
            pytest.skip("No ambiguous directory")
        scenarios = []
        for yaml_file in ambiguous_dir.rglob("*.yaml"):
            with open(yaml_file, encoding="utf-8") as f:
                data = yaml.safe_load(f)
            scenarios.append(Scenario.from_dict(data))
        return scenarios

    def test_80_infeasible_scenarios(self, infeasible_scenarios):
        assert len(infeasible_scenarios) == 80

    def test_infeasible_have_v3_taxonomy(self, infeasible_scenarios):
        for s in infeasible_scenarios:
            assert s.feasibility == "infeasible"
            assert s.taxonomy is not None
            assert s.taxonomy.information in ("explicit", "state", "context", "diagnosis")
            assert s.taxonomy.action is None

    def test_80_ambiguous_scenarios(self, ambiguous_scenarios):
        assert len(ambiguous_scenarios) == 80

    def test_ambiguous_have_v3_taxonomy(self, ambiguous_scenarios):
        for s in ambiguous_scenarios:
            assert s.feasibility == "ambiguous"
            assert s.taxonomy is not None
            assert s.taxonomy.information in ("explicit", "state", "context", "diagnosis")
            assert s.taxonomy.action is None
