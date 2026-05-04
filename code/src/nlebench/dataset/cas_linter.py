"""
Constraint Authoring Standard (CAS) Linter

Validates scenario YAML files against the NLE-Bench authoring standard.
Ensures consistency, completeness, and correctness of scenario definitions.

Rules:
- Required fields present and valid
- Constraint types use correct operators
- Feasibility-specific fields present
- ID format follows conventions
- Tolerance specified for numeric comparisons
- expected_changed_entities non-empty for feasible scenarios
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

from nlebench.models import ConstraintType, Level, Operator, Scenario

logger = logging.getLogger(__name__)

# Valid categories (includes both v2.3 standard + legacy naming)
VALID_CATEGORIES = {
    "caption", "clip", "track", "sequence", "media", "bin",
    "caption_editing", "clip_editing", "clip_management",
    "track_management", "structure_management",
    "compound_editing", "batch_operations", "intelligent_editing",
    "general_editing", "cross_category",
}

# Valid fixture names
VALID_FIXTURE_PREFIXES = {
    "basic", "single_clip", "multi_clip", "captions", "complex",
}

# ID format patterns by feasibility
ID_PREFIXES = {
    "feasible": {"L1_", "L2_", "L3_", "L4_", "L4a_", "L4b_"},
    "infeasible": {"infeasible_"},
    "ambiguous": {"ambiguous_"},
}

# Operators that require tolerance for numeric fields
NUMERIC_OPERATORS = {Operator.EQUALS, Operator.GTE, Operator.LTE, Operator.GT, Operator.LT}


@dataclass
class LintError:
    """A single linting error."""

    scenario_id: str
    rule: str
    message: str
    severity: str = "error"  # "error" or "warning"


@dataclass
class LintResult:
    """Result of linting one or more scenarios."""

    errors: list[LintError] = field(default_factory=list)
    warnings: list[LintError] = field(default_factory=list)
    scenarios_checked: int = 0

    @property
    def passed(self) -> bool:
        return len(self.errors) == 0

    def summary(self) -> str:
        lines = [
            f"CAS Lint: {self.scenarios_checked} scenarios checked",
            f"  Errors: {len(self.errors)}",
            f"  Warnings: {len(self.warnings)}",
        ]
        if self.errors:
            lines.append("")
            lines.append("Errors:")
            for e in self.errors:
                lines.append(f"  [{e.scenario_id}] {e.rule}: {e.message}")
        if self.warnings:
            lines.append("")
            lines.append("Warnings:")
            for w in self.warnings:
                lines.append(f"  [{w.scenario_id}] {w.rule}: {w.message}")
        return "\n".join(lines)


def lint_scenario(scenario: Scenario) -> list[LintError]:
    """
    Lint a single Scenario object against CAS rules.

    Returns list of LintError (empty = passed).
    """
    errors: list[LintError] = []
    sid = scenario.id

    # Rule: ID format
    valid_prefixes = ID_PREFIXES.get(scenario.feasibility, set())
    if valid_prefixes and not any(sid.startswith(p) for p in valid_prefixes):
        errors.append(LintError(
            sid, "id_format",
            f"ID '{sid}' should start with one of {valid_prefixes} for {scenario.feasibility} scenarios",
        ))

    # Rule: category valid
    if scenario.category not in VALID_CATEGORIES:
        errors.append(LintError(
            sid, "invalid_category",
            f"Category '{scenario.category}' not in {VALID_CATEGORIES}",
        ))

    # Rule: user_messages non-empty
    if not scenario.user_messages:
        errors.append(LintError(
            sid, "empty_messages",
            "user_messages must not be empty",
        ))

    # Rule: feasible scenarios must have at least 1 required + 1 validity
    if scenario.feasibility == "feasible":
        if not scenario.required_constraints:
            errors.append(LintError(
                sid, "no_required_constraints",
                "Feasible scenarios must have at least one required constraint",
            ))
        if not scenario.validity_constraints:
            errors.append(LintError(
                sid, "no_validity_constraints",
                "Feasible scenarios should have at least one validity constraint",
                severity="warning",
            ))

    # Rule: per-level constraint count ranges
    if scenario.feasibility == "feasible":
        n_constraints = len(scenario.all_constraints)
        level = scenario.level.base_level
        constraint_ranges = {
            "L1": (1, 3),
            "L2": (3, 6),
            "L3": (5, 10),
        }
        if level in constraint_ranges:
            lo, hi = constraint_ranges[level]
            if n_constraints > hi:
                errors.append(LintError(
                    sid, "too_many_constraints",
                    f"{level} scenarios should have at most {hi} constraints (has {n_constraints})",
                    severity="warning",
                ))
            if n_constraints < lo:
                errors.append(LintError(
                    sid, "too_few_constraints",
                    f"{level} scenarios should have at least {lo} constraints (has {n_constraints})",
                    severity="warning",
                ))

    # Rule: feasible scenarios should have expected_changed_entities
    if scenario.feasibility == "feasible" and not scenario.expected_changed_entities:
        errors.append(LintError(
            sid, "missing_expected_entities",
            "Feasible scenarios should specify expected_changed_entities for OVR",
            severity="warning",
        ))

    # Rule: legacy infeasible metadata, retained as a warning because v3.1
    # encodes calibration labels through taxonomy and detector-side behavior.
    if scenario.feasibility == "infeasible" and not scenario.required_capability:
        errors.append(LintError(
            sid, "missing_capability",
            "required_capability is empty; v3.1 uses taxonomy + detector behavior",
            severity="warning",
        ))

    # Rule: legacy ambiguous metadata, retained as a warning for corpora that
    # aim to score missing-parameter quality rather than the v3.1 proxy.
    if scenario.feasibility == "ambiguous":
        if not scenario.ambiguity_type:
            errors.append(LintError(
                sid, "missing_ambiguity_type",
                "Ambiguous scenarios should specify ambiguity_type when used",
                severity="warning",
            ))
        if not scenario.required_clarifications:
            errors.append(LintError(
                sid, "missing_clarifications",
                "required_clarifications is empty; v3.1 SR-ambiguous is not a missing-parameter score",
                severity="warning",
            ))

    # Rule: numeric constraints should have tolerance
    for constraint in scenario.all_constraints:
        if (
            constraint.operator in NUMERIC_OPERATORS
            and isinstance(constraint.value, (int, float))
            and constraint.tolerance is None
        ):
            errors.append(LintError(
                sid, "missing_tolerance",
                f"Numeric constraint '{constraint.field}.{constraint.operator.value}' "
                f"should specify tolerance",
                severity="warning",
            ))

    # Rule: L4/L4a/L4b scenarios should have max_turns > 1
    if scenario.level.base_level == "L4" and scenario.max_turns <= 1:
        errors.append(LintError(
            sid, "l4_single_turn",
            "L4/L4a/L4b scenarios should have max_turns > 1",
            severity="warning",
        ))

    # Rule: L4/L4a/L4b scenarios should have multiple user_messages
    if scenario.level.base_level == "L4" and len(scenario.user_messages) < 2:
        errors.append(LintError(
            sid, "l4_single_message",
            "L4/L4a/L4b scenarios should have multiple user_messages for multi-turn",
            severity="warning",
        ))

    # Rule: L4a/L4b scenarios should use turns format
    if scenario.level in (Level.L4a, Level.L4b) and scenario.turns is None:
        errors.append(LintError(
            sid, "l4_missing_turns",
            f"{scenario.level.value} scenarios should use 'turns' format for per-turn constraints",
            severity="warning",
        ))

    # Rule: Turn.user must not be empty
    if scenario.turns:
        for i, turn in enumerate(scenario.turns):
            if not turn.user or not turn.user.strip():
                errors.append(LintError(
                    sid, "empty_turn_user",
                    f"Turn {i} has empty 'user' message",
                ))

    return errors


def lint_yaml_file(yaml_path: Path) -> list[LintError]:
    """Lint a single scenario YAML file."""
    try:
        with open(yaml_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        scenario = Scenario.from_dict(data)
        return lint_scenario(scenario)
    except Exception as e:
        return [LintError(
            str(yaml_path.name), "parse_error",
            f"Failed to parse: {e}",
        )]


def lint_directory(scenarios_dir: Path) -> LintResult:
    """
    Lint all scenario YAML files in a directory tree.

    Scans L1/, L2/, L3/, L4/, L4a/, L4b/, infeasible/, ambiguous/ subdirectories.
    """
    result = LintResult()

    for subdir_name in ["L1", "L2", "L3", "L4", "L4a", "L4b", "infeasible", "ambiguous"]:
        subdir = scenarios_dir / subdir_name
        if not subdir.exists():
            continue

        for yaml_file in sorted(subdir.glob("*.yaml")):
            lint_errors = lint_yaml_file(yaml_file)
            result.scenarios_checked += 1

            for error in lint_errors:
                if error.severity == "warning":
                    result.warnings.append(error)
                else:
                    result.errors.append(error)

    return result
