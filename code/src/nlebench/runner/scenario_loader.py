"""
NLEBench Scenario Loader.

Loads scenarios from YAML files using the unified schema.

Spec reference: scenario_design_spec.md §4
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import yaml

from nlebench.models import Scenario, Scale, Feasibility

logger = logging.getLogger(__name__)

# Default scenarios directory for the submitted v3.1 benchmark.
SCENARIOS_DIR = Path(__file__).parent.parent / "dataset" / "scenarios_v3_1"
ATTRIBUTE_CHANGED_DIRECTIONS = {"increase", "decrease", "any"}

# Legacy level directories (flat structure)
LEVEL_DIRS = ["L1", "L2", "L3", "L4", "L4a", "L4b"]

# Nested scenario structure: feasible/<information>/<action>/<split>/,
# infeasible/<information>/<split>/, ambiguous/<information>/<split>/.
V2_FEASIBLE_DIR = "feasible"
V2_CALIBRATION_DIRS = ["infeasible", "ambiguous"]

# Non-feasible scenario directories (legacy)
SPECIAL_DIRS = ["infeasible", "ambiguous"]


def _matches_scenario_ids(scenario: Scenario, scenario_ids: list[str]) -> bool:
    """Match either the public scenario id or the retained legacy id."""
    return scenario.id in scenario_ids or (
        scenario.legacy_id is not None and scenario.legacy_id in scenario_ids
    )


def load_scenario(path: Path) -> Scenario:
    """Load a single scenario from a YAML file."""
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return Scenario.from_dict(data)


def load_scenarios(
    scenarios_dir: Optional[Path] = None,
    *,
    levels: Optional[list[str]] = None,
    categories: Optional[list[str]] = None,
    scenario_ids: Optional[list[str]] = None,
    feasibilities: Optional[list[str]] = None,
    scales: Optional[list[str]] = None,
    split: Optional[str] = None,
    include_infeasible: bool = True,
    include_ambiguous: bool = True,
) -> list[Scenario]:
    """
    Load scenarios from YAML files with filtering.

    Args:
        scenarios_dir: Root directory containing either the v3.1 nested
            directories or the legacy L1/, L2/, L3/ layout.
        levels: Filter by level directories (e.g., ["L1", "L2"]).
        categories: Filter by scenario category.
        scenario_ids: Filter by specific scenario IDs.
        feasibilities: Filter by feasibility (e.g., ["feasible", "infeasible"]).
        scales: Filter by Scale enum (e.g., ["L1", "L2"]).
        split: Filter by split ("dev" or "test").
        include_infeasible: Whether to scan infeasible/ directory.
        include_ambiguous: Whether to scan ambiguous/ directory.

    Returns:
        List of Scenario objects.
    """
    if scenarios_dir is None:
        scenarios_dir = SCENARIOS_DIR

    scenarios: list[Scenario] = []
    scan_dirs: list[str] = []

    # Detect nested structure (has feasible/ subdirectory).
    is_nested = (scenarios_dir / V2_FEASIBLE_DIR).is_dir()

    if is_nested:
        scan_dirs.append(V2_FEASIBLE_DIR)
        for cal_dir in V2_CALIBRATION_DIRS:
            if cal_dir == "infeasible" and include_infeasible:
                scan_dirs.append(cal_dir)
            elif cal_dir == "ambiguous" and include_ambiguous:
                scan_dirs.append(cal_dir)
    else:
        # Legacy structure: L1/, L2/, L3/, infeasible/, ambiguous/
        if levels:
            scan_dirs.extend(levels)
        else:
            scan_dirs.extend(LEVEL_DIRS)
        if include_infeasible:
            scan_dirs.append("infeasible")
        if include_ambiguous:
            scan_dirs.append("ambiguous")

    for dir_name in scan_dirs:
        dir_path = scenarios_dir / dir_name
        if not dir_path.exists():
            continue

        # Support both flat (L1/*.yaml) and nested (feasible/L1/B/*.yaml) structures
        for yaml_file in sorted(dir_path.rglob("*.yaml")):
            try:
                scenario = load_scenario(yaml_file)
            except Exception as e:
                logger.error(f"Failed to load {yaml_file}: {e}")
                continue

            # Apply filters
            if categories and scenario.category not in categories:
                continue
            if scenario_ids and not _matches_scenario_ids(scenario, scenario_ids):
                continue
            if feasibilities and scenario.feasibility not in feasibilities:
                continue

            # Scale filter (from explicit scales param or legacy levels param in nested mode)
            effective_scales = scales
            if not effective_scales and levels and is_nested:
                # In nested mode, translate legacy levels filter to scales.
                effective_scales = [lv for lv in levels if lv in ("L1", "L2", "L3")]
            if effective_scales:
                effective_scale = scenario.effective_taxonomy.scale.value
                if effective_scale not in effective_scales:
                    continue
            if split and scenario.split != split:
                continue

            scenarios.append(scenario)

    return scenarios


def validate_scenario_yaml(data: dict) -> list[str]:
    """
    Validate a scenario YAML dict against the unified schema.

    Returns list of validation errors (empty = valid).
    """
    errors: list[str] = []

    # Required fields
    if "id" not in data:
        errors.append("Missing required field: id")

    # Must have either turns or user_messages
    if "turns" not in data and "user_messages" not in data:
        errors.append("Must have either 'turns' or 'user_messages'")

    # Validate taxonomy if present
    taxonomy = data.get("taxonomy")
    if taxonomy:
        scale = taxonomy.get("scale")
        if scale and scale not in ("L1", "L2", "L3", "L4", "L4a", "L4b"):
            errors.append(f"Invalid taxonomy.scale: {scale}")

        cog = taxonomy.get("cognitive_type")
        if cog and cog not in ("B", "A", "R", "E", "P", "I"):
            errors.append(f"Invalid taxonomy.cognitive_type: {cog}")

        feas = taxonomy.get("feasibility")
        if feas and feas not in ("feasible", "infeasible", "ambiguous"):
            errors.append(f"Invalid taxonomy.feasibility: {feas}")

    # Validate constraints format
    constraints = data.get("constraints", {})
    for key in ("required", "specified", "required_named", "specified_named"):
        for c in constraints.get(key, []):
            if isinstance(c, dict):
                # Should be either legacy (has 'operator') or named (single key)
                if "operator" not in c and len(c) != 1:
                    errors.append(
                        f"Invalid constraint in {key}: must be legacy (with 'operator') "
                        f"or named (single key dict), got {list(c.keys())}"
                    )
                if "operator" not in c and "attribute_changed" in c:
                    params = c.get("attribute_changed") or {}
                    direction = params.get("direction")
                    if direction is not None and direction not in ATTRIBUTE_CHANGED_DIRECTIONS:
                        errors.append(
                            "Invalid attribute_changed.direction in "
                            f"{key}: {direction!r}; expected one of "
                            f"{sorted(ATTRIBUTE_CHANGED_DIRECTIONS)}"
                        )

    # Validate fixture
    fixture = data.get("fixture")
    if fixture is not None:
        if isinstance(fixture, dict):
            if "base" not in fixture:
                errors.append("Fixture dict must have 'base' key")
        elif not isinstance(fixture, str):
            errors.append(f"Fixture must be a string or dict, got {type(fixture)}")

    # v3.1 calibration scenarios are identified by taxonomy.feasibility.
    # Legacy/forward-compatible slots such as expected_behavior and
    # missing_parameters may be present, but the submitted corpus leaves them
    # null and scores refusal/clarification through detector-side behavior plus
    # an unchanged-state gate.

    return errors
