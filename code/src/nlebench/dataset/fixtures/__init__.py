"""
NLEBench Fixtures

JSON-based fixtures using EditProject v4.3 schema.
"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Union

from nlebench.models import EditProject

# JSON fixtures directory
FIXTURES_DIR = Path(__file__).parent / "json"

# ──────────────────────────────────────────────
# JSON Fixture Loader (v4.3)
# ──────────────────────────────────────────────

JSON_FIXTURES = ["empty", "single_clip", "simple_sequence", "complex_sequence", "multi_sequence", "with_transitions"]


def load_base_fixture(name: str) -> EditProject:
    """Load a base JSON fixture by name."""
    path = FIXTURES_DIR / f"{name}.json"
    if not path.exists():
        raise ValueError(f"Unknown fixture: {name}. Available: {JSON_FIXTURES}")
    return EditProject.from_json(path.read_text(encoding="utf-8"))


def apply_patch(state: EditProject, patch: dict) -> None:
    """Apply a single patch operation to an EditProject.

    Supported ops:
    - Any canonical tool name (e.g., add_clip, add_effect): executes the tool
    - set_attribute: sets entity.field = value
    """
    from nlebench.tools.executor import execute_tool

    op = patch["op"]
    params = patch.get("params", {})

    if op == "set_attribute":
        entity_id = params["entity"]
        # Strip $ prefix if present (scenario convention)
        if entity_id.startswith("$"):
            entity_id = entity_id[1:]
        # Try to find entity across all collections (clips, tracks, media, timelines)
        entity = (
            state.get_clip_by_id(entity_id)
            or state.get_media_by_id(entity_id)
            or state.get_timeline_by_id(entity_id)
        )
        # Also search tracks
        if entity is None:
            for tl in state.timelines:
                for track in tl.tracks:
                    if track.id == entity_id:
                        entity = track
                        break
                if entity:
                    break
        if entity is None:
            raise ValueError(f"Patch target not found: {entity_id}")

        field = params["field"]
        value = params["value"]

        # Special handling for speed field (must be Speed object, not float)
        if field == "speed" and isinstance(value, (int, float)):
            from nlebench.models import Speed, SpeedPoint, Rational
            entity.speed = Speed(speed_map=[SpeedPoint(time=Rational(0, 1), rate=float(value))])
            return

        # Convert dict rational representations ({n, d}) to Rational objects
        # before setattr. Many YAML scenarios express durations/times this way
        # (e.g., `value: {n: 999, d: 1}`), which would otherwise crash to_dict()
        # calls downstream because dicts don't have a `.to_dict()` method.
        if isinstance(value, dict) and set(value.keys()) == {"n", "d"}:
            from nlebench.models import Rational
            value = Rational(int(value["n"]), int(value["d"]))

        # Field aliases for common mismatches
        FIELD_ALIASES = {
            "start": "timeline_start",
            "end": None,  # computed property, need special handling
            "text": None,  # read-only, need caption/title sub-object
        }
        if field in FIELD_ALIASES:
            alias = FIELD_ALIASES[field]
            if field == "text":
                # Set text on caption or title sub-object
                if hasattr(entity, "caption") and entity.caption:
                    entity.caption.text = value
                elif hasattr(entity, "title") and entity.title:
                    entity.title.text = value
                return
            elif field == "start":
                from nlebench.models import Rational
                entity.timeline_start = Rational.from_float(float(value)) if not isinstance(value, Rational) else value
                return
            elif field == "end":
                # Adjust duration to match desired end time
                from nlebench.models import Rational
                new_end = float(value)
                current_start = entity.timeline_start.to_float()
                entity.duration = Rational.from_float(new_end - current_start)
                return

        # Support nested field paths (e.g., "transform.opacity")
        if "." in field:
            parts = field.split(".")
            obj = entity
            for part in parts[:-1]:
                obj = getattr(obj, part, None)
                if obj is None:
                    # Create sub-object if needed (e.g., transform)
                    from nlebench.models import Transform, ClipAudio
                    if part == "transform":
                        obj = Transform()
                        setattr(entity, part, obj)
                    elif part == "audio":
                        obj = ClipAudio()
                        setattr(entity, part, obj)
                    else:
                        raise ValueError(f"Cannot create sub-object for: {part}")
            setattr(obj, parts[-1], value)
        else:
            setattr(entity, field, value)
    else:
        # Strip $ prefix from all string param values (including in lists)
        def resolve_val(v):
            if isinstance(v, str) and v.startswith("$"):
                return v[1:]
            if isinstance(v, list):
                return [resolve_val(x) for x in v]
            return v

        resolved_params = {k: resolve_val(v) for k, v in params.items()}

        # Map legacy/invalid tool names
        canonical_op = op
        if op == "add_entity":
            # Route by entity type
            etype = resolved_params.pop("type", "clip")
            resolved_params.pop("entity", None)  # remove synthetic entity ID
            if etype == "transition":
                canonical_op = "add_transition"
                between = resolved_params.pop("between", [])
                if len(between) >= 2:
                    resolved_params["clip_id_1"] = between[0]
                    resolved_params["clip_id_2"] = between[1]
                if "track_id" not in resolved_params:
                    resolved_params["track_id"] = "video_track_1"
            elif etype == "effect":
                canonical_op = "add_effect"
                # Remap clip -> clip_id
                if "clip" in resolved_params and "clip_id" not in resolved_params:
                    resolved_params["clip_id"] = resolved_params.pop("clip")
            elif etype == "media":
                canonical_op = "import_media"
                # Remap name -> file_path
                if "name" in resolved_params and "file_path" not in resolved_params:
                    resolved_params["file_path"] = f"/media/{resolved_params.pop('name')}"
            else:
                canonical_op = "add_clip"
        elif op == "create_bin":
            canonical_op = "manage_bin"

        if canonical_op == "manage_bin" and "action" not in resolved_params:
            resolved_params["action"] = "create"

        # Remap common param name mismatches across all tool calls
        if "entity" in resolved_params and "clip_id" not in resolved_params:
            if canonical_op in ("add_effect", "update_effect", "remove_effect",
                                "update_clip", "remove_clip", "split_clip"):
                resolved_params["clip_id"] = resolved_params.pop("entity")
        if "entity" in resolved_params and "caption_id" not in resolved_params:
            if canonical_op in ("update_caption", "remove_caption"):
                resolved_params["caption_id"] = resolved_params.pop("entity")

        result = execute_tool(state, canonical_op, resolved_params)
        if not result.get("success"):
            raise ValueError(f"Patch failed: {op} -> {result.get('error', 'unknown')}")


def build_fixture(fixture_spec: Union[str, dict]) -> EditProject:
    """Build an EditProject from a fixture spec.

    Args:
        fixture_spec: Either a fixture name (str) or a dict with 'base' and optional 'patch' list.

    Returns:
        EditProject instance.
    """
    if isinstance(fixture_spec, str):
        return load_base_fixture(fixture_spec)

    # Dict format: {"base": "simple_sequence", "patch": [{op, params}, ...]}
    state = load_base_fixture(fixture_spec["base"])
    for patch in fixture_spec.get("patch", []):
        apply_patch(state, patch)
    return state


# ──────────────────────────────────────────────
# Legacy name -> JSON fixture mapping (backwards compat)
# ──────────────────────────────────────────────

LEGACY_TO_JSON = {
    "basic_sequence": "simple_sequence",
    "single_clip_project": "single_clip",
    "multi_clip_project": "simple_sequence",
    "complex_project": "complex_sequence",
    "captions_project": "complex_sequence",
}


# ──────────────────────────────────────────────
# Unified Registry
# ──────────────────────────────────────────────

def get_fixture(name: str, perturb: bool = False, seed: int = 0) -> EditProject:
    """Get fixture by name.

    Supports:
    - JSON fixture names: empty, single_clip, simple_sequence, complex_sequence, multi_sequence
    - Legacy names: basic_sequence, single_clip_project, etc. (mapped to JSON fixtures)
    - Dict fixture spec: {"base": "...", "patch": [...]}

    Args:
        name: Fixture name or legacy name
        perturb: If True, randomize entity IDs (contamination defense)
        seed: Random seed for deterministic perturbation

    Returns:
        EditProject instance (v4.3 schema)
    """
    if isinstance(name, dict):
        state = build_fixture(name)
    elif name in JSON_FIXTURES:
        state = load_base_fixture(name)
    elif name in LEGACY_TO_JSON:
        state = load_base_fixture(LEGACY_TO_JSON[name])
    else:
        raise ValueError(
            f"Unknown fixture: {name}. "
            f"Available: {JSON_FIXTURES + list(LEGACY_TO_JSON.keys())}"
        )

    # TODO: Implement perturbation for v4.3 schema if needed
    # if perturb:
    #     state = perturb_project(state, seed=seed)

    return state


# Convenience re-exports
FIXTURE_REGISTRY = {name: name for name in JSON_FIXTURES}
FIXTURE_REGISTRY.update(LEGACY_TO_JSON)

__all__ = [
    "build_fixture",
    "load_base_fixture",
    "apply_patch",
    "get_fixture",
    "FIXTURE_REGISTRY",
    "JSON_FIXTURES",
]
