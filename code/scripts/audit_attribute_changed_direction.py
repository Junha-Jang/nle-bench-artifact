#!/usr/bin/env python3
"""Audit attribute_changed.direction usage in the released scenario corpus.

The scorer enforces direction only when the compared field is numeric at
runtime. This script identifies every scenario whose `attribute_changed`
constraint supplies `direction`, summarizes direction/field usage, and writes a
reviewable scenario list.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import yaml


DEFAULT_SCENARIOS_DIR = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "nlebench"
    / "dataset"
    / "scenarios_v3_1"
)

VALID_DIRECTIONS = {"increase", "decrease", "any"}
LIKELY_NUMERIC_FIELD_TOKENS = {
    "duration",
    "end",
    "fps",
    "height",
    "in_point",
    "opacity",
    "out_point",
    "pan",
    "position_x",
    "position_y",
    "source_in",
    "source_out",
    "speed",
    "start",
    "timeline_end",
    "timeline_start",
    "volume",
    "width",
    "x",
    "y",
}


@dataclass
class DirectionConstraint:
    section: str
    index: int
    entity: str
    field: str
    direction: str
    likely_numeric: bool


@dataclass
class DirectionScenario:
    scenario_id: str
    split: str
    feasibility: str
    information: str
    action: str
    path: str
    constraints: list[DirectionConstraint]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scenarios-dir",
        type=Path,
        default=DEFAULT_SCENARIOS_DIR,
        help=f"Scenario root to audit (default: {DEFAULT_SCENARIOS_DIR})",
    )
    parser.add_argument(
        "--include-non-feasible",
        action="store_true",
        help="Also scan infeasible and ambiguous scenarios. Default scans feasible scenarios only.",
    )
    parser.add_argument("--markdown-out", type=Path, help="Optional Markdown report path.")
    parser.add_argument("--json-out", type=Path, help="Optional JSON report path.")
    parser.add_argument("--csv-out", type=Path, help="Optional scenario-level CSV path.")
    parser.add_argument(
        "--max-examples",
        type=int,
        default=25,
        help="Maximum affected scenarios to print/write as examples.",
    )
    return parser.parse_args()


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise TypeError(f"{path}: YAML root is {type(data).__name__}, expected dict")
    return data


def is_likely_numeric_field(field: str) -> bool:
    tokens = set(field.split("."))
    tokens.add(field)
    return bool(tokens & LIKELY_NUMERIC_FIELD_TOKENS)


def direction_constraints(data: dict[str, Any]) -> list[DirectionConstraint]:
    constraints = data.get("constraints") or {}
    found: list[DirectionConstraint] = []
    for section in ("required", "specified", "required_named", "specified_named"):
        for index, constraint in enumerate(constraints.get(section) or []):
            if not isinstance(constraint, dict) or len(constraint) != 1:
                continue
            if "attribute_changed" not in constraint:
                continue
            params = constraint.get("attribute_changed") or {}
            if "direction" not in params:
                continue
            field = str(params.get("field", ""))
            found.append(
                DirectionConstraint(
                    section=section,
                    index=index,
                    entity=str(params.get("entity", "")),
                    field=field,
                    direction=str(params.get("direction", "")),
                    likely_numeric=is_likely_numeric_field(field),
                )
            )
    return found


def audit_scenario(root: Path, path: Path, data: dict[str, Any]) -> DirectionScenario | None:
    found = direction_constraints(data)
    if not found:
        return None
    taxonomy = data.get("taxonomy") or {}
    return DirectionScenario(
        scenario_id=str(data.get("id", path.stem)),
        split=str(data.get("split", "")),
        feasibility=str(taxonomy.get("feasibility", "")),
        information=str(taxonomy.get("information", "")),
        action=str(taxonomy.get("action", "")),
        path=str(path.relative_to(root)),
        constraints=found,
    )


def summary_payload(scenarios: list[DirectionScenario]) -> dict[str, Any]:
    all_constraints = [constraint for scenario in scenarios for constraint in scenario.constraints]
    numeric_constraints = [constraint for constraint in all_constraints if constraint.likely_numeric]
    invalid_constraints = [
        constraint for constraint in all_constraints if constraint.direction not in VALID_DIRECTIONS
    ]
    return {
        "affected_scenarios": len(scenarios),
        "affected_constraints": len(all_constraints),
        "likely_numeric_constraints": len(numeric_constraints),
        "nonnumeric_or_unknown_constraints": len(all_constraints) - len(numeric_constraints),
        "invalid_direction_constraints": len(invalid_constraints),
        "direction_counts": dict(Counter(c.direction for c in all_constraints)),
        "field_counts": dict(Counter(c.field for c in all_constraints)),
        "cell_counts": dict(
            Counter(f"{s.information}/{s.action}" for s in scenarios if s.feasibility == "feasible")
        ),
        "split_counts": dict(Counter(s.split for s in scenarios)),
    }


def write_markdown(path: Path, scenarios: list[DirectionScenario], max_examples: int) -> None:
    summary = summary_payload(scenarios)
    lines = [
        "# Attribute-Changed Direction Audit",
        "",
        "This report is generated by `code/scripts/audit_attribute_changed_direction.py`.",
        "It enumerates released scenarios that pass a `direction` parameter to",
        "`attribute_changed`. Under the patched scorer, `increase` and `decrease`",
        "are enforced for numeric fields; `any` keeps the previous changed-only",
        "numeric behavior. Nonnumeric fields still require a value change.",
        "",
        "## Summary",
        "",
    ]
    for key in (
        "affected_scenarios",
        "affected_constraints",
        "likely_numeric_constraints",
        "nonnumeric_or_unknown_constraints",
        "invalid_direction_constraints",
    ):
        lines.append(f"- {key.replace('_', ' ').capitalize()}: {summary[key]}")

    lines.extend(["", "## Direction Counts", ""])
    for direction, count in sorted(summary["direction_counts"].items()):
        lines.append(f"- `{direction}`: {count}")

    lines.extend(["", "## Field Counts", ""])
    for field, count in sorted(summary["field_counts"].items()):
        lines.append(f"- `{field}`: {count}")

    lines.extend(["", f"## First {min(max_examples, len(scenarios))} Affected Scenarios", ""])
    for scenario in scenarios[:max_examples]:
        constraints = "; ".join(
            f"{c.section}[{c.index}] {c.entity}.{c.field} direction={c.direction}"
            f" numeric={str(c.likely_numeric).lower()}"
            for c in scenario.constraints
        )
        lines.extend(
            [
                f"### `{scenario.scenario_id}`",
                "",
                f"- Path: `{scenario.path}`",
                f"- Cell: `{scenario.information}/{scenario.action}`, split `{scenario.split}`",
                f"- Constraints: {constraints}",
                "",
            ]
        )

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def write_json(path: Path, scenarios: list[DirectionScenario]) -> None:
    payload = {
        "description": "attribute_changed.direction usage audit for the released scenario corpus.",
        "summary": summary_payload(scenarios),
        "scenarios": [asdict(scenario) for scenario in scenarios],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def write_csv(path: Path, scenarios: list[DirectionScenario]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "scenario_id",
                "split",
                "feasibility",
                "information",
                "action",
                "path",
                "constraint_count",
                "directions",
                "fields",
                "likely_numeric_constraints",
            ],
        )
        writer.writeheader()
        for scenario in scenarios:
            writer.writerow(
                {
                    "scenario_id": scenario.scenario_id,
                    "split": scenario.split,
                    "feasibility": scenario.feasibility,
                    "information": scenario.information,
                    "action": scenario.action,
                    "path": scenario.path,
                    "constraint_count": len(scenario.constraints),
                    "directions": ";".join(c.direction for c in scenario.constraints),
                    "fields": ";".join(c.field for c in scenario.constraints),
                    "likely_numeric_constraints": sum(c.likely_numeric for c in scenario.constraints),
                }
            )


def main() -> int:
    args = parse_args()
    root = args.scenarios_dir.resolve()
    scenarios: list[DirectionScenario] = []

    for path in sorted(root.rglob("*.yaml")):
        data = load_yaml(path)
        feasibility = (data.get("taxonomy") or {}).get("feasibility")
        if not args.include_non_feasible and feasibility != "feasible":
            continue
        audit = audit_scenario(root, path, data)
        if audit is not None:
            scenarios.append(audit)

    summary = summary_payload(scenarios)
    print("=" * 72)
    print("NLE-BENCH ATTRIBUTE_CHANGED DIRECTION AUDIT")
    print("=" * 72)
    print(f"Scenario root: {root}")
    for key, value in summary.items():
        print(f"{key}: {value}")

    if scenarios:
        print("\nExamples:")
        for scenario in scenarios[: args.max_examples]:
            details = ", ".join(
                f"{c.field}:{c.direction}" for c in scenario.constraints
            )
            print(f"  [{scenario.scenario_id}] {details}")

    if args.markdown_out:
        write_markdown(args.markdown_out, scenarios, args.max_examples)
        print(f"\nWrote Markdown report: {args.markdown_out}")
    if args.json_out:
        write_json(args.json_out, scenarios)
        print(f"Wrote JSON report: {args.json_out}")
    if args.csv_out:
        write_csv(args.csv_out, scenarios)
        print(f"Wrote CSV report: {args.csv_out}")

    print("=" * 72)
    return 1 if summary["invalid_direction_constraints"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
