"""
NLEBench Reliability Metrics

Measures system stability and consistency.
CSR (Compile Success Rate), OVR (Over-edit Violation Rate).
"""

from __future__ import annotations

from dataclasses import fields as dc_fields
from typing import Any, Optional

from nlebench.models import EditProject, ExecutionResult, Rational


# ============================================================
# OVR: Entity-level semantic diff (v2, spec-aligned)
# ============================================================

# Field-specific tolerances for semantic equality
_TOLERANCE = {
    "start": 0.05,
    "end": 0.05,
    "timeline_start": 0.05,  # v4.3 field name
    "in_point": 0.05,
    "out_point": 0.05,
    "duration": 0.05,
    "volume": 0.5,
    "speed": 0.01,
}


def _entity_semantically_equal(a: Any, b: Any) -> bool:
    """Check if two entities are semantically equal with tolerance.

    Skips nested list fields since those are compared at their entity level.
    Handles Rational objects by comparing their float values with tolerance.
    """
    if type(a) is not type(b):
        return False

    # Fields that contain child entities - skip these
    # Note: native is NOT skipped because adding effects to a clip is a semantic change
    nested_fields = {"clips", "tracks", "transitions", "bins", "media", "timelines"}

    for f in dc_fields(a):
        if f.name.startswith("_"):
            continue
        if f.name in nested_fields:
            continue  # Skip nested entity lists
        v1 = getattr(a, f.name, None)
        v2 = getattr(b, f.name, None)

        # Handle Rational objects by converting to float
        if isinstance(v1, Rational) and isinstance(v2, Rational):
            tol = _TOLERANCE.get(f.name, 1e-6)
            if abs(v1.to_float() - v2.to_float()) > tol:
                return False
        elif isinstance(v1, float) and isinstance(v2, float):
            tol = _TOLERANCE.get(f.name, 1e-6)
            if abs(v1 - v2) > tol:
                return False
        elif isinstance(v1, list) and isinstance(v2, list):
            # Compare native lists by length and content (effects are semantic changes)
            if f.name == "native":
                if len(v1) != len(v2):
                    return False
                # Simple: if lengths match, check if all elements match by type/data
                for n1, n2 in zip(v1, v2):
                    if type(n1) is not type(n2):
                        return False
                    if getattr(n1, "type", None) != getattr(n2, "type", None):
                        return False
                    if getattr(n1, "data", None) != getattr(n2, "data", None):
                        return False
            # Skip other list fields (child entities compared separately)
            continue
        elif v1 != v2:
            return False
    return True


def _collect_entities(state: EditProject) -> dict[str, Any]:
    """Collect all entities as {id: entity} dict (v4.3 compatible)."""
    entities: dict[str, Any] = {}

    # Entity lists that have .id attribute
    for list_name in [
        "bins", "media", "timelines",
        "video_tracks", "audio_tracks",
        "video_clips", "audio_clips", "captions",
        "transitions",
    ]:
        for e in getattr(state, list_name, []):
            eid = getattr(e, "id", None)
            if eid:
                entities[eid] = e

    return entities


def calculate_ovr_entity_diff(
    initial_state: EditProject,
    final_state: EditProject,
    expected_changed: list[str],
) -> float:
    """
    Calculate OVR using entity-level semantic diff (metrics_spec.md §4).

    OVR = unexpected_changes / total_entities

    Where:
    - total_entities = |initial_entities|
    - unexpected = modified/deleted/added entities NOT in expected_changed
    """
    expected_set = set(expected_changed)
    initial_entities = _collect_entities(initial_state)
    final_entities = _collect_entities(final_state)

    total = len(initial_entities)
    if total == 0:
        return 0.0

    unexpected = 0

    # Modified entities
    for eid, initial_entity in initial_entities.items():
        if eid in final_entities:
            if not _entity_semantically_equal(initial_entity, final_entities[eid]):
                if eid not in expected_set:
                    unexpected += 1

    # Deleted entities
    for eid in initial_entities:
        if eid not in final_entities and eid not in expected_set:
            unexpected += 1

    # Added entities
    for eid in final_entities:
        if eid not in initial_entities and eid not in expected_set:
            unexpected += 1

    return unexpected / total


# ============================================================
# CSR: Compile Success Rate with validity checks
# ============================================================

def validate_edit_project(state: EditProject) -> tuple[bool, list[str]]:
    """
    Validate EditProject structural integrity (v4.3 schema).

    Checks:
    1. Reference integrity (all ref_id valid)
    2. No duplicate IDs
    3. Transition references valid

    Returns:
        (valid, errors) tuple
    """
    errors: list[str] = []
    all_ids = state.collect_all_ids()

    # Check for duplicate IDs
    if len(all_ids) != len(set(all_ids)):
        seen: set[str] = set()
        for eid in all_ids:
            if eid in seen:
                errors.append(f"Duplicate entity ID: {eid}")
            seen.add(eid)

    # Reference integrity: clip references (v4.3: ref_id instead of media_id)
    media_ids = {m.id for m in state.media}
    timeline_ids = {t.id for t in state.timelines}
    valid_refs = media_ids | timeline_ids

    for clip in state.video_clips + state.audio_clips:
        ref_id = getattr(clip, "ref_id", None)
        if ref_id and ref_id not in valid_refs:
            errors.append(f"Clip {clip.id} references missing media/timeline {ref_id}")

    # Reference integrity: transition clip_ids (v4.3: clip_before_id, clip_after_id)
    clip_ids = {c.id for c in state.video_clips + state.audio_clips + state.captions}
    for t in state.transitions:
        before_id = getattr(t, "clip_before_id", None)
        after_id = getattr(t, "clip_after_id", None)
        if before_id and before_id not in clip_ids:
            errors.append(f"Transition {t.id} references missing clip {before_id}")
        if after_id and after_id not in clip_ids:
            errors.append(f"Transition {t.id} references missing clip {after_id}")

    return len(errors) == 0, errors


def calculate_csr(results: list[ExecutionResult]) -> float:
    """
    Calculate Compile Success Rate (CSR).

    CSR = Number of successfully compiled outputs / Total outputs

    A compile is successful if the EditState can be converted to valid XML.

    Args:
        results: List of execution results

    Returns:
        CSR as a float between 0.0 and 1.0
    """
    if not results:
        return 0.0

    successful = sum(1 for r in results if r.validation.csr)
    return successful / len(results)


def calculate_ovr(results: list[ExecutionResult]) -> float:
    """
    Calculate average Over-edit Violation Rate (OVR).

    OVR measures unintended entity changes via entity-level semantic diff:
    - 0.0 = No over-edits (ideal)
    - 1.0 = All entities were over-edited (worst)

    Args:
        results: List of execution results

    Returns:
        Average OVR across all results
    """
    if not results:
        return 0.0

    total_ovr = sum(r.validation.ovr for r in results)
    return total_ovr / len(results)


def calculate_reliability_score(results: list[ExecutionResult]) -> float:
    """
    Calculate combined reliability score.

    Weighted combination:
    - CSR: 60% weight
    - (1 - OVR): 40% weight (inverted so higher is better)

    Args:
        results: List of execution results

    Returns:
        Reliability score between 0.0 and 1.0
    """
    csr = calculate_csr(results)
    ovr = calculate_ovr(results)

    return csr * 0.60 + (1 - ovr) * 0.40
