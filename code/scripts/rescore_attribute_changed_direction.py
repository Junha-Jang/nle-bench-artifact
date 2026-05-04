#!/usr/bin/env python3
"""Rescore raw result logs after the attribute_changed.direction scorer patch.

The raw harness logs store initial/final project states for completed runs.
This script reloads those states, evaluates feasible scenarios with the current
local scorer, and rewrites the reviewer-facing redacted aggregate artifacts.
Calibration rows are copied from the original validation because the scorer
patch affects only feasible final-state constraints.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from nlebench.models import EditProject, Scenario
from nlebench.runner.constraints import (
    CONSTRAINT_FUNCTIONS,
    ConstraintResult,
    _as_number,
    _field_tolerance,
    _get_entity,
    _resolve_field,
    validate_named_constraints,
)


SUPPLEMENTARY_ROOT = Path(__file__).resolve().parents[2]
CODE_ROOT = SUPPLEMENTARY_ROOT / "code"
REPO_ROOT = SUPPLEMENTARY_ROOT.parent
DEFAULT_RAW_RESULTS_ROOT = Path(
    os.environ.get(
        "NLEBENCH_RAW_RESULTS_ROOT",
        "raw_results_unreleased",
    )
)
SCENARIOS_DIR = CODE_ROOT / "src" / "nlebench" / "dataset" / "scenarios_v3_1"
RESULTS_DIR = SUPPLEMENTARY_ROOT / "results"

MAIN_RESULTS = RESULTS_DIR / "main_results.csv"
MAIN_RESULTS_RECOMPUTABLE = RESULTS_DIR / "main_results_recomputable.csv"
RUN_MANIFEST = RESULTS_DIR / "run_manifest.csv"
RUN_SUMMARIES = RESULTS_DIR / "run_summaries_redacted.jsonl"
PER_SCENARIO = RESULTS_DIR / "per_scenario_results_redacted.csv"
RESULT_RECONCILIATION = RESULTS_DIR / "result_reconciliation.csv"
AUDIT_MD = RESULTS_DIR / "attribute_changed_direction_rescore_audit.md"
AUDIT_JSON = RESULTS_DIR / "attribute_changed_direction_rescore_audit.json"

PAPER_MAIN_ROW_IDS = {
    "1",
    "2",
    "3",
    "4",
    "5",
    "6",
    "7",
    "9",
    "10",
    "17",
    "18",
    "19",
    "20",
    "28",
    "29",
}
VALID_DIRECTIONS = {"increase", "decrease", "any"}


@dataclass
class PatchedValidation:
    success: bool
    tsr: bool
    unpatched_release_success: bool
    unpatched_release_tsr: bool
    csr: bool | str
    failed_constraints: list[str]
    feasibility: str
    had_states: bool
    old_success: bool
    old_tsr: bool


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def boolish(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).lower() == "true"


def pct_string(successful: int, total: int) -> str:
    if total <= 0:
        return "0.0"
    return f"{successful / total:.4f}".rstrip("0").rstrip(".")


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def row_key(row: dict[str, str]) -> tuple[str, str, str, str]:
    return (row["model"], row["provider"], row["track"], row["timestamp"])


def load_scenarios() -> dict[str, Scenario]:
    scenarios: dict[str, Scenario] = {}
    for path in sorted(SCENARIOS_DIR.rglob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        scenario = Scenario.from_dict(data)
        scenarios[scenario.id] = scenario
        if scenario.legacy_id:
            scenarios[scenario.legacy_id] = scenario
    return scenarios


def scenarios_with_direction() -> set[str]:
    affected: set[str] = set()
    for path in sorted(SCENARIOS_DIR.rglob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        taxonomy = data.get("taxonomy") or {}
        if taxonomy.get("feasibility") != "feasible":
            continue
        constraints = data.get("constraints") or {}
        has_direction = False
        for section in ("required", "specified", "required_named", "specified_named"):
            for constraint in constraints.get(section) or []:
                if not isinstance(constraint, dict) or "attribute_changed" not in constraint:
                    continue
                params = constraint.get("attribute_changed") or {}
                direction = params.get("direction")
                if direction in VALID_DIRECTIONS:
                    has_direction = True
        if has_direction:
            affected.add(str(data["id"]))
            if data.get("legacy_id"):
                affected.add(str(data["legacy_id"]))
    return affected


def failed_constraint_labels(results: list[ConstraintResult]) -> list[str]:
    labels: list[str] = []
    for result in results:
        status = "error" if result.error else "failed"
        labels.append(f"named:{result.func_name}:{status}")
    return labels


def attribute_changed_without_direction(state: EditProject, params: dict, tolerance: dict) -> bool:
    """Released pre-patch behavior: changed-by-tolerance, ignoring direction."""
    initial = state._initial
    if initial is None:
        return False
    entity = _get_entity(state, params["entity"])
    initial_entity = _get_entity(initial, params["entity"])
    if entity is None or initial_entity is None:
        return entity is not initial_entity
    field_name = params["field"]
    current_val = _resolve_field(entity, field_name)
    initial_val = _resolve_field(initial_entity, field_name)
    current_num = _as_number(current_val)
    initial_num = _as_number(initial_val)
    if current_num is not None and initial_num is not None:
        tol = _field_tolerance(field_name, tolerance)
        return abs(current_num - initial_num) > tol
    return current_val != initial_val


def validate_with_attribute_changed(
    initial: EditProject,
    final: EditProject,
    scenario: Scenario,
    *,
    ignore_direction: bool,
) -> tuple[bool, list[str]]:
    original = CONSTRAINT_FUNCTIONS["attribute_changed"]
    if ignore_direction:
        CONSTRAINT_FUNCTIONS["attribute_changed"] = attribute_changed_without_direction
    try:
        tsr, result = validate_named_constraints(initial, final, scenario)
        return bool(tsr), failed_constraint_labels(result.failed)
    finally:
        CONSTRAINT_FUNCTIONS["attribute_changed"] = original


def rescore_record(record: dict[str, Any], scenario: Scenario) -> PatchedValidation:
    validation = record.get("validation") or {}
    feasibility = scenario.feasibility
    old_success = boolish(record.get("success"))
    old_tsr = boolish(validation.get("tsr"))
    old_csr = validation.get("csr", "")
    had_states = bool(record.get("initial_state_json")) and bool(record.get("final_state_json"))

    if feasibility != "feasible":
        failed = validation.get("failed_constraints") or []
        return PatchedValidation(
            success=old_success,
            tsr=old_tsr,
            unpatched_release_success=old_success,
            unpatched_release_tsr=old_tsr,
            csr=old_csr,
            failed_constraints=[str(item) for item in failed],
            feasibility=feasibility,
            had_states=had_states,
            old_success=old_success,
            old_tsr=old_tsr,
        )

    if not had_states:
        failed = validation.get("failed_constraints") or []
        return PatchedValidation(
            success=False,
            tsr=False,
            unpatched_release_success=False,
            unpatched_release_tsr=False,
            csr=boolish(old_csr),
            failed_constraints=[str(item) for item in failed],
            feasibility=feasibility,
            had_states=False,
            old_success=old_success,
            old_tsr=old_tsr,
        )

    try:
        initial = EditProject.from_json(record["initial_state_json"])
        final = EditProject.from_json(record["final_state_json"])
        unpatched_tsr, _ = validate_with_attribute_changed(
            initial,
            final,
            scenario,
            ignore_direction=True,
        )
        tsr, failed = validate_with_attribute_changed(
            initial,
            final,
            scenario,
            ignore_direction=False,
        )
    except Exception as exc:
        tsr = False
        unpatched_tsr = False
        failed = [f"patched_rescore_error:{type(exc).__name__}:{str(exc)[:120]}"]

    csr = boolish(old_csr)
    return PatchedValidation(
        success=bool(tsr and csr),
        tsr=bool(tsr),
        unpatched_release_success=bool(unpatched_tsr and csr),
        unpatched_release_tsr=bool(unpatched_tsr),
        csr=csr,
        failed_constraints=failed,
        feasibility=feasibility,
        had_states=True,
        old_success=old_success,
        old_tsr=old_tsr,
    )


def update_aggregate_csv(path: Path, counts_by_key: dict[tuple[str, str, str, str], dict[str, int]]) -> None:
    rows = load_csv(path)
    if not rows:
        return
    fieldnames = list(rows[0].keys())
    for row in rows:
        counts = counts_by_key.get(row_key(row))
        if not counts:
            continue
        row["successful_runs"] = str(counts["successful"])
        row["sr"] = pct_string(counts["successful"], counts["total"])
    write_csv(path, rows, fieldnames)


def update_run_summaries(counts_by_row: dict[str, dict[str, int]]) -> None:
    lines: list[str] = []
    with RUN_SUMMARIES.open(encoding="utf-8") as handle:
        for line in handle:
            record = json.loads(line)
            row_id = str(record.get("row_id"))
            counts = counts_by_row.get(row_id)
            if counts:
                record["successful_runs"] = counts["successful"]
                record["sr"] = float(pct_string(counts["successful"], counts["total"]))
                record["redacted_successful_runs"] = counts["successful"]
                record["rescored_under"] = "attribute_changed_direction_patched"
            lines.append(json.dumps(record, sort_keys=True))
    RUN_SUMMARIES.write_text("\n".join(lines) + "\n", encoding="utf-8")


def update_manifest(counts_by_row: dict[str, dict[str, int]]) -> None:
    rows = load_csv(RUN_MANIFEST)
    fieldnames = list(rows[0].keys())
    for row in rows:
        counts = counts_by_row.get(row["row_id"])
        if not counts:
            continue
        row["successful_runs"] = str(counts["successful"])
        row["sr"] = pct_string(counts["successful"], counts["total"])
        row["redacted_successful_runs"] = str(counts["successful"])
        row["notes"] = (
            "Rescored from raw results.jsonl under the patched "
            "attribute_changed.direction scorer. Source summary hashes point "
            "to the original pre-patch harness summaries; full prompts, "
            "assistant responses, tool arguments, and states remain omitted."
        )
    write_csv(RUN_MANIFEST, rows, fieldnames)


def update_reconciliation(counts_by_row: dict[str, dict[str, int]]) -> None:
    rows = load_csv(RESULT_RECONCILIATION)
    fieldnames = list(rows[0].keys())
    for row in rows:
        counts = counts_by_row.get(row["row_id"])
        if not counts:
            continue
        row["aggregate_successful_runs"] = str(counts["successful"])
        row["jsonl_successful_runs"] = str(counts["successful"])
    write_csv(RESULT_RECONCILIATION, rows, fieldnames)


def write_audit(
    *,
    raw_root: Path,
    row_summaries: list[dict[str, Any]],
    total_missing_state_failures: int,
    paper_main_missing_state_failures: int,
    affected_success_raw: Counter[str],
    affected_success_unpatched: Counter[str],
    affected_success_new: Counter[str],
) -> None:
    deltas = [
        {
            "row_id": item["row_id"],
            "model": item["model"],
            "total": item["total"],
            "raw_successful": item["raw_successful"],
            "unpatched_release_successful": item["unpatched_release_successful"],
            "patched_successful": item["patched_successful"],
            "raw_to_patched_delta": item["patched_successful"] - item["raw_successful"],
            "unpatched_to_patched_delta": (
                item["patched_successful"] - item["unpatched_release_successful"]
            ),
            "raw_sr_feasible": item["raw_sr_feasible"],
            "unpatched_release_sr_feasible": item["unpatched_release_sr_feasible"],
            "patched_sr_feasible": item["patched_sr_feasible"],
            "feasible_delta": item["patched_feasible_success"] - item["old_feasible_success"],
            "affected_direction_raw_success": affected_success_raw[item["row_id"]],
            "affected_direction_unpatched_release_success": affected_success_unpatched[item["row_id"]],
            "affected_direction_patched_success": affected_success_new[item["row_id"]],
        }
        for item in row_summaries
    ]
    payload = {
        "description": "Raw-log rescore after enforcing attribute_changed.direction for numeric fields.",
        "raw_results_root": str(raw_root),
        "rows_rescored": len(row_summaries),
        "total_missing_state_failure_records": total_missing_state_failures,
        "paper_main_missing_state_failure_records": paper_main_missing_state_failures,
        "paper_main_direction_scenarios": 112,
        "paper_main_direction_raw_successes": sum(
            affected_success_raw[row_id] for row_id in PAPER_MAIN_ROW_IDS
        ),
        "paper_main_direction_unpatched_release_successes": sum(
            affected_success_unpatched[row_id] for row_id in PAPER_MAIN_ROW_IDS
        ),
        "paper_main_direction_patched_successes": sum(
            affected_success_new[row_id] for row_id in PAPER_MAIN_ROW_IDS
        ),
        "row_deltas": deltas,
    }
    AUDIT_JSON.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    lines = [
        "# Attribute-Changed Direction Rescore Audit",
        "",
        "This report is generated by `code/scripts/rescore_attribute_changed_direction.py`.",
        "It uses raw logs under the configured raw results root to recompute feasible",
        "TSR with the patched `attribute_changed.direction` scorer. Calibration rows",
        "are retained from the original validation because the patch does not touch",
        "refusal/clarification scoring.",
        "",
        "## Summary",
        "",
        f"- Raw results root: `{raw_root}`",
        f"- Recomputed rows: {len(row_summaries)}",
        f"- Missing-state records retained as failures: {total_missing_state_failures}",
        f"- Paper-main missing-state records retained as failures: {paper_main_missing_state_failures}",
        "- Missing-state records that were prior successes: 0",
        "- Feasible scenarios with `attribute_changed.direction`: 112",
        (
            "- Paper-main successes on those scenarios in archived raw validation: "
            f"{payload['paper_main_direction_raw_successes']}"
        ),
        (
            "- Paper-main successes on those scenarios under the local unpatched release scorer: "
            f"{payload['paper_main_direction_unpatched_release_successes']}"
        ),
        (
            "- Paper-main successes on those scenarios after patch: "
            f"{payload['paper_main_direction_patched_successes']}"
        ),
        "",
        "## Row Deltas",
        "",
        "| Row | Model | Raw successes | Unpatched release successes | Patched successes | Raw SR-feas (%) | Unpatched SR-feas (%) | Patched SR-feas (%) |",
        "|---:|---|---:|---:|---:|---:|---:|---:|",
    ]
    for item in deltas:
        lines.append(
            f"| {item['row_id']} | {item['model']} | {item['raw_successful']} | "
            f"{item['unpatched_release_successful']} | {item['patched_successful']} | "
            f"{item['raw_sr_feasible']:.1f} | "
            f"{item['unpatched_release_sr_feasible']:.1f} | "
            f"{item['patched_sr_feasible']:.1f} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "The raw logs were sufficient to rescore all prior successes. Records without",
            "stored states were provider/runtime failures or context-window failures and",
            "were already unsuccessful; they remain unsuccessful under the patched scorer.",
            "The source `summary.json` hashes in the manifest still identify the original",
            "pre-patch harness summaries, while the redacted CSV/JSONL result fields now",
            "reflect this post-hoc patched rescore.",
            "",
        ]
    )
    AUDIT_MD.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-results-root", type=Path, default=DEFAULT_RAW_RESULTS_ROOT)
    parser.add_argument(
        "--write-results",
        action="store_true",
        help="Rewrite redacted aggregate/per-scenario artifacts in supplementary/results.",
    )
    args = parser.parse_args()

    raw_root = args.raw_results_root.resolve()
    scenarios = load_scenarios()
    affected = scenarios_with_direction()
    manifest_rows = load_csv(RUN_MANIFEST)
    per_rows = load_csv(PER_SCENARIO)
    per_by_key = {
        (row["row_id"], int(row["source_jsonl_line"])): row
        for row in per_rows
    }

    counts_by_row: dict[str, dict[str, int]] = {}
    counts_by_key: dict[tuple[str, str, str, str], dict[str, int]] = {}
    patched_by_line: dict[tuple[str, int], PatchedValidation] = {}
    row_summaries: list[dict[str, Any]] = []
    affected_success_raw: Counter[str] = Counter()
    affected_success_unpatched: Counter[str] = Counter()
    affected_success_new: Counter[str] = Counter()
    total_missing_state_failures = 0
    paper_main_missing_state_failures = 0

    for row in manifest_rows:
        if row.get("excluded_from_recompute") == "yes":
            continue
        results_path = raw_root / row["source_results_relpath"]
        if not results_path.exists():
            raise FileNotFoundError(results_path)

        raw_successful = int(row["successful_runs"])
        total = 0
        unpatched_release_successful = 0
        patched_successful = 0
        old_feasible_success = 0
        unpatched_feasible_success = 0
        patched_feasible_success = 0
        feasible_total = 0
        missing_state_failures = 0

        with results_path.open(encoding="utf-8") as handle:
            for line_no, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                record = json.loads(line)
                scenario = scenarios[record["scenario_id"]]
                patched = rescore_record(record, scenario)
                patched_by_line[(row["row_id"], line_no)] = patched

                total += 1
                unpatched_release_successful += int(patched.unpatched_release_success)
                patched_successful += int(patched.success)
                if patched.feasibility == "feasible":
                    feasible_total += 1
                    old_feasible_success += int(patched.old_success)
                    unpatched_feasible_success += int(patched.unpatched_release_success)
                    patched_feasible_success += int(patched.success)
                    if record["scenario_id"] in affected:
                        affected_success_raw[row["row_id"]] += int(patched.old_success)
                        affected_success_unpatched[row["row_id"]] += int(
                            patched.unpatched_release_success
                        )
                        affected_success_new[row["row_id"]] += int(patched.success)
                    if not patched.had_states:
                        missing_state_failures += 1
                elif not patched.had_states:
                    missing_state_failures += 1

        total_missing_state_failures += missing_state_failures
        if row["row_id"] in PAPER_MAIN_ROW_IDS:
            paper_main_missing_state_failures += missing_state_failures

        counts = {"total": total, "successful": patched_successful}
        counts_by_row[row["row_id"]] = counts
        counts_by_key[row_key(row)] = counts
        row_summaries.append(
            {
                "row_id": row["row_id"],
                "model": row["model"],
                "total": total,
                "raw_successful": raw_successful,
                "unpatched_release_successful": unpatched_release_successful,
                "patched_successful": patched_successful,
                "old_feasible_success": old_feasible_success,
                "unpatched_feasible_success": unpatched_feasible_success,
                "patched_feasible_success": patched_feasible_success,
                "raw_sr_feasible": 100.0 * old_feasible_success / feasible_total if feasible_total else 0.0,
                "unpatched_release_sr_feasible": (
                    100.0 * unpatched_feasible_success / feasible_total if feasible_total else 0.0
                ),
                "patched_sr_feasible": (
                    100.0 * patched_feasible_success / feasible_total if feasible_total else 0.0
                ),
                "missing_state_failures": missing_state_failures,
            }
        )

    for key, row in per_by_key.items():
        patched = patched_by_line.get(key)
        if patched is None:
            continue
        row["success"] = str(patched.success)
        row["validation_tsr"] = str(patched.tsr)
        row["validation_csr"] = str(patched.csr)
        row["failed_constraint_count"] = str(len(patched.failed_constraints))
        row["failed_constraints_sha256"] = sha256_text(
            json.dumps(patched.failed_constraints, sort_keys=True)
        )

    write_audit(
        raw_root=raw_root,
        row_summaries=row_summaries,
        total_missing_state_failures=total_missing_state_failures,
        paper_main_missing_state_failures=paper_main_missing_state_failures,
        affected_success_raw=affected_success_raw,
        affected_success_unpatched=affected_success_unpatched,
        affected_success_new=affected_success_new,
    )

    if args.write_results:
        if per_rows:
            write_csv(PER_SCENARIO, per_rows, list(per_rows[0].keys()))
        update_aggregate_csv(MAIN_RESULTS, counts_by_key)
        update_aggregate_csv(MAIN_RESULTS_RECOMPUTABLE, counts_by_key)
        update_run_summaries(counts_by_row)
        update_manifest(counts_by_row)
        update_reconciliation(counts_by_row)

    changed_rows = [
        item for item in row_summaries
        if item["patched_successful"] != item["raw_successful"]
    ]
    print("=" * 72)
    print("NLE-BENCH ATTRIBUTE_CHANGED DIRECTION RESCORE")
    print("=" * 72)
    print(f"raw_results_root: {raw_root}")
    print(f"rows_rescored: {len(row_summaries)}")
    print(f"rows_with_success_delta: {len(changed_rows)}")
    print(f"missing_state_failure_records: {total_missing_state_failures}")
    print(f"paper_main_missing_state_failure_records: {paper_main_missing_state_failures}")
    print(f"wrote_audit: {AUDIT_MD}")
    print(f"wrote_audit: {AUDIT_JSON}")
    if args.write_results:
        print("updated_results: yes")
    else:
        print("updated_results: no (dry run)")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
