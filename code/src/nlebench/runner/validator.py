"""
NLEBench Constraint Validator

Validates that the final EditProject satisfies the scenario constraints.
Based on WebArena's Constraint Satisfaction approach.

Updated for EditProject v4.3 schema.
"""

import re
from dataclasses import fields as dc_fields, is_dataclass
from typing import Any, Optional

from nlebench.models import (
    EditProject,
    Clip,
    Track,
    Timeline,
    Media,
    Bin,
    Constraint,
    ConstraintType,
    Operator,
    Scenario,
    ValidationResult,
)


class ConstraintValidator:
    """
    Validates constraints against EditProject.

    Supports JSONPath-like field selectors and various operators
    for flexible constraint specification.
    """

    def __init__(self):
        self._compile_errors: list[str] = []

    def validate(
        self,
        initial_state: EditProject,
        final_state: EditProject,
        scenario: Scenario,
    ) -> ValidationResult:
        """
        Validate all constraints for a scenario.

        Args:
            initial_state: EditProject before agent execution
            final_state: EditProject after agent execution
            scenario: Scenario with constraints to validate

        Returns:
            ValidationResult with all metrics
        """
        failed_constraints: list[str] = []

        # Check named constraints first (v2 format: dict-based)
        named_required = scenario.named_constraints_required
        named_specified = scenario.named_constraints_specified

        if named_required or named_specified:
            # Use named constraint evaluation
            try:
                from nlebench.runner.constraints import validate_named_constraints
                named_tsr, eval_result = validate_named_constraints(
                    initial_state, final_state, scenario
                )
                if not named_tsr:
                    for cr in eval_result.results:
                        if not cr.passed:
                            failed_constraints.append(
                                f"named:{cr.func_name}:{cr.error or 'failed'}"
                            )
            except Exception as e:
                # Log but don't crash — allow post-hoc revalidation
                failed_constraints.append(f"validation_error:{str(e)[:100]}")
        else:
            # Fallback to legacy constraints (Constraint objects)
            for constraint in scenario.required_constraints:
                if not self._check_constraint(initial_state, final_state, constraint):
                    failed_constraints.append(
                        f"required:{constraint.field}.{constraint.operator.value}"
                    )

            for constraint in scenario.specified_constraints:
                if not self._check_constraint(initial_state, final_state, constraint):
                    failed_constraints.append(
                        f"specified:{constraint.field}.{constraint.operator.value}"
                    )

            for constraint in scenario.validity_constraints:
                if not self._check_constraint(initial_state, final_state, constraint):
                    failed_constraints.append(
                        f"validity:{constraint.field}.{constraint.operator.value}"
                    )

        # Calculate metrics
        tsr = len(failed_constraints) == 0
        csr = self._check_compile_success(final_state)
        ovr = self._calculate_ovr(initial_state, final_state, scenario)

        return ValidationResult(
            tsr=tsr,
            csr=csr,
            ovr=ovr,
            failed_constraints=failed_constraints,
        )

    def _check_constraint(
        self,
        initial_state: EditProject,
        final_state: EditProject,
        constraint: Constraint,
    ) -> bool:
        """Check a single constraint."""
        try:
            # Special operators that don't need field value
            if constraint.operator == Operator.NO_OVERLAP:
                return self._check_no_overlap(final_state)

            if constraint.operator == Operator.COMPILE_SUCCESS:
                return self._check_compile_success(final_state)

            if constraint.operator == Operator.COUNT_CHANGED:
                initial_value = self._get_field_value(initial_state, constraint.field)
                final_value = self._get_field_value(final_state, constraint.field)
                initial_count = len(initial_value) if isinstance(initial_value, list) else 0
                final_count = len(final_value) if isinstance(final_value, list) else 0
                return initial_count != final_count

            # Get field value from final state
            value = self._get_field_value(final_state, constraint.field)

            return self._apply_operator(value, constraint)

        except Exception as e:
            # Log error but don't crash
            self._compile_errors.append(f"Error checking {constraint.field}: {e}")
            return False

    def _get_field_value(self, state: EditProject, field: str) -> Any:
        """
        Get field value from EditProject using JSONPath-like selector.

        Supported patterns (v4.3 naming):
        - "clips.caption" -> all caption clips
        - "clips.caption.text" -> text field of caption clips
        - "clips.video" -> all video clips
        - "clips.audio" -> all audio clips
        - "tracks.video" -> all video tracks
        - "tracks.audio" -> all audio tracks
        - "timelines" -> all timelines
        - "media" -> all media

        Legacy patterns (still supported):
        - "captions" -> clips.caption
        - "video_clips" -> clips.video
        - "audio_clips" -> clips.audio
        """
        # Normalize legacy names to v4.3 naming
        field = self._normalize_field_name(field)

        # Try to parse as typed collection (e.g., "clips.video", "tracks.audio")
        collection_name, type_filter, nested_field = self._parse_typed_field(field)

        # Handle index selectors like "clips.video[-1]" or "clips.video[0]"
        # The collection_name might be "clips.video[0]" so we extract base and index
        index_match = re.match(r"(.+)\[(-?\d+)\]$", collection_name)
        if index_match:
            base_collection = index_match.group(1)  # e.g., "clips.video"
            index = int(index_match.group(2))
            # Extract the base collection name (e.g., "clips" from "clips.video")
            base_parts = base_collection.split(".")
            actual_collection_name = base_parts[0]  # "clips"
            collection = self._get_collection(state, actual_collection_name, type_filter)
            if collection is None or not isinstance(collection, list):
                return None
            try:
                item = collection[index]
            except IndexError:
                return None
            if not nested_field:
                return item
            return self._get_nested_value(item, nested_field)

        # Handle wildcards like "clips[*]"
        if "[*]" in collection_name:
            collection_name = collection_name.replace("[*]", "")

        # Extract the base collection name for _get_collection
        # e.g., "clips.video" -> "clips"
        base_parts = collection_name.split(".")
        actual_collection_name = base_parts[0]

        # Get collection with optional type filter
        collection = self._get_collection(state, actual_collection_name, type_filter)

        if collection is None:
            return None

        # If no nested field, return the collection
        if not nested_field:
            return collection

        # Handle wildcards in nested field
        if "[*]" in nested_field:
            nested_field = nested_field.replace("[*]", "")

        # Handle array fields
        if isinstance(collection, list):
            return [self._get_nested_value(item, nested_field) for item in collection]

        return self._get_nested_value(collection, nested_field)

    def _normalize_field_name(self, field: str) -> str:
        """Normalize legacy field names to v4.3 naming."""
        # Map legacy names
        legacy_map = {
            "captions": "clips.caption",
            "video_clips": "clips.video",
            "audio_clips": "clips.audio",
            "video_tracks": "tracks.video",
            "audio_tracks": "tracks.audio",
            "av_medias": "media",
            "sequences": "timelines",
        }

        # Check direct mapping
        if field in legacy_map:
            return legacy_map[field]

        # Check prefix mapping (e.g., "captions.text" -> "clips.caption.text")
        for old, new in legacy_map.items():
            if field.startswith(old + "."):
                return field.replace(old + ".", new + ".", 1)
            if field.startswith(old + "["):
                return field.replace(old, new, 1)

        return field

    def _parse_typed_field(self, field: str) -> tuple[str, str | None, str | None]:
        """
        Parse a typed field like "clips.video.duration" into components.

        Returns:
            (collection_name, type_filter, nested_field)
            e.g., "clips.video.duration" -> ("clips.video", "video", "duration")
            e.g., "clips.video[0].start" -> ("clips.video[0]", "video", "start")
            e.g., "clips.video" -> ("clips.video", "video", None)
            e.g., "timelines" -> ("timelines", None, None)
        """
        parts = field.split(".")

        # Check for typed collections: clips.{type}, tracks.{type}, media.{type}
        if len(parts) >= 2:
            base = parts[0]
            if base in ("clips", "clip"):
                # Extract type and possible index: "video[0]" -> type="video", index part preserved
                type_part = parts[1]
                # Extract pure type name (without index)
                type_match = re.match(r"(\w+)(\[.+\])?", type_part)
                type_filter = type_match.group(1) if type_match else type_part
                # Build collection_name with index if present
                collection_name = f"clips.{type_part}"
                nested_field = ".".join(parts[2:]) if len(parts) > 2 else None
                return (collection_name, type_filter, nested_field)
            if base in ("tracks", "track"):
                type_part = parts[1]
                type_match = re.match(r"(\w+)(\[.+\])?", type_part)
                type_filter = type_match.group(1) if type_match else type_part
                collection_name = f"tracks.{type_part}"
                nested_field = ".".join(parts[2:]) if len(parts) > 2 else None
                return (collection_name, type_filter, nested_field)
            if base == "media":
                type_part = parts[1]
                type_match = re.match(r"(\w+)(\[.+\])?", type_part)
                pure_type = type_match.group(1) if type_match else type_part
                # Check if second part is a type filter
                if pure_type in ("video", "audio", "image"):
                    collection_name = f"media.{type_part}"
                    nested_field = ".".join(parts[2:]) if len(parts) > 2 else None
                    return (collection_name, pure_type, nested_field)

        # No type filter, just collection + nested field
        nested_field = ".".join(parts[1:]) if len(parts) > 1 else None
        return (parts[0], None, nested_field)

    def _get_collection(
        self, state: EditProject, name: str, type_filter: str | None = None
    ) -> Any:
        """
        Get a collection from EditProject by logical name.

        Args:
            state: EditProject instance
            name: Collection name (clips, tracks, media, etc.)
            type_filter: Optional type filter (video, audio, caption, etc.)
        """
        # ──────────────────────────────────────────────
        # Clips (aggregated across all timelines)
        # ──────────────────────────────────────────────
        if name in ("clip", "clips"):
            if type_filter == "video":
                return state.video_clips
            if type_filter == "audio":
                return state.audio_clips
            if type_filter == "caption":
                return state.captions
            if type_filter == "title":
                return [c for c in state.all_clips if c.type == "title"]
            if type_filter == "gap":
                return [c for c in state.all_clips if c.type == "gap"]
            if type_filter is None:
                return state.all_clips
            # Unknown type filter, try to match by type field
            return [c for c in state.all_clips if c.type == type_filter]

        # ──────────────────────────────────────────────
        # Tracks (aggregated across all timelines)
        # ──────────────────────────────────────────────
        if name in ("track", "tracks"):
            if type_filter == "video":
                return state.video_tracks
            if type_filter == "audio":
                return state.audio_tracks
            if type_filter is None:
                return state.video_tracks + state.audio_tracks
            # Unknown type filter, try to match by kind field
            all_tracks = state.video_tracks + state.audio_tracks
            return [t for t in all_tracks if t.kind == type_filter]

        # ──────────────────────────────────────────────
        # Media collections
        # ──────────────────────────────────────────────
        if name in ("media", "medias"):
            if type_filter == "video":
                return [m for m in state.media if m.type == "video"]
            if type_filter == "audio":
                return [m for m in state.media if m.type == "audio"]
            if type_filter == "image":
                return [m for m in state.media if m.type == "image"]
            if type_filter is None:
                return state.media
            return [m for m in state.media if m.type == type_filter]

        # ──────────────────────────────────────────────
        # Timeline/Sequence
        # ──────────────────────────────────────────────
        if name in ("timeline", "timelines", "sequence", "sequences"):
            return state.timelines

        # ──────────────────────────────────────────────
        # Bins
        # ──────────────────────────────────────────────
        if name in ("bin", "bins"):
            return state.bins

        # ──────────────────────────────────────────────
        # Legacy names (backwards compatibility)
        # ──────────────────────────────────────────────
        if name == "video_clips":
            return state.video_clips
        if name == "audio_clips":
            return state.audio_clips
        if name in ("caption", "captions"):
            return state.captions
        if name == "video_tracks":
            return state.video_tracks
        if name == "audio_tracks":
            return state.audio_tracks
        if name == "av_medias":
            return state.media

        # ──────────────────────────────────────────────
        # Try to find by ID
        # ──────────────────────────────────────────────
        if "_" in name:
            # Try media
            media = state.get_media_by_id(name)
            if media:
                return media
            # Try timeline
            timeline = state.get_timeline_by_id(name)
            if timeline:
                return timeline
            # Try clip
            clip = state.get_clip_by_id(name)
            if clip:
                return clip

        return None

    def _get_nested_value(self, obj: Any, field: str) -> Any:
        """Get nested field value from an object."""
        if obj is None:
            return None

        parts = field.split(".")
        current = obj

        for part in parts:
            if current is None:
                return None

            if hasattr(current, part):
                current = getattr(current, part)
            elif isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return None

        return current

    def _apply_operator(self, value: Any, constraint: Constraint) -> bool:
        """Apply operator to check constraint."""
        op = constraint.operator
        expected = constraint.value
        tolerance = constraint.tolerance or 0.0

        if op == Operator.EXISTS:
            if expected:
                return value is not None and (
                    not isinstance(value, list) or len(value) > 0
                )
            else:
                return value is None or (isinstance(value, list) and len(value) == 0)

        if op == Operator.NOT_EXISTS:
            return value is None or (isinstance(value, list) and len(value) == 0)

        if op == Operator.EQUALS:
            if isinstance(value, (int, float)) and isinstance(expected, (int, float)):
                return abs(value - expected) <= tolerance
            if isinstance(value, list):
                # For lists, check if any item matches
                return any(
                    (abs(v - expected) <= tolerance if isinstance(v, (int, float)) else v == expected)
                    for v in value
                )
            return value == expected

        if op == Operator.GTE:
            if isinstance(value, list):
                return all(v >= expected for v in value if v is not None)
            return value is not None and value >= expected

        if op == Operator.LTE:
            if isinstance(value, list):
                return all(v <= expected for v in value if v is not None)
            return value is not None and value <= expected

        if op == Operator.GT:
            if isinstance(value, list):
                return all(v > expected for v in value if v is not None)
            return value is not None and value > expected

        if op == Operator.LT:
            if isinstance(value, list):
                return all(v < expected for v in value if v is not None)
            return value is not None and value < expected

        if op == Operator.PATTERN:
            if isinstance(value, list):
                return all(
                    bool(re.match(expected, str(v))) for v in value if v is not None
                )
            return value is not None and bool(re.match(expected, str(value)))

        if op == Operator.COUNT:
            if isinstance(value, list):
                return len(value) == expected
            return False

        if op == Operator.CONTAINS:
            if isinstance(value, str):
                return expected in value
            if isinstance(value, list):
                return any(expected in str(v) for v in value)
            return False

        if op == Operator.ALIGNED_TO_CLIPS:
            # Check if captions are aligned to clip boundaries
            # This is a complex check that needs video clip info
            return True  # Simplified for now

        return False

    def validate_turn(
        self,
        previous_state: EditProject,
        current_state: EditProject,
        constraints: list[Constraint],
    ) -> list[str]:
        """
        Validate per-turn constraints.

        Compares previous_state (before this turn) with current_state (after).
        Handles comparative operators (unchanged_from_previous, etc.)
        and delegates standard operators to _check_constraint().

        Returns:
            List of failed constraint descriptions (empty = all passed).
        """
        failed: list[str] = []
        for constraint in constraints:
            if not self._check_turn_constraint(previous_state, current_state, constraint):
                failed.append(f"{constraint.field}.{constraint.operator.value}")
        return failed

    def _check_turn_constraint(
        self,
        previous_state: EditProject,
        current_state: EditProject,
        constraint: Constraint,
    ) -> bool:
        """Check a single per-turn constraint."""
        try:
            op = constraint.operator

            if op == Operator.UNCHANGED_FROM_PREVIOUS:
                prev_val = self._get_field_value(previous_state, constraint.field)
                curr_val = self._get_field_value(current_state, constraint.field)
                return prev_val == curr_val

            if op == Operator.COUNT_INCREASED:
                prev_val = self._get_field_value(previous_state, constraint.field)
                curr_val = self._get_field_value(current_state, constraint.field)
                prev_count = len(prev_val) if isinstance(prev_val, list) else 0
                curr_count = len(curr_val) if isinstance(curr_val, list) else 0
                return curr_count > prev_count

            if op == Operator.GREATER_THAN_PREVIOUS:
                prev_val = self._get_field_value(previous_state, constraint.field)
                curr_val = self._get_field_value(current_state, constraint.field)
                if isinstance(prev_val, (int, float)) and isinstance(curr_val, (int, float)):
                    return curr_val > prev_val
                return False

            if op == Operator.LESS_THAN_PREVIOUS:
                prev_val = self._get_field_value(previous_state, constraint.field)
                curr_val = self._get_field_value(current_state, constraint.field)
                if isinstance(prev_val, (int, float)) and isinstance(curr_val, (int, float)):
                    return curr_val < prev_val
                return False

            # Standard operators: check against current state
            return self._check_constraint(previous_state, current_state, constraint)

        except Exception as e:
            self._compile_errors.append(f"Error in turn constraint {constraint.field}: {e}")
            return False

    def _check_no_overlap(self, state: EditProject) -> bool:
        """Check if there are no overlapping clips on the same track."""
        for timeline in state.timelines:
            for track in timeline.tracks:
                clips = sorted(track.clips, key=lambda c: c.start)
                for i in range(len(clips) - 1):
                    if clips[i].end > clips[i + 1].start:
                        return False
        return True

    def _check_compile_success(self, state: EditProject) -> bool:
        """
        Check if the EditProject can be successfully compiled.

        Basic structural validity checks.
        """
        try:
            # Check we have at least a bin
            if state.bin is None:
                return False

            # Check all clip refs are valid
            for timeline in state.timelines:
                for track in timeline.tracks:
                    for clip in track.clips:
                        if clip.ref_id and clip.ref_type == "media":
                            if state.get_media_by_id(clip.ref_id) is None:
                                return False
                        if clip.ref_id and clip.ref_type == "timeline":
                            if state.get_timeline_by_id(clip.ref_id) is None:
                                return False

            return True

        except Exception:
            return False

    # Legacy category tokens accepted in expected_changed_entities for
    # backwards compatibility. Released v3.1 scenarios primarily use entity IDs.
    _TYPE_TO_CATEGORY: dict[str, list[str]] = {
        "Bin": ["bins"],
        "Timeline": ["timelines"],
        "Track": ["tracks", "tracks.video", "tracks.audio"],
        "Clip": ["clips", "clips.video", "clips.audio", "clips.caption"],
        "Media": ["media", "media.video", "media.audio"],
        "Transition": ["transitions"],
    }
    _CATEGORY_TOKENS: set[str] = {
        "bins",
        "timelines",
        "tracks",
        "tracks.video",
        "tracks.audio",
        "clips",
        "clips.video",
        "clips.audio",
        "clips.caption",
        "clips.title",
        "clips.gap",
        "media",
        "media.video",
        "media.audio",
        "media.image",
        "media.generator",
        "transitions",
    }

    @classmethod
    def _entity_type_categories(cls, entity: object) -> list[str]:
        """Get the expected_changed_entities category names for an entity object."""
        class_name = type(entity).__name__

        # Handle Clip type subdivisions (v4.3 naming: clips.video, clips.caption, etc.)
        if class_name == "Clip" and hasattr(entity, "type"):
            clip_type = entity.type
            if clip_type == "video":
                return ["clips", "clips.video"]
            if clip_type == "audio":
                return ["clips", "clips.audio"]
            if clip_type == "caption":
                return ["clips", "clips.caption"]
            if clip_type == "title":
                return ["clips", "clips.title"]
            return ["clips"]

        # Handle Track kind subdivisions (v4.3 naming: tracks.video, tracks.audio)
        if class_name == "Track" and hasattr(entity, "kind"):
            track_kind = entity.kind
            if track_kind == "video":
                return ["tracks", "tracks.video"]
            if track_kind == "audio":
                return ["tracks", "tracks.audio"]
            return ["tracks"]

        # Handle Media type subdivisions
        if class_name == "Media" and hasattr(entity, "type"):
            media_type = entity.type
            if media_type == "video":
                return ["media", "media.video"]
            if media_type == "audio":
                return ["media", "media.audio"]
            return ["media"]

        return cls._TYPE_TO_CATEGORY.get(class_name, [])

    def _calculate_ovr(
        self,
        initial_state: EditProject,
        final_state: EditProject,
        scenario: Scenario,
    ) -> float:
        """
        Calculate Over-edit Violation Rate (entity-level semantic diff).

        Compares initial and final state at the entity level.
        Entities that changed but whose ID is NOT in expected_changed_entities
        are counted as over-edit violations. Legacy category tokens such as
        "clips.video" remain accepted for older scenarios.

        OVR = unexpected_changes / total_changed_entities
        Denominator is only entities that actually changed (not all entities).
        0.0 = no over-edits (ideal), 1.0 = all changes were unintended (worst).
        """
        initial_entities = self._collect_entities(initial_state)
        final_entities = self._collect_entities(final_state)
        expected_ids, expected_categories = self._resolve_expected_changed_entities(
            initial_state,
            final_state,
            scenario,
        )

        all_entity_ids = set(initial_entities.keys()) | set(final_entities.keys())

        # Step 1: Identify all changed entities (with their state objects)
        changed: list[tuple[str, object]] = []  # (entity_id, entity_state)
        for entity_id in all_entity_ids:
            initial = initial_entities.get(entity_id)
            final = final_entities.get(entity_id)

            # Entity added or removed
            if (initial is None) != (final is None):
                changed.append((entity_id, final if final is not None else initial))
                continue

            if initial is None or final is None:
                continue

            # Entity modified
            if self._entity_semantically_changed(initial, final):
                changed.append((entity_id, final))

        if not changed:
            return 0.0  # No changes = no over-editing

        # Step 2: Classify as expected vs unexpected by entity ID, with legacy
        # category fallback only when category tokens were explicitly supplied.
        unexpected_count = 0
        for entity_id, entity_obj in changed:
            if not self._is_expected_change(
                entity_id,
                entity_obj,
                expected_ids,
                expected_categories,
            ):
                unexpected_count += 1

        return unexpected_count / len(changed)

    def _resolve_expected_changed_entities(
        self,
        initial_state: EditProject,
        final_state: EditProject,
        scenario: Scenario,
    ) -> tuple[set[str], set[str]]:
        """Resolve expected_changed_entities into entity IDs and legacy categories."""
        expected_ids: set[str] = set()
        expected_categories: set[str] = set()
        raw_expected = scenario.expected_changed_entities or []

        bindings: dict[str, Optional[str]] = {}
        if any(str(token).startswith("$") for token in raw_expected):
            try:
                from nlebench.runner.constraints import bind_entity_refs, rebind_entity_refs

                bindings = bind_entity_refs(initial_state, scenario)
                initial_ids = set(initial_state.collect_all_ids())
                bindings = rebind_entity_refs(
                    final_state,
                    scenario,
                    bindings,
                    initial_ids,
                )
            except Exception:
                bindings = {}

        all_entity_ids = set(self._collect_entities(initial_state)) | set(
            self._collect_entities(final_state)
        )

        for raw_token in raw_expected:
            token = str(raw_token)
            if token.startswith("$"):
                resolved = bindings.get(token) or self._resolve_expected_entity_ref(
                    token,
                    initial_state,
                    final_state,
                )
                expected_ids.add(resolved if resolved else token)
            elif token in self._CATEGORY_TOKENS and token not in all_entity_ids:
                expected_categories.add(token)
            else:
                expected_ids.add(token)

        return expected_ids, expected_categories

    def _resolve_expected_entity_ref(
        self,
        token: str,
        initial_state: EditProject,
        final_state: EditProject,
    ) -> str | None:
        """Resolve simple $type_N expected-change refs even without constraints."""
        raw = token.lstrip("$")
        new_only = raw.startswith("new_")
        if new_only:
            raw = raw[4:]

        match = re.match(r"^(.+?)_(\d+)$", raw)
        if not match:
            return None

        type_name = match.group(1)
        index = int(match.group(2)) - 1
        if index < 0:
            return None

        if new_only:
            initial_ids = set(initial_state.collect_all_ids())
            entities = [
                entity
                for entity in self._entities_for_expected_ref(final_state, type_name)
                if getattr(entity, "id", None) not in initial_ids
            ]
        else:
            entities = self._entities_for_expected_ref(initial_state, type_name)
            if index >= len(entities):
                entities = self._entities_for_expected_ref(final_state, type_name)

        if index >= len(entities):
            return None

        return getattr(entities[index], "id", None)

    @staticmethod
    def _entities_for_expected_ref(state: EditProject, type_name: str) -> list[Any]:
        """Return entities for $type_N references used by scenario YAMLs."""
        mapping = {
            "clip": state.video_clips + state.audio_clips + state.captions,
            "video": state.video_clips,
            "video_clip": state.video_clips,
            "audio": state.audio_clips,
            "audio_clip": state.audio_clips,
            "caption": state.captions,
            "track": state.video_tracks + state.audio_tracks,
            "video_track": state.video_tracks,
            "audio_track": state.audio_tracks,
            "media": state.media,
            "av_media": state.av_medias,
            "video_media": state.video_medias,
            "audio_media": state.audio_medias,
            "timeline": state.timelines,
            "sequence": state.timelines,
            "bin": state.bins,
            "transition": state.transitions,
        }
        return list(mapping.get(type_name, []))

    @classmethod
    def _is_expected_change(
        cls,
        entity_id: str,
        entity_obj: object,
        expected_ids: set[str],
        expected_categories: set[str],
    ) -> bool:
        """Return whether a changed entity is covered by ID or legacy category."""
        if entity_id in expected_ids:
            return True
        if not expected_categories:
            return False
        categories = cls._entity_type_categories(entity_obj)
        return any(category in expected_categories for category in categories)

    def _collect_entities(self, state: EditProject) -> dict[str, Any]:
        """Collect all entities from EditProject into a dict by ID."""
        entities: dict[str, Any] = {}

        # Bin (root)
        entities[state.bin.id] = state.bin

        # Media
        for m in state.media:
            entities[m.id] = m

        # Timelines, Tracks, Clips
        for timeline in state.timelines:
            entities[timeline.id] = timeline
            for track in timeline.tracks:
                entities[track.id] = track
                for clip in track.clips:
                    entities[clip.id] = clip
                for trans in track.transitions:
                    entities[trans.id] = trans

        return entities

    # -----------------------------------------------------------------------
    # OVR tolerance constants (field-specific)
    # -----------------------------------------------------------------------

    # Fields matched by name substring -> tolerance value
    _TIMING_FIELDS = {"start", "end", "timeline_start", "duration", "source_in", "source_out"}
    _POSITION_FIELDS = {"position_x", "position_y", "x", "y", "anchor_x", "anchor_y"}
    _TIMING_TOLERANCE = 0.01  # 0.01s for timing fields
    _POSITION_TOLERANCE = 0.01  # ±1px normalized (0-1 range)
    _DEFAULT_FLOAT_TOLERANCE = 1e-6  # For other floats

    @classmethod
    def _get_field_tolerance(cls, field_name: str) -> float:
        """Get appropriate tolerance for a field based on its name."""
        name_lower = field_name.lower()
        if any(t in name_lower for t in cls._TIMING_FIELDS):
            return cls._TIMING_TOLERANCE
        if any(p in name_lower for p in cls._POSITION_FIELDS):
            return cls._POSITION_TOLERANCE
        return cls._DEFAULT_FLOAT_TOLERANCE

    @classmethod
    def _entity_semantically_changed(
        cls,
        initial: Any,
        final: Any,
    ) -> bool:
        """
        Check if two entity objects differ semantically.

        Uses field-specific tolerance:
        - Timing fields (start, end, duration, etc.): 0.01s
        - Position fields (x, y, position_*): 0.01 (normalized)
        - Text fields: exact match
        - Other floats: 1e-6
        """
        if type(initial) is not type(final):
            initial_num = cls._as_semantic_number(initial)
            final_num = cls._as_semantic_number(final)
            if initial_num is None or final_num is None:
                return True
            return abs(initial_num - final_num) > cls._DEFAULT_FLOAT_TOLERANCE

        nested_fields = {"clips", "tracks", "transitions", "bins", "media", "timelines"}

        if is_dataclass(initial):
            for field_info in dc_fields(initial):
                key = field_info.name
                if key.startswith("_") or key in nested_fields:
                    continue
                v1 = getattr(initial, key, None)
                v2 = getattr(final, key, None)
                n1 = cls._as_semantic_number(v1)
                n2 = cls._as_semantic_number(v2)
                if n1 is not None and n2 is not None:
                    tol = cls._get_field_tolerance(key)
                    if abs(n1 - n2) > tol:
                        return True
                elif isinstance(v1, list) and isinstance(v2, list):
                    if len(v1) != len(v2):
                        return True
                    for item1, item2 in zip(v1, v2):
                        if cls._entity_semantically_changed(item1, item2):
                            return True
                elif v1 != v2:
                    return True
            return False

        return initial != final

    @staticmethod
    def _as_semantic_number(value: Any) -> float | None:
        """Convert numeric/Rational-like values for tolerance-aware comparison."""
        if isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            return float(value)
        if hasattr(value, "to_float"):
            return float(value.to_float())
        return None


def validate_scenario(
    initial_state: EditProject,
    final_state: EditProject,
    scenario: Scenario,
) -> ValidationResult:
    """Convenience function to validate a scenario."""
    validator = ConstraintValidator()
    return validator.validate(initial_state, final_state, scenario)
