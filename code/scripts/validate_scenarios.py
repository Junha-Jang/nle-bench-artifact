#!/usr/bin/env python3
"""Validate the active NLE-Bench v3.1 scenario corpus.

This script is intentionally lightweight: it loads every YAML file through the
submitted package parser, runs the package schema checks, and verifies the
review-bundle layout/counts reviewers are likely to inspect.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from pathlib import Path

import yaml

from nlebench.models import Scenario
from nlebench.runner.scenario_loader import SCENARIOS_DIR, validate_scenario_yaml


VALID_FEASIBILITIES = {"feasible", "infeasible", "ambiguous"}
VALID_INFORMATION = {"explicit", "state", "context", "diagnosis"}
VALID_ACTIONS = {"atomic", "compound", "dependent", "cumulative"}
VALID_SPLITS = {"dev", "test"}

INFO_PREFIX = {
    "explicit": "EX",
    "state": "ST",
    "context": "CX",
    "diagnosis": "DI",
}
ACTION_PREFIX = {
    "atomic": "AT",
    "compound": "CO",
    "dependent": "DE",
    "cumulative": "CU",
}
CALIBRATION_PREFIX = {
    "infeasible": "IN",
    "ambiguous": "AM",
}

FEASIBLE_ID_RE = re.compile(r"^NLEB-(EX|ST|CX|DI)-(AT|CO|DE|CU)-\d{3}$")
CALIBRATION_ID_RE = re.compile(r"^NLEB-(IN|AM)-(EX|ST|CX|DI)-\d{3}$")
LEGACY_ID_RE = re.compile(r"^NLB-v3-[A-Z]{2}-[A-Z]{2}-\d{3}$")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scenarios-dir",
        type=Path,
        default=SCENARIOS_DIR,
        help=f"Scenario root to validate (default: {SCENARIOS_DIR})",
    )
    parser.add_argument(
        "--expected-total",
        type=int,
        default=800,
        help="Expected YAML count for this corpus; use 0 to skip.",
    )
    parser.add_argument(
        "--expected-dev",
        type=int,
        default=200,
        help="Expected dev split count; use 0 to skip.",
    )
    parser.add_argument(
        "--expected-test",
        type=int,
        default=600,
        help="Expected test split count; use 0 to skip.",
    )
    return parser.parse_args()


def load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise TypeError(f"YAML root is {type(data).__name__}, expected dict")
    return data


def check_path_metadata(root: Path, path: Path, scenario: Scenario) -> list[str]:
    errors: list[str] = []
    rel = path.relative_to(root)
    parts = rel.parts

    if len(parts) < 4:
        return [f"{rel}: expected nested v3.1 path, got {rel}"]

    feasibility = scenario.feasibility
    taxonomy = scenario.effective_taxonomy
    information = taxonomy.information
    action = taxonomy.action
    split = scenario.split

    if feasibility not in VALID_FEASIBILITIES:
        errors.append(f"{rel}: invalid feasibility {feasibility!r}")
    if split not in VALID_SPLITS:
        errors.append(f"{rel}: invalid split {split!r}")

    path_feasibility = parts[0]
    if path_feasibility != feasibility:
        errors.append(
            f"{rel}: taxonomy.feasibility {feasibility!r} does not match path {path_feasibility!r}"
        )

    if path_feasibility == "feasible":
        if len(parts) != 5:
            errors.append(f"{rel}: feasible path should be feasible/<info>/<action>/<split>/<file>")
            return errors
        path_info, path_action, path_split = parts[1], parts[2], parts[3]
        if path_info not in VALID_INFORMATION:
            errors.append(f"{rel}: invalid information directory {path_info!r}")
        if path_action not in VALID_ACTIONS:
            errors.append(f"{rel}: invalid action directory {path_action!r}")
        if information != path_info:
            errors.append(f"{rel}: taxonomy.information {information!r} does not match path {path_info!r}")
        if action != path_action:
            errors.append(f"{rel}: taxonomy.action {action!r} does not match path {path_action!r}")
        if split != path_split:
            errors.append(f"{rel}: split {split!r} does not match path {path_split!r}")

        expected_prefix = f"NLEB-{INFO_PREFIX.get(path_info)}-{ACTION_PREFIX.get(path_action)}-"
        if not scenario.id.startswith(expected_prefix) or not FEASIBLE_ID_RE.match(scenario.id):
            errors.append(f"{rel}: feasible id {scenario.id!r} does not match path prefix {expected_prefix!r}")
    elif path_feasibility in {"infeasible", "ambiguous"}:
        if len(parts) != 4:
            errors.append(f"{rel}: calibration path should be {path_feasibility}/<info>/<split>/<file>")
            return errors
        path_info, path_split = parts[1], parts[2]
        if path_info not in VALID_INFORMATION:
            errors.append(f"{rel}: invalid information directory {path_info!r}")
        if information != path_info:
            errors.append(f"{rel}: taxonomy.information {information!r} does not match path {path_info!r}")
        if action is not None:
            errors.append(f"{rel}: calibration scenario should not have taxonomy.action, got {action!r}")
        if split != path_split:
            errors.append(f"{rel}: split {split!r} does not match path {path_split!r}")

        expected_prefix = f"NLEB-{CALIBRATION_PREFIX[path_feasibility]}-{INFO_PREFIX.get(path_info)}-"
        if not scenario.id.startswith(expected_prefix) or not CALIBRATION_ID_RE.match(scenario.id):
            errors.append(f"{rel}: calibration id {scenario.id!r} does not match path prefix {expected_prefix!r}")
    else:
        errors.append(f"{rel}: top-level directory {path_feasibility!r} is not a v3.1 scenario class")

    expected_filename = f"{scenario.id}.yaml"
    if path.name != expected_filename:
        errors.append(f"{rel}: filename {path.name!r} does not match scenario id {scenario.id!r}")

    if not scenario.legacy_id or not LEGACY_ID_RE.match(scenario.legacy_id):
        errors.append(f"{rel}: missing or invalid legacy_id {scenario.legacy_id!r}")
    elif scenario.legacy_id.replace("NLB-v3-", "NLEB-") != scenario.id:
        errors.append(f"{rel}: legacy_id {scenario.legacy_id!r} does not map to public id {scenario.id!r}")

    return errors


def active_schema_errors(data: dict) -> list[str]:
    """Run package YAML checks under the submitted v3.1 schema contract."""
    return validate_scenario_yaml(data)


def main() -> int:
    args = parse_args()
    scenarios_dir = args.scenarios_dir.resolve()
    if not scenarios_dir.exists():
        print(f"ERROR: scenarios directory not found: {scenarios_dir}", file=sys.stderr)
        return 1

    yaml_files = sorted(scenarios_dir.rglob("*.yaml"))
    errors: list[str] = []
    ids: dict[str, Path] = {}
    split_counts: Counter[str] = Counter()
    feasibility_counts: Counter[str] = Counter()
    scale_counts: Counter[str] = Counter()
    cell_counts: Counter[str] = Counter()

    for path in yaml_files:
        rel = path.relative_to(scenarios_dir)
        try:
            data = load_yaml(path)
        except Exception as exc:  # pragma: no cover - exercised by artifact checks
            errors.append(f"{rel}: YAML load error: {exc}")
            continue

        for err in active_schema_errors(data):
            errors.append(f"{rel}: {err}")

        try:
            scenario = Scenario.from_dict(data)
        except Exception as exc:
            errors.append(f"{rel}: Scenario.from_dict error: {exc}")
            continue

        if scenario.id in ids:
            errors.append(f"{rel}: duplicate scenario id {scenario.id!r}; first seen at {ids[scenario.id]}")
        else:
            ids[scenario.id] = rel

        errors.extend(check_path_metadata(scenarios_dir, path, scenario))

        taxonomy = scenario.effective_taxonomy
        split_counts[scenario.split or "missing"] += 1
        feasibility_counts[scenario.feasibility] += 1
        scale_counts[taxonomy.scale.value] += 1
        if scenario.feasibility == "feasible":
            cell_counts[f"{taxonomy.information}/{taxonomy.action}"] += 1
        else:
            cell_counts[f"{scenario.feasibility}/{taxonomy.information}"] += 1

    if args.expected_total and len(yaml_files) != args.expected_total:
        errors.append(f"GLOBAL: found {len(yaml_files)} YAML files, expected {args.expected_total}")
    if args.expected_dev and split_counts["dev"] != args.expected_dev:
        errors.append(f"GLOBAL: found {split_counts['dev']} dev scenarios, expected {args.expected_dev}")
    if args.expected_test and split_counts["test"] != args.expected_test:
        errors.append(f"GLOBAL: found {split_counts['test']} test scenarios, expected {args.expected_test}")

    expected_feasibility = {"feasible": 640, "infeasible": 80, "ambiguous": 80}
    for key, expected in expected_feasibility.items():
        if feasibility_counts[key] != expected:
            errors.append(f"GLOBAL: found {feasibility_counts[key]} {key} scenarios, expected {expected}")

    print("=" * 72)
    print("NLE-BENCH SCENARIO VALIDATION")
    print("=" * 72)
    print(f"Scenario root: {scenarios_dir}")
    print(f"YAML files: {len(yaml_files)}")
    print(f"Unique ids: {len(ids)}")
    print(f"Split counts: {dict(sorted(split_counts.items()))}")
    print(f"Feasibility counts: {dict(sorted(feasibility_counts.items()))}")
    print(f"Scale counts: {dict(sorted(scale_counts.items()))}")
    print(f"Cells checked: {len(cell_counts)}")

    if errors:
        print(f"\nERRORS FOUND: {len(errors)}")
        for err in sorted(errors):
            print(f"  [ERROR] {err}")
        print("=" * 72)
        return 1

    print("\nALL CHECKS PASSED")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
