# Redacted Dev Trajectory Samples

`redacted_dev_trajectory_samples.jsonl` contains six representative raw-run
trajectory samples from existing local result files. All sampled scenarios are
from the v3.1 `dev` split.

## Scope

The sample spans:

- feasible execution success;
- feasible clarification failure;
- ambiguous clarification success;
- ambiguous execution failure;
- infeasible refusal success;
- infeasible execution failure.

Each JSONL record includes the scenario ID, split, taxonomy, dev instruction
turns, model/run provenance, source JSONL line, raw record hash, validation
summary, tool-call names and arguments, and full dev initial/final state JSON.
Provider call IDs and the full raw record wrapper are omitted.

## Redactions

Assistant responses are not released in full. Each record includes a response
SHA256 and, when the visible final answer is short and contains no reasoning
trace, a short final-answer excerpt. Chain-of-thought is not included.

The file contains no private/test prompts, private/test states, private/test raw
responses, private/test tool traces, or response-level refusal-audit judge
labels. The refusal-audit labels remain absent from this anonymous bundle, as
documented in `refusal_audit_status.json`.

## Provenance

Source paths are relative to the raw results root used during artifact
preparation, `<raw-results-root>`, and are also
listed in `run_manifest.csv`. Hashes use SHA256 over the raw `results.jsonl`
line or raw state/response string, matching the redaction convention used by
`generate_review_artifacts.py`.
