#!/usr/bin/env python3
"""Heuristic audit for instruction-to-constraint coverage.

This is not a scenario validator. It scans natural-language instructions for
surface mentions of numeric timing, duration, and spatial-position requirements,
then checks whether required constraints mention corresponding fields or named
predicates. Findings are review candidates for human audit.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
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

TIME_LITERAL_RE = re.compile(
    r"\b(?:at|from|until|around|near|before|after|starting\s+at|starts?\s+at|begins?\s+at|timeline)\s+"
    r"(?:the\s+)?(?:timeline\s+)?\d+(?:\.\d+)?\s*(?:s|sec|secs|second|seconds)\b"
    r"|\bposition\s+\d+(?:\.\d+)?\s*(?:s|sec|secs|second|seconds)\b"
    r"|\bat\s+the\s+\d+(?:\.\d+)?[- ](?:s|sec|second)s?\s+mark\b"
    r"|\b(?:start|end)\b[^.?!;]{0,50}\b\d+(?:\.\d+)?\s*(?:s|sec|secs|second|seconds)\s+(?:later|earlier)\b"
    r"|\b\d{1,2}:\d{2}(?::\d{2})?\b",
    re.IGNORECASE,
)
DURATION_RE = re.compile(
    r"\b(?:duration|durations|lasts?|lasting)\b"
    r"|\bfor\s+\d+(?:\.\d+)?\s*(?:s|sec|secs|second|seconds)\b"
    r"|\b(?:shorten|lengthen|extend|trim)\b[^.?!;]{0,50}\b\d+(?:\.\d+)?\s*(?:s|sec|secs|second|seconds)\b"
    r"|\b\d+(?:\.\d+)?[- ](?:s|sec|second)s?\s+(?:duration|transition|fade|dissolve|gap|pause)\b",
    re.IGNORECASE,
)
RELATIVE_TIME_RE = re.compile(
    r"\b(?:at|from|to|until|before|after)\s+(?:its|their|the|this)\s+"
    r"(?:start|end|beginning)\b"
    r"|\b(?:beginning|start|end)\s+of\s+(?:the|its|their)\b",
    re.IGNORECASE,
)
SPATIAL_RE = re.compile(
    r"\b(?:top|bottom|upper|lower)[-_ ](?:left|right|center)\b"
    r"|\b(?:lower|upper)[-_ ]third\b"
    r"|\b(?:top|bottom|centered|centre|center)\b"
    r"|\bposition(?:ed|ing)?\b"
    r"|\b(?:left|right)[-_ ](?:aligned|side|corner)\b",
    re.IGNORECASE,
)
SPLIT_POSITION_RE = re.compile(
    r"\b(?:split|cut|trim)\b[^.?!;]{0,50}\b(?:at|to|from)\b",
    re.IGNORECASE,
)
NUMERIC_RE = re.compile(r"(?<![A-Za-z])[-+]?\d+(?:\.\d+)?\s*(?:%|x|dB|db|s|sec|seconds?)?\b")
CAPTION_TITLE_RE = re.compile(r"\b(?:caption|subtitle|title|text)\b", re.IGNORECASE)

EXACT_TIME_FIELDS = {
    "start",
    "end",
    "timeline_start",
    "timeline_end",
    "in_point",
    "out_point",
}
DURATION_FIELDS = {"duration"}
SPATIAL_FIELDS = {
    "position",
    "position_x",
    "position_y",
    "transform.position",
    "transform.position_x",
    "transform.position_y",
    "caption.style.position",
    "style.position",
}
EXACT_TIME_CONSTRAINTS = {"position_equals"}
DURATION_CONSTRAINTS = {"duration_equals"}
SPATIAL_CONSTRAINTS: set[str] = set()


@dataclass
class ScenarioAudit:
    scenario_id: str
    split: str
    information: str
    action: str
    path: str
    instruction: str
    instruction_features: list[str]
    constraint_features: list[str]
    flags: list[str]
    numeric_mentions: list[str]


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
    parser.add_argument(
        "--markdown-out",
        type=Path,
        help="Optional Markdown report path.",
    )
    parser.add_argument(
        "--json-out",
        type=Path,
        help="Optional JSON report path.",
    )
    parser.add_argument(
        "--csv-out",
        type=Path,
        help="Optional CSV of flagged scenarios.",
    )
    parser.add_argument(
        "--max-examples",
        type=int,
        default=25,
        help="Maximum flagged examples to print/write in the compact report.",
    )
    return parser.parse_args()


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise TypeError(f"{path}: YAML root is {type(data).__name__}, expected dict")
    return data


def instruction_text(data: dict[str, Any]) -> str:
    turns = data.get("turns") or []
    chunks: list[str] = []
    for turn in turns:
        if isinstance(turn, dict) and isinstance(turn.get("instruction"), str):
            chunks.append(turn["instruction"])
    return " ".join(chunks)


def strip_quoted_text(text: str) -> str:
    """Remove quoted caption/title strings before numeric surface matching."""
    return re.sub(r"'[^']*'|\"[^\"]*\"", "", text)


def constraint_items(data: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    required = (data.get("constraints") or {}).get("required") or []
    items: list[tuple[str, dict[str, Any]]] = []
    for constraint in required:
        if not isinstance(constraint, dict) or len(constraint) != 1:
            continue
        name, params = next(iter(constraint.items()))
        if isinstance(params, dict):
            items.append((str(name), params))
        else:
            items.append((str(name), {}))
    return items


def collect_field_tokens(value: Any) -> set[str]:
    tokens: set[str] = set()
    if isinstance(value, dict):
        for key, nested in value.items():
            key_s = str(key)
            tokens.add(key_s)
            if key_s == "field" and isinstance(nested, str):
                tokens.add(nested)
                tokens.update(nested.split("."))
            tokens.update(collect_field_tokens(nested))
    elif isinstance(value, list):
        for item in value:
            tokens.update(collect_field_tokens(item))
    return tokens


def instruction_features(text: str) -> tuple[list[str], list[str]]:
    scan_text = strip_quoted_text(text)
    features: list[str] = []
    if TIME_LITERAL_RE.search(scan_text) or RELATIVE_TIME_RE.search(scan_text):
        features.append("time")
    if DURATION_RE.search(scan_text):
        features.append("duration")
    spatial_text = re.sub(
        r"\bposition\s+\d+(?:\.\d+)?\s*(?:s|sec|secs|second|seconds)\b",
        "",
        scan_text,
        flags=re.IGNORECASE,
    )
    if SPATIAL_RE.search(spatial_text):
        features.append("spatial_position")
    if SPLIT_POSITION_RE.search(scan_text):
        features.append("split_position")
    if CAPTION_TITLE_RE.search(scan_text):
        features.append("caption_or_title")
    numeric_mentions = [m.group(0).strip() for m in NUMERIC_RE.finditer(scan_text)]
    if numeric_mentions:
        features.append("numeric")
    return sorted(set(features)), numeric_mentions


def constraint_features(items: list[tuple[str, dict[str, Any]]]) -> list[str]:
    names = {name for name, _ in items}
    field_tokens: set[str] = set()
    for _, params in items:
        field_tokens.update(collect_field_tokens(params))

    features: list[str] = []
    if names & EXACT_TIME_CONSTRAINTS or field_tokens & EXACT_TIME_FIELDS:
        features.append("time")
    if names & DURATION_CONSTRAINTS or field_tokens & DURATION_FIELDS:
        features.append("duration")
    if names & SPATIAL_CONSTRAINTS or field_tokens & SPATIAL_FIELDS:
        features.append("spatial_position")
    if "order" in names:
        features.append("relative_order")
    if "unchanged_except" in names:
        features.append("preservation")
    return sorted(set(features))


def flags_for(instr_features: list[str], constr_features: list[str]) -> list[str]:
    instr = set(instr_features)
    constr = set(constr_features)
    flags: list[str] = []
    if "time" in instr and "time" not in constr:
        flags.append("time_mention_without_time_constraint")
    if "duration" in instr and "duration" not in constr:
        flags.append("duration_mention_without_duration_constraint")
    if "split_position" in instr and not ({"time", "spatial_position"} & constr):
        flags.append("split_position_without_position_constraint")
    if "spatial_position" in instr and "spatial_position" not in constr:
        flags.append("spatial_position_without_position_constraint")
    if "caption_or_title" in instr and "time_mention_without_time_constraint" in flags:
        flags.append("caption_or_title_time_coverage_candidate")
    return flags


def audit_scenario(root: Path, path: Path, data: dict[str, Any]) -> ScenarioAudit:
    text = instruction_text(data)
    instr_features, numeric_mentions = instruction_features(text)
    constr_features = constraint_features(constraint_items(data))
    taxonomy = data.get("taxonomy") or {}
    return ScenarioAudit(
        scenario_id=str(data.get("id", path.stem)),
        split=str(data.get("split", "")),
        information=str(taxonomy.get("information", "")),
        action=str(taxonomy.get("action", "")),
        path=str(path.relative_to(root)),
        instruction=text,
        instruction_features=instr_features,
        constraint_features=constr_features,
        flags=flags_for(instr_features, constr_features),
        numeric_mentions=numeric_mentions,
    )


def write_markdown(path: Path, audits: list[ScenarioAudit], max_examples: int) -> None:
    flagged = [a for a in audits if a.flags]
    flag_counts = Counter(flag for audit in flagged for flag in audit.flags)
    feature_counts = Counter(feature for audit in audits for feature in audit.instruction_features)
    caption_title_flags = [
        a for a in flagged if "caption_or_title_time_coverage_candidate" in a.flags
    ]

    lines = [
        "# Instruction-to-Constraint Coverage Audit",
        "",
        "This report is generated by `code/scripts/audit_instruction_constraint_coverage.py`.",
        "It is a heuristic review aid, not a validator failure report. It does not prove",
        "that a scenario is correct or incorrect, and it does not compare numeric values.",
        "",
        "## Summary",
        "",
        f"- Scenarios scanned: {len(audits)}",
        f"- Scenarios with numeric instruction mentions: {sum(1 for a in audits if a.numeric_mentions)}",
        f"- Scenarios with heuristic coverage flags: {len(flagged)}",
        f"- Caption/title timing candidates: {len(caption_title_flags)}",
        "",
        "## Instruction Feature Counts",
        "",
    ]
    for feature, count in sorted(feature_counts.items()):
        lines.append(f"- `{feature}`: {count}")
    lines.extend(["", "## Flag Counts", ""])
    if flag_counts:
        for flag, count in sorted(flag_counts.items()):
            lines.append(f"- `{flag}`: {count}")
    else:
        lines.append("- No heuristic flags.")

    lines.extend(
        [
            "",
            f"## First {min(max_examples, len(flagged))} Flagged Examples",
            "",
        ]
    )
    for audit in flagged[:max_examples]:
        numeric = ", ".join(audit.numeric_mentions) if audit.numeric_mentions else "none"
        lines.extend(
            [
                f"### `{audit.scenario_id}`",
                "",
                f"- Path: `{audit.path}`",
                f"- Cell: `{audit.information}/{audit.action}`, split `{audit.split}`",
                f"- Flags: {', '.join(f'`{flag}`' for flag in audit.flags)}",
                f"- Instruction features: {', '.join(f'`{f}`' for f in audit.instruction_features) or 'none'}",
                f"- Required-constraint features: {', '.join(f'`{f}`' for f in audit.constraint_features) or 'none'}",
                f"- Numeric mentions: {numeric}",
                f"- Instruction: {audit.instruction}",
                "",
            ]
        )

    lines.extend(
        [
            "## Interpretation",
            "",
            "A flag means the instruction contains a surface timing, duration, split-position,",
            "or spatial-position cue, while the required constraints do not contain an",
            "obvious matching field or named predicate. Expected false positives include",
            "relative wording, colloquial use of position words, and constraints encoded",
            "through broader predicates. Expected false negatives include requirements",
            "phrased without these surface cues or constraints whose semantics are broader",
            "than their field names. Human review is required before changing any scenario",
            "or interpreting a flag as a scoring defect.",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def write_json(path: Path, audits: list[ScenarioAudit]) -> None:
    payload = {
        "description": "Heuristic instruction-to-constraint coverage audit; flags are review candidates, not validator failures.",
        "scenarios_scanned": len(audits),
        "flagged_scenarios": sum(1 for audit in audits if audit.flags),
        "flag_counts": dict(Counter(flag for audit in audits for flag in audit.flags)),
        "audits": [asdict(audit) for audit in audits],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def write_csv(path: Path, audits: list[ScenarioAudit]) -> None:
    flagged = [audit for audit in audits if audit.flags]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "scenario_id",
                "split",
                "information",
                "action",
                "path",
                "flags",
                "instruction_features",
                "constraint_features",
                "numeric_mentions",
                "instruction",
            ],
        )
        writer.writeheader()
        for audit in flagged:
            writer.writerow(
                {
                    "scenario_id": audit.scenario_id,
                    "split": audit.split,
                    "information": audit.information,
                    "action": audit.action,
                    "path": audit.path,
                    "flags": ";".join(audit.flags),
                    "instruction_features": ";".join(audit.instruction_features),
                    "constraint_features": ";".join(audit.constraint_features),
                    "numeric_mentions": ";".join(audit.numeric_mentions),
                    "instruction": audit.instruction,
                }
            )


def main() -> int:
    args = parse_args()
    root = args.scenarios_dir.resolve()
    yaml_files = sorted(root.rglob("*.yaml"))
    audits: list[ScenarioAudit] = []

    for path in yaml_files:
        data = load_yaml(path)
        if not args.include_non_feasible and (data.get("taxonomy") or {}).get("feasibility") != "feasible":
            continue
        audits.append(audit_scenario(root, path, data))

    flagged = [audit for audit in audits if audit.flags]
    flag_counts = Counter(flag for audit in flagged for flag in audit.flags)
    feature_counts = Counter(feature for audit in audits for feature in audit.instruction_features)

    print("=" * 72)
    print("NLE-BENCH INSTRUCTION-CONSTRAINT COVERAGE AUDIT")
    print("=" * 72)
    print("Status: heuristic review aid; flags are not validator failures.")
    print(f"Scenario root: {root}")
    print(f"Scenarios scanned: {len(audits)}")
    print(f"Scenarios with numeric instruction mentions: {sum(1 for a in audits if a.numeric_mentions)}")
    print(f"Scenarios with heuristic coverage flags: {len(flagged)}")
    print(f"Instruction features: {dict(sorted(feature_counts.items()))}")
    print(f"Flag counts: {dict(sorted(flag_counts.items()))}")

    if flagged:
        print("\nExamples:")
        for audit in flagged[: args.max_examples]:
            print(
                f"  [{audit.scenario_id}] {', '.join(audit.flags)} | "
                f"instr={audit.instruction_features} constraints={audit.constraint_features}"
            )
            print(f"    {audit.instruction}")

    if args.markdown_out:
        write_markdown(args.markdown_out, audits, args.max_examples)
        print(f"\nWrote Markdown report: {args.markdown_out}")
    if args.json_out:
        write_json(args.json_out, audits)
        print(f"Wrote JSON report: {args.json_out}")
    if args.csv_out:
        write_csv(args.csv_out, audits)
        print(f"Wrote CSV report: {args.csv_out}")

    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
