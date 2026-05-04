"""Generate reviewer-facing audit artifacts.

Inputs:
- supplementary/results/main_results.csv
- raw harness outputs under NLEBENCH_RAW_RESULTS_ROOT
- supplementary/data/human_study.json
- scripts/hstudy_tmp/per_row_provenance_2026-04-26.csv, when present
- v3 and v3.1 scenario directories, when both are present

Outputs are redacted: no prompts, full assistant responses, full initial/final
states, or tool arguments are written. Hashes retain audit linkage without
including prompt-fingerprintable content.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
from pathlib import Path
from typing import Any

import yaml


SUPPLEMENTARY_ROOT = Path(__file__).resolve().parents[2]
CODE_ROOT = SUPPLEMENTARY_ROOT / "code"
REPO_ROOT = SUPPLEMENTARY_ROOT.parent
RAW_RESULTS_ROOT = Path(
    os.environ.get("NLEBENCH_RAW_RESULTS_ROOT", str(REPO_ROOT / "raw_results"))
)

MAIN_RESULTS = SUPPLEMENTARY_ROOT / "results" / "main_results.csv"
RUN_MANIFEST = SUPPLEMENTARY_ROOT / "results" / "run_manifest.csv"
RUN_SUMMARIES = SUPPLEMENTARY_ROOT / "results" / "run_summaries_redacted.jsonl"
PER_SCENARIO = SUPPLEMENTARY_ROOT / "results" / "per_scenario_results_redacted.csv"
RESULT_RECONCILIATION = SUPPLEMENTARY_ROOT / "results" / "result_reconciliation.csv"
SCENARIO_FILE_MANIFEST = SUPPLEMENTARY_ROOT / "results" / "scenario_v3_to_v3_1_file_manifest.csv"
HUMAN_STUDY_JSON = SUPPLEMENTARY_ROOT / "data" / "human_study.json"
HUMAN_PROVENANCE_SOURCE = REPO_ROOT / "scripts" / "hstudy_tmp" / "per_row_provenance_2026-04-26.csv"
HUMAN_PROVENANCE_OUT = SUPPLEMENTARY_ROOT / "data" / "human_study_per_row_provenance.csv"
SCENARIO_V3 = CODE_ROOT / "src" / "nlebench" / "dataset" / "scenarios_v3"
SCENARIO_V31 = CODE_ROOT / "src" / "nlebench" / "dataset" / "scenarios_v3_1"

NONRECOMPUTABLE_RUNS = {
    (
        "gemini-3.1-pro-preview",
        "2026-04-24T11:58:59.308395",
    ): (
        "Matched raw results.jsonl is corrupted/inconsistent with the "
        "aggregate summary: 842 valid JSON rows + 1 malformed line with "
        "5 successes, while summary/main_results report 800 rows and "
        "38 successes. No clean replacement source was found during Round 6."
    ),
}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def artifact_ref(path: Path) -> str:
    try:
        return path.resolve().relative_to(SUPPLEMENTARY_ROOT.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def raw_ref(path: Path) -> str:
    try:
        return path.resolve().relative_to(RAW_RESULTS_ROOT.resolve()).as_posix()
    except ValueError:
        return path.name


def run_exclusion_reason(row: dict[str, str]) -> str:
    return NONRECOMPUTABLE_RUNS.get((row["model"], row["timestamp"]), "")


def load_main_rows() -> list[dict[str, str]]:
    with MAIN_RESULTS.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for idx, row in enumerate(rows, start=1):
        row["row_id"] = str(idx)
    return rows


def load_summary_index() -> list[tuple[Path, dict[str, Any]]]:
    out: list[tuple[Path, dict[str, Any]]] = []
    for path in sorted(RAW_RESULTS_ROOT.rglob("summary.json")):
        try:
            out.append((path, json.loads(path.read_text(encoding="utf-8"))))
        except Exception:
            continue
    return out


def summary_matches(row: dict[str, str], summary: dict[str, Any]) -> bool:
    keys = ("model", "provider", "track", "timestamp")
    if all(str(summary.get(k, "")) == row[k] for k in keys):
        return True
    if not all(str(summary.get(k, "")) == row[k] for k in ("model", "provider", "track")):
        return False
    try:
        return (
            int(summary.get("total_runs", -1)) == int(row["total_runs"])
            and int(summary.get("successful_runs", -1)) == int(row["successful_runs"])
            and abs(float(summary.get("sr", -1)) - float(row["sr"])) < 1e-4
        )
    except Exception:
        return False


def find_run_matches(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    summaries = load_summary_index()
    matches: list[dict[str, Any]] = []
    for row in rows:
        found = [(p, s) for p, s in summaries if summary_matches(row, s)]
        if len(found) != 1:
            raise RuntimeError(
                f"Expected exactly one raw summary match for row {row['row_id']} "
                f"{row['model']} {row['timestamp']}, found {len(found)}"
            )
        summary_path, summary = found[0]
        results_path = summary_path.with_name("results.jsonl")
        if not results_path.exists():
            raise RuntimeError(f"Matched summary has no results.jsonl: {summary_path}")
        matches.append({
            "row": row,
            "summary": summary,
            "summary_path": summary_path,
            "results_path": results_path,
            "summary_sha256": sha256_file(summary_path),
            "results_sha256": sha256_file(results_path),
        })
    return matches


def load_scenario_meta() -> dict[str, dict[str, str]]:
    meta: dict[str, dict[str, str]] = {}
    for path in sorted(SCENARIO_V31.rglob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        taxonomy = data.get("taxonomy") or {}
        info = taxonomy.get("information") or ""
        action = taxonomy.get("action") or ""
        feasibility = taxonomy.get("feasibility") or data.get("feasibility") or ""
        item = {
            "scenario_id": data["id"],
            "legacy_scenario_id": data.get("legacy_id") or "",
            "split": data.get("split") or "",
            "scale": taxonomy.get("scale") or data.get("level") or "",
            "feasibility": feasibility,
            "information": info,
            "action": action,
            "cell": f"{info}/{action}" if feasibility == "feasible" else f"{feasibility}/{info}",
            "scenario_relpath": artifact_ref(path),
        }
        meta[data["id"]] = item
        if data.get("legacy_id"):
            meta[data["legacy_id"]] = item
    return meta


def compact_error(value: Any) -> str:
    if not value:
        return ""
    text = str(value).splitlines()[0]
    return text[:160]


def write_result_artifacts(matches: list[dict[str, Any]]) -> None:
    scenario_meta = load_scenario_meta()
    RUN_SUMMARIES.parent.mkdir(parents=True, exist_ok=True)

    per_fields = [
        "row_id", "model", "provider", "track", "run_id", "run_number",
        "source_jsonl_line", "scenario_id", "legacy_scenario_id", "split", "scale",
        "scenario_feasibility", "information", "action", "cell",
        "success", "validation_tsr", "validation_csr", "validation_ovr",
        "validation_feasibility", "state_changed", "refusal_appropriate",
        "asked_clarification", "behavior", "failed_constraint_count",
        "failed_constraints_sha256", "latency_ms", "input_tokens",
        "output_tokens", "token_usage", "cost_usd", "tool_call_count",
        "tool_names", "tool_names_sha256", "agent_response_sha256",
        "initial_state_sha256", "final_state_sha256", "raw_record_sha256",
        "error_message_type", "source_results_sha256",
    ]

    manifest_fields = [
        "row_id", "model", "provider", "track", "timestamp", "total_runs",
        "successful_runs", "sr", "aggregate_csv",
        "included_summary_artifact", "included_per_scenario_artifact",
        "source_summary_relpath", "source_results_relpath",
        "source_summary_sha256", "source_results_sha256",
        "valid_jsonl_rows", "redacted_rows_written",
        "redacted_successful_runs", "malformed_jsonl_lines",
        "recompute_status", "excluded_from_recompute", "exclusion_reason",
        "per_call_logs_included", "full_tool_args_included",
        "full_agent_responses_included", "full_states_included", "notes",
    ]
    reconciliation_fields = [
        "row_id", "model", "provider", "track", "timestamp",
        "aggregate_total_runs", "aggregate_successful_runs",
        "valid_jsonl_rows", "redacted_rows_written",
        "jsonl_successful_runs", "malformed_jsonl_lines",
        "recompute_status", "exclusion_reason",
    ]

    with (
        RUN_SUMMARIES.open("w", encoding="utf-8") as summaries_f,
        PER_SCENARIO.open("w", newline="", encoding="utf-8") as per_f,
        RUN_MANIFEST.open("w", newline="", encoding="utf-8") as manifest_f,
        RESULT_RECONCILIATION.open("w", newline="", encoding="utf-8") as reconciliation_f,
    ):
        per_writer = csv.DictWriter(per_f, fieldnames=per_fields)
        per_writer.writeheader()
        manifest_writer = csv.DictWriter(manifest_f, fieldnames=manifest_fields)
        manifest_writer.writeheader()
        reconciliation_writer = csv.DictWriter(
            reconciliation_f, fieldnames=reconciliation_fields
        )
        reconciliation_writer.writeheader()

        for match in matches:
            row = match["row"]
            summary = match["summary"]
            run_id = Path(match["summary_path"]).parent.name
            exclusion_reason = run_exclusion_reason(row)
            excluded = bool(exclusion_reason)
            malformed_lines = 0
            valid_rows = 0
            success_rows = 0
            redacted_rows: list[dict[str, Any]] = []

            with Path(match["results_path"]).open(encoding="utf-8") as f:
                for line_no, line in enumerate(f, start=1):
                    if not line.strip():
                        continue
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        malformed_lines += 1
                        continue
                    valid_rows += 1
                    if str(record.get("success", "")).lower() == "true":
                        success_rows += 1
                    validation = record.get("validation") or {}
                    sid = record.get("scenario_id", "")
                    meta = scenario_meta.get(sid, {})
                    failed = validation.get("failed_constraints") or []
                    tool_calls = record.get("tool_calls") or []
                    tool_names = [
                        str(tc.get("name", "")) for tc in tool_calls
                        if isinstance(tc, dict) and tc.get("name")
                    ]
                    redacted_rows.append({
                        "row_id": row["row_id"],
                        "model": row["model"],
                        "provider": row["provider"],
                        "track": row["track"],
                        "run_id": run_id,
                        "run_number": record.get("run_number", ""),
                        "source_jsonl_line": line_no,
                        "scenario_id": meta.get("scenario_id", sid),
                        "legacy_scenario_id": meta.get("legacy_scenario_id", ""),
                        "split": meta.get("split", ""),
                        "scale": meta.get("scale", ""),
                        "scenario_feasibility": meta.get("feasibility", ""),
                        "information": meta.get("information", ""),
                        "action": meta.get("action", ""),
                        "cell": meta.get("cell", ""),
                        "success": record.get("success", ""),
                        "validation_tsr": validation.get("tsr", ""),
                        "validation_csr": validation.get("csr", ""),
                        "validation_ovr": validation.get("ovr", ""),
                        "validation_feasibility": validation.get("feasibility", ""),
                        "state_changed": validation.get("state_changed", ""),
                        "refusal_appropriate": validation.get("refusal_appropriate", ""),
                        "asked_clarification": validation.get("asked_clarification", ""),
                        "behavior": validation.get("behavior", ""),
                        "failed_constraint_count": len(failed),
                        "failed_constraints_sha256": sha256_text(json.dumps(failed, sort_keys=True)),
                        "latency_ms": record.get("latency_ms", ""),
                        "input_tokens": record.get("input_tokens", ""),
                        "output_tokens": record.get("output_tokens", ""),
                        "token_usage": record.get("token_usage", ""),
                        "cost_usd": record.get("cost_usd", ""),
                        "tool_call_count": len(tool_calls),
                        "tool_names": ";".join(tool_names),
                        "tool_names_sha256": sha256_text(json.dumps(tool_names, sort_keys=True)),
                        "agent_response_sha256": sha256_text(record.get("agent_response") or ""),
                        "initial_state_sha256": sha256_text(record.get("initial_state_json") or ""),
                        "final_state_sha256": sha256_text(record.get("final_state_json") or ""),
                        "raw_record_sha256": sha256_text(line.rstrip("\n")),
                        "error_message_type": compact_error(
                            record.get("error_message") or validation.get("error_message")
                        ),
                        "source_results_sha256": match["results_sha256"],
                    })

            expected_total = int(row["total_runs"])
            expected_success = int(row["successful_runs"])
            if excluded:
                recompute_status = "excluded_nonrecomputable"
                rows_to_write: list[dict[str, Any]] = []
            elif (
                valid_rows == expected_total
                and success_rows == expected_success
                and malformed_lines == 0
            ):
                recompute_status = "reconciled"
                rows_to_write = redacted_rows
            else:
                raise RuntimeError(
                    "Result reconciliation failed for row "
                    f"{row['row_id']} {row['model']} {row['timestamp']}: "
                    f"aggregate={expected_success}/{expected_total}, "
                    f"jsonl={success_rows}/{valid_rows}, "
                    f"malformed={malformed_lines}"
                )

            for redacted_row in rows_to_write:
                per_writer.writerow(redacted_row)

            reconciliation_writer.writerow({
                "row_id": row["row_id"],
                "model": row["model"],
                "provider": row["provider"],
                "track": row["track"],
                "timestamp": row["timestamp"],
                "aggregate_total_runs": expected_total,
                "aggregate_successful_runs": expected_success,
                "valid_jsonl_rows": valid_rows,
                "redacted_rows_written": len(rows_to_write),
                "jsonl_successful_runs": success_rows,
                "malformed_jsonl_lines": malformed_lines,
                "recompute_status": recompute_status,
                "exclusion_reason": exclusion_reason,
            })

            summary_record = {
                "row_id": int(row["row_id"]),
                **{k: summary.get(k) for k in (
                    "model", "provider", "track", "total_runs",
                    "successful_runs", "sr", "timestamp"
                )},
                "source_summary_relpath": raw_ref(match["summary_path"]),
                "source_results_relpath": raw_ref(match["results_path"]),
                "source_summary_sha256": match["summary_sha256"],
                "source_results_sha256": match["results_sha256"],
                "valid_jsonl_rows": valid_rows,
                "redacted_rows_written": len(rows_to_write),
                "redacted_successful_runs": success_rows if not excluded else "",
                "malformed_jsonl_lines": malformed_lines,
                "recompute_status": recompute_status,
                "excluded_from_recompute": excluded,
                "exclusion_reason": exclusion_reason,
            }
            summaries_f.write(json.dumps(summary_record, sort_keys=True) + "\n")

            manifest_writer.writerow({
                "row_id": row["row_id"],
                "model": row["model"],
                "provider": row["provider"],
                "track": row["track"],
                "timestamp": row["timestamp"],
                "total_runs": row["total_runs"],
                "successful_runs": row["successful_runs"],
                "sr": row["sr"],
                "aggregate_csv": artifact_ref(MAIN_RESULTS),
                "included_summary_artifact": artifact_ref(RUN_SUMMARIES),
                "included_per_scenario_artifact": artifact_ref(PER_SCENARIO),
                "source_summary_relpath": raw_ref(match["summary_path"]),
                "source_results_relpath": raw_ref(match["results_path"]),
                "source_summary_sha256": match["summary_sha256"],
                "source_results_sha256": match["results_sha256"],
                "valid_jsonl_rows": valid_rows,
                "redacted_rows_written": len(rows_to_write),
                "redacted_successful_runs": success_rows if not excluded else "",
                "malformed_jsonl_lines": malformed_lines,
                "recompute_status": recompute_status,
                "excluded_from_recompute": "yes" if excluded else "no",
                "exclusion_reason": exclusion_reason,
                "per_call_logs_included": "redacted_fields_only",
                "full_tool_args_included": "no",
                "full_agent_responses_included": "no",
                "full_states_included": "no",
                "notes": exclusion_reason or (
                    "Included artifacts contain aggregate summaries and "
                    "per-scenario/per-run validation fields. Full prompts, "
                    "assistant responses, tool arguments, and states are "
                    "omitted; hashes preserve linkage to raw internal files."
                ),
            })


def write_human_provenance() -> None:
    if not HUMAN_PROVENANCE_SOURCE.exists():
        return

    records = json.loads(HUMAN_STUDY_JSON.read_text(encoding="utf-8"))
    by_key: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for record in records:
        for sid in (record.get("scenario_id"), record.get("legacy_scenario_id")):
            if sid:
                key = (sid, record["layer"], record["created_at"])
                by_key.setdefault(key, []).append(record)

    fields = [
        "human_study_id", "layer", "rater", "scenario_id", "legacy_scenario_id",
        "provenance", "response_match", "created_at", "updated_at",
        "source_evaluator_sha256",
    ]
    with (
        HUMAN_PROVENANCE_SOURCE.open(newline="", encoding="utf-8") as in_f,
        HUMAN_PROVENANCE_OUT.open("w", newline="", encoding="utf-8") as out_f,
    ):
        reader = csv.DictReader(in_f)
        writer = csv.DictWriter(out_f, fieldnames=fields)
        writer.writeheader()
        for row in reader:
            key = (row["scenarioId"], row["layer"], row["created_at"])
            candidates = by_key.get(key) or []
            record = candidates[0] if candidates else {}
            writer.writerow({
                "human_study_id": record.get("id", ""),
                "layer": row["layer"],
                "rater": record.get("rater", "unmatched"),
                "scenario_id": record.get("scenario_id", row["scenarioId"]),
                "legacy_scenario_id": record.get("legacy_scenario_id", ""),
                "provenance": row["provenance"],
                "response_match": row["response_match"],
                "created_at": row["created_at"],
                "updated_at": record.get("updated_at", ""),
                "source_evaluator_sha256": sha256_text(row.get("evaluatorId", "")),
            })


def file_hash_or_empty(path: Path) -> str:
    return sha256_file(path) if path.exists() else ""


def write_scenario_file_manifest() -> None:
    if not (SCENARIO_V3.exists() and SCENARIO_V31.exists()):
        return
    rows: list[dict[str, str]] = []
    rels = {
        p.relative_to(SCENARIO_V3).as_posix() for p in SCENARIO_V3.rglob("*.yaml")
    } | {
        p.relative_to(SCENARIO_V31).as_posix() for p in SCENARIO_V31.rglob("*.yaml")
    }
    for rel in sorted(rels):
        p3 = SCENARIO_V3 / rel
        p31 = SCENARIO_V31 / rel
        sha3 = file_hash_or_empty(p3)
        sha31 = file_hash_or_empty(p31)
        rows.append({
            "relpath": rel,
            "present_in_v3": str(p3.exists()).lower(),
            "present_in_v3_1": str(p31.exists()).lower(),
            "v3_sha256": sha3,
            "v3_1_sha256": sha31,
            "changed": str(sha3 != sha31).lower(),
        })
    with SCENARIO_FILE_MANIFEST.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "relpath", "present_in_v3", "present_in_v3_1",
            "v3_sha256", "v3_1_sha256", "changed",
        ])
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    rows = load_main_rows()
    matches = find_run_matches(rows)
    write_result_artifacts(matches)
    write_human_provenance()
    write_scenario_file_manifest()
    print(f"matched_run_rows={len(matches)}")
    print(f"wrote={artifact_ref(RUN_MANIFEST)}")
    print(f"wrote={artifact_ref(RUN_SUMMARIES)}")
    print(f"wrote={artifact_ref(PER_SCENARIO)}")
    print(f"wrote={artifact_ref(RESULT_RECONCILIATION)}")
    with RESULT_RECONCILIATION.open(newline="", encoding="utf-8") as f:
        recon_rows = list(csv.DictReader(f))
    print(
        "reconciliation="
        f"reconciled:{sum(r['recompute_status'] == 'reconciled' for r in recon_rows)},"
        f"excluded:{sum(r['recompute_status'].startswith('excluded') for r in recon_rows)}"
    )
    if HUMAN_PROVENANCE_OUT.exists():
        print(f"wrote={artifact_ref(HUMAN_PROVENANCE_OUT)}")
    if SCENARIO_FILE_MANIFEST.exists():
        print(f"wrote={artifact_ref(SCENARIO_FILE_MANIFEST)}")


if __name__ == "__main__":
    main()
