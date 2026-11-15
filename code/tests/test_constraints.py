"""Tests for the named constraint system (Phase 4) - v4.3 schema."""

import pytest
from copy import deepcopy

from nlebench.models import (
    EditProject, Scenario, Level, Taxonomy, Scale, Feasibility,
    Media, Timeline, Track, Clip, Bin, Rational, Transition,
    VideoProperties, AudioProperties, Caption, TextStyle,
)
from nlebench.runner.constraints import (
    bind_entity_refs,
    rebind_entity_refs,
    evaluate_constraints,
    validate_named_constraints,
    CONSTRAINT_FUNCTIONS,
    DEFAULT_TOLERANCE,
    _parse_ref,
    _merge_tolerance,
    _resolve_refs,
)


# ── Helpers ──

def _make_simple_state() -> EditProject:
    """Create a simple state with 1 timeline, 1 video track, 2 clips using v4.3 schema."""
    return EditProject(
        schema_version="4.3",
        title="Test",
        bin=Bin(
            id="bin_1",
            name="Root",
            media_ids=["av_media_1"],
            timeline_ids=["timeline_1"],
        ),
        media=[
            Media(
                id="av_media_1",
                name="test.mp4",
                type="video",
                path="/test.mp4",
                duration=Rational.from_float(30.0),
                video=VideoProperties(width=1920, height=1080, fps=Rational(n=30000, d=1001)),
                audio=AudioProperties(),
            ),
        ],
        timelines=[
            Timeline(
                id="timeline_1",
                name="Main",
                tracks=[
                    Track(
                        id="video_track_1",
                        kind="video",
                        name="V1",
                        clips=[
                            Clip(
                                id="video_clip_1",
                                type="video",
                                name="Clip 1",
                                ref_id="av_media_1",
                                ref_type="media",
                                timeline_start=Rational.from_float(0.0),
                                duration=Rational.from_float(5.0),
                                source_in=Rational.from_float(0.0),
                                source_out=Rational.from_float(5.0),
                                link_group="link_1",
                            ),
                            Clip(
                                id="video_clip_2",
                                type="video",
                                name="Clip 2",
                                ref_id="av_media_1",
                                ref_type="media",
                                timeline_start=Rational.from_float(5.0),
                                duration=Rational.from_float(5.0),
                                source_in=Rational.from_float(5.0),
                                source_out=Rational.from_float(10.0),
                            ),
                        ],
                    ),
                    Track(
                        id="audio_track_1",
                        kind="audio",
                        name="A1",
                        clips=[
                            Clip(
                                id="audio_clip_1",
                                type="audio",
                                name="Audio 1",
                                ref_id="av_media_1",
                                ref_type="media",
                                timeline_start=Rational.from_float(0.0),
                                duration=Rational.from_float(5.0),
                                source_in=Rational.from_float(0.0),
                                source_out=Rational.from_float(5.0),
                                volume=-3.0,
                                link_group="link_1",
                            ),
                        ],
                    ),
                ],
            ),
        ],
    )


def _make_scenario(**kwargs) -> Scenario:
    """Create a minimal scenario with named constraints."""
    defaults = dict(
        id="test_001",
        name="Test",
        level=Level.L1,
        category="test",
        description="Test scenario",
        fixture="single_clip",
        user_messages=["Test instruction"],
    )
    defaults.update(kwargs)
    return Scenario(**defaults)


# ── Tests: _parse_ref ──

class TestParseRef:
    def test_clip_ref(self):
        assert _parse_ref("$clip_1") == ("clip", 1)

    def test_video_clip_ref(self):
        assert _parse_ref("$video_clip_3") == ("video_clip", 3)

    def test_new_ref(self):
        assert _parse_ref("$new_caption_2") == ("caption", 2)

    def test_audio_ref(self):
        assert _parse_ref("$audio_clip_1") == ("audio_clip", 1)


# ── Tests: Entity Binding ──

class TestEntityBinding:
    def test_bind_clip_refs(self):
        state = _make_simple_state()
        scenario = _make_scenario(
            named_constraints_required=[
                {"attribute_equals": {"entity": "$clip_1", "field": "start", "value": 0.0}},
                {"attribute_equals": {"entity": "$clip_2", "field": "start", "value": 5.0}},
            ]
        )
        bindings = bind_entity_refs(state, scenario)
        # $clip_N indexes into all clips combined
        assert bindings["$clip_1"] == "video_clip_1"
        assert bindings["$clip_2"] == "video_clip_2"

    def test_bind_video_clip_refs(self):
        state = _make_simple_state()
        scenario = _make_scenario(
            named_constraints_required=[
                {"position_equals": {"entity": "$video_clip_2", "start": 5.0}},
            ]
        )
        bindings = bind_entity_refs(state, scenario)
        assert bindings["$video_clip_2"] == "video_clip_2"

    def test_bind_new_ref_is_none(self):
        state = _make_simple_state()
        scenario = _make_scenario(
            named_constraints_required=[
                {"entity_exists": {"type": "caption"}},
            ],
            named_constraints_specified=[
                {"attribute_equals": {"entity": "$new_caption_1", "field": "text", "value": "Hello"}},
            ]
        )
        bindings = bind_entity_refs(state, scenario)
        assert bindings.get("$new_caption_1") is None

    def test_resolve_refs(self):
        bindings = {"$clip_1": "video_clip_1", "$clip_2": "video_clip_2"}
        params = {"entities": ["$clip_1", "$clip_2"], "track": "V1"}
        resolved = _resolve_refs(params, bindings)
        assert resolved == {"entities": ["video_clip_1", "video_clip_2"], "track": "V1"}


# ── Tests: Constraint Functions ──

class TestEntityExists:
    def test_exists(self):
        state = _make_simple_state()
        tol = DEFAULT_TOLERANCE
        assert CONSTRAINT_FUNCTIONS["entity_exists"](
            state, {"type": "video_clip", "track": "V1", "index": 0}, tol
        )

    def test_exists_index_out_of_range(self):
        state = _make_simple_state()
        tol = DEFAULT_TOLERANCE
        assert not CONSTRAINT_FUNCTIONS["entity_exists"](
            state, {"type": "video_clip", "track": "V1", "index": 5}, tol
        )

    def test_not_exists(self):
        state = _make_simple_state()
        tol = DEFAULT_TOLERANCE
        assert CONSTRAINT_FUNCTIONS["entity_not_exists"](
            state, {"type": "caption", "track": "V1", "index": 0}, tol
        )


class TestEntityCount:
    def test_count_matches(self):
        state = _make_simple_state()
        tol = DEFAULT_TOLERANCE
        assert CONSTRAINT_FUNCTIONS["entity_count"](
            state, {"type": "video_clip", "track": "V1", "expected": 2}, tol
        )

    def test_count_no_match(self):
        state = _make_simple_state()
        tol = DEFAULT_TOLERANCE
        assert not CONSTRAINT_FUNCTIONS["entity_count"](
            state, {"type": "video_clip", "track": "V1", "expected": 3}, tol
        )

    def test_count_all(self):
        state = _make_simple_state()
        tol = DEFAULT_TOLERANCE
        assert CONSTRAINT_FUNCTIONS["entity_count"](
            state, {"type": "video_clip", "track": None, "expected": 2}, tol
        )


class TestAttributeEquals:
    def test_float_equals_exact(self):
        state = _make_simple_state()
        tol = DEFAULT_TOLERANCE
        assert CONSTRAINT_FUNCTIONS["attribute_equals"](
            state, {"entity": "video_clip_1", "field": "start", "value": 0.0}, tol
        )

    def test_float_within_tolerance(self):
        state = _make_simple_state()
        tol = DEFAULT_TOLERANCE
        assert CONSTRAINT_FUNCTIONS["attribute_equals"](
            state, {"entity": "video_clip_1", "field": "start", "value": 0.04}, tol
        )

    def test_float_outside_tolerance(self):
        state = _make_simple_state()
        tol = DEFAULT_TOLERANCE
        assert not CONSTRAINT_FUNCTIONS["attribute_equals"](
            state, {"entity": "video_clip_1", "field": "start", "value": 1.0}, tol
        )

    def test_string_equals(self):
        state = _make_simple_state()
        tol = DEFAULT_TOLERANCE
        assert CONSTRAINT_FUNCTIONS["attribute_equals"](
            state, {"entity": "video_clip_1", "field": "ref_id", "value": "av_media_1"}, tol
        )

    def test_entity_not_found(self):
        state = _make_simple_state()
        tol = DEFAULT_TOLERANCE
        assert not CONSTRAINT_FUNCTIONS["attribute_equals"](
            state, {"entity": "nonexistent", "field": "start", "value": 0.0}, tol
        )


class TestAttributeInRange:
    def test_in_range(self):
        state = _make_simple_state()
        tol = DEFAULT_TOLERANCE
        assert CONSTRAINT_FUNCTIONS["attribute_in_range"](
            state, {"entity": "audio_clip_1", "field": "volume", "min": -6.0, "max": 0.0}, tol
        )

    def test_out_of_range(self):
        state = _make_simple_state()
        tol = DEFAULT_TOLERANCE
        assert not CONSTRAINT_FUNCTIONS["attribute_in_range"](
            state, {"entity": "audio_clip_1", "field": "volume", "min": 0.0, "max": 3.0}, tol
        )


class TestAttributeChanged:
    def test_changed(self):
        state = _make_simple_state()
        state._initial = deepcopy(state)
        # Modify the clip
        state.timelines[0].tracks[0].clips[0].timeline_start = Rational.from_float(2.0)
        tol = DEFAULT_TOLERANCE
        assert CONSTRAINT_FUNCTIONS["attribute_changed"](
            state, {"entity": "video_clip_1", "field": "start"}, tol
        )

    def test_not_changed(self):
        state = _make_simple_state()
        state._initial = deepcopy(state)
        tol = DEFAULT_TOLERANCE
        assert not CONSTRAINT_FUNCTIONS["attribute_changed"](
            state, {"entity": "video_clip_1", "field": "start"}, tol
        )

    def test_direction_increase_passes_for_numeric_increase(self):
        state = _make_simple_state()
        state._initial = deepcopy(state)
        state.timelines[0].tracks[0].clips[0].timeline_start = Rational.from_float(2.0)
        tol = DEFAULT_TOLERANCE
        assert CONSTRAINT_FUNCTIONS["attribute_changed"](
            state,
            {"entity": "video_clip_1", "field": "start", "direction": "increase"},
            tol,
        )

    def test_direction_increase_rejects_numeric_decrease(self):
        state = _make_simple_state()
        state._initial = deepcopy(state)
        state.timelines[0].tracks[0].clips[0].timeline_start = Rational.from_float(-2.0)
        tol = DEFAULT_TOLERANCE
        assert not CONSTRAINT_FUNCTIONS["attribute_changed"](
            state,
            {"entity": "video_clip_1", "field": "start", "direction": "increase"},
            tol,
        )

    def test_direction_decrease_passes_for_numeric_decrease(self):
        state = _make_simple_state()
        state._initial = deepcopy(state)
        state.timelines[0].tracks[1].clips[0].volume = -6.0
        tol = DEFAULT_TOLERANCE
        assert CONSTRAINT_FUNCTIONS["attribute_changed"](
            state,
            {"entity": "audio_clip_1", "field": "audio.volume", "direction": "decrease"},
            tol,
        )

    def test_direction_decrease_rejects_numeric_increase(self):
        state = _make_simple_state()
        state._initial = deepcopy(state)
        state.timelines[0].tracks[1].clips[0].volume = 0.0
        tol = DEFAULT_TOLERANCE
        assert not CONSTRAINT_FUNCTIONS["attribute_changed"](
            state,
            {"entity": "audio_clip_1", "field": "audio.volume", "direction": "decrease"},
            tol,
        )

    def test_direction_any_accepts_numeric_change(self):
        state = _make_simple_state()
        state._initial = deepcopy(state)
        state.timelines[0].tracks[1].clips[0].volume = 0.0
        tol = DEFAULT_TOLERANCE
        assert CONSTRAINT_FUNCTIONS["attribute_changed"](
            state,
            {"entity": "audio_clip_1", "field": "audio.volume", "direction": "any"},
            tol,
        )

    def test_direction_on_non_numeric_field_checks_changed_only(self):
        state = _make_simple_state()
        state._initial = deepcopy(state)
        state.timelines[0].tracks[0].clips[0].name = "Renamed"
        tol = DEFAULT_TOLERANCE
        assert CONSTRAINT_FUNCTIONS["attribute_changed"](
            state,
            {"entity": "video_clip_1", "field": "name", "direction": "increase"},
            tol,
        )

    def test_invalid_direction_raises(self):
        state = _make_simple_state()
        state._initial = deepcopy(state)
        tol = DEFAULT_TOLERANCE
        with pytest.raises(ValueError, match="attribute_changed.direction"):
            CONSTRAINT_FUNCTIONS["attribute_changed"](
                state,
                {"entity": "video_clip_1", "field": "start", "direction": "sideways"},
                tol,
            )


class TestPositionEquals:
    def test_matches(self):
        state = _make_simple_state()
        tol = DEFAULT_TOLERANCE
        assert CONSTRAINT_FUNCTIONS["position_equals"](
            state, {"entity": "video_clip_1", "start": 0.0, "end": 5.0}, tol
        )

    def test_partial_check(self):
        state = _make_simple_state()
        tol = DEFAULT_TOLERANCE
        assert CONSTRAINT_FUNCTIONS["position_equals"](
            state, {"entity": "video_clip_1", "start": 0.0, "end": None}, tol
        )

    def test_mismatch(self):
        state = _make_simple_state()
        tol = DEFAULT_TOLERANCE
        assert not CONSTRAINT_FUNCTIONS["position_equals"](
            state, {"entity": "video_clip_1", "start": 2.0}, tol
        )


class TestDurationEquals:
    def test_matches(self):
        state = _make_simple_state()
        tol = DEFAULT_TOLERANCE
        assert CONSTRAINT_FUNCTIONS["duration_equals"](
            state, {"entity": "video_clip_1", "value": 5.0}, tol
        )

    def test_within_tolerance(self):
        state = _make_simple_state()
        tol = DEFAULT_TOLERANCE
        assert CONSTRAINT_FUNCTIONS["duration_equals"](
            state, {"entity": "video_clip_1", "value": 5.04}, tol
        )


class TestOrder:
    def test_correct_order(self):
        state = _make_simple_state()
        tol = DEFAULT_TOLERANCE
        assert CONSTRAINT_FUNCTIONS["order"](
            state, {"entities": ["video_clip_1", "video_clip_2"], "track": "V1"}, tol
        )

    def test_wrong_order(self):
        state = _make_simple_state()
        tol = DEFAULT_TOLERANCE
        assert not CONSTRAINT_FUNCTIONS["order"](
            state, {"entities": ["video_clip_2", "video_clip_1"], "track": "V1"}, tol
        )


class TestNoOverlap:
    def test_no_overlap(self):
        state = _make_simple_state()
        tol = DEFAULT_TOLERANCE
        assert CONSTRAINT_FUNCTIONS["no_overlap"](state, {"track": "V1"}, tol)

    def test_overlap(self):
        state = _make_simple_state()
        # Make clip 2 overlap with clip 1
        state.timelines[0].tracks[0].clips[1].timeline_start = Rational.from_float(4.0)
        tol = DEFAULT_TOLERANCE
        assert not CONSTRAINT_FUNCTIONS["no_overlap"](state, {"track": "V1"}, tol)


class TestNoGap:
    def test_no_gap(self):
        state = _make_simple_state()
        tol = DEFAULT_TOLERANCE
        assert CONSTRAINT_FUNCTIONS["no_gap"](state, {"track": "V1"}, tol)

    def test_has_gap(self):
        state = _make_simple_state()
        # Make gap by moving clip 2
        state.timelines[0].tracks[0].clips[1].timeline_start = Rational.from_float(6.0)
        tol = DEFAULT_TOLERANCE
        assert not CONSTRAINT_FUNCTIONS["no_gap"](state, {"track": "V1"}, tol)


class TestReferenceIntact:
    def test_valid(self):
        state = _make_simple_state()
        tol = DEFAULT_TOLERANCE
        assert CONSTRAINT_FUNCTIONS["reference_intact"](state, {}, tol)

    def test_broken_media_ref(self):
        state = _make_simple_state()
        state.timelines[0].tracks[0].clips[0].ref_id = "nonexistent"
        tol = DEFAULT_TOLERANCE
        assert not CONSTRAINT_FUNCTIONS["reference_intact"](state, {}, tol)


class TestHasEffect:
    def test_has_effect(self):
        state = _make_simple_state()
        # Add effect as NativeBlock
        from nlebench.models import NativeBlock
        state.timelines[0].tracks[0].clips[0].native.append(
            NativeBlock(source="nlebench", type="blur", data={"id": "effect_1", "enabled": True})
        )
        tol = DEFAULT_TOLERANCE
        assert CONSTRAINT_FUNCTIONS["has_effect"](
            state, {"entity": "video_clip_1", "effect_type": "blur"}, tol
        )

    def test_no_effect(self):
        state = _make_simple_state()
        tol = DEFAULT_TOLERANCE
        assert not CONSTRAINT_FUNCTIONS["has_effect"](
            state, {"entity": "video_clip_1"}, tol
        )


class TestHasTransition:
    def test_has_transition(self):
        state = _make_simple_state()
        # Add transition
        state.timelines[0].tracks[0].transitions.append(
            Transition(
                id="transition_1",
                type="cross_dissolve",
                duration=Rational.from_float(1.0),
                clip_before_id="video_clip_1",
                clip_after_id="video_clip_2",
            )
        )
        tol = DEFAULT_TOLERANCE
        assert CONSTRAINT_FUNCTIONS["has_transition"](
            state, {"between": ["video_clip_1", "video_clip_2"], "type": "cross_dissolve"}, tol
        )

    def test_no_transition(self):
        state = _make_simple_state()
        tol = DEFAULT_TOLERANCE
        assert not CONSTRAINT_FUNCTIONS["has_transition"](
            state, {"between": ["video_clip_1", "video_clip_2"]}, tol
        )


class TestUnchangedExcept:
    def test_unchanged(self):
        state = _make_simple_state()
        state._initial = deepcopy(state)
        tol = DEFAULT_TOLERANCE
        assert CONSTRAINT_FUNCTIONS["unchanged_except"](
            state, {"changed": []}, tol
        )

    def test_expected_change(self):
        state = _make_simple_state()
        state._initial = deepcopy(state)
        state.timelines[0].tracks[0].clips[0].timeline_start = Rational.from_float(2.0)
        tol = DEFAULT_TOLERANCE
        assert CONSTRAINT_FUNCTIONS["unchanged_except"](
            state, {"changed": ["video_clip_1"]}, tol
        )

    def test_unexpected_change(self):
        state = _make_simple_state()
        state._initial = deepcopy(state)
        state.timelines[0].tracks[0].clips[0].timeline_start = Rational.from_float(2.0)
        tol = DEFAULT_TOLERANCE
        assert not CONSTRAINT_FUNCTIONS["unchanged_except"](
            state, {"changed": []}, tol
        )


# ── Tests: Full Evaluation ──

class TestEvaluateConstraints:
    def test_all_pass(self):
        state = _make_simple_state()
        state._initial = deepcopy(state)
        scenario = _make_scenario(
            named_constraints_required=[
                {"entity_count": {"type": "video_clip", "track": "V1", "expected": 2}},
                {"no_overlap": {"track": "V1"}},
            ]
        )
        bindings = bind_entity_refs(state, scenario)
        result = evaluate_constraints(state, scenario, bindings)
        assert result.all_passed
        assert result.total == 2
        assert result.passed_count == 2

    def test_partial_fail(self):
        state = _make_simple_state()
        state._initial = deepcopy(state)
        scenario = _make_scenario(
            named_constraints_required=[
                {"entity_count": {"type": "video_clip", "track": "V1", "expected": 5}},
                {"no_overlap": {"track": "V1"}},
            ]
        )
        bindings = bind_entity_refs(state, scenario)
        result = evaluate_constraints(state, scenario, bindings)
        assert not result.all_passed
        assert result.passed_count == 1
        assert len(result.failed) == 1

    def test_with_ref_binding(self):
        state = _make_simple_state()
        state._initial = deepcopy(state)
        scenario = _make_scenario(
            named_constraints_required=[
                {"position_equals": {"entity": "$video_clip_1", "start": 0.0, "end": 5.0}},
            ]
        )
        bindings = bind_entity_refs(state, scenario)
        result = evaluate_constraints(state, scenario, bindings)
        assert result.all_passed

    def test_tolerance_override(self):
        state = _make_simple_state()
        state._initial = deepcopy(state)
        # Use tight tolerance - 0.04 should fail with time tolerance 0.01
        scenario = _make_scenario(
            named_constraints_required=[
                {"position_equals": {"entity": "$video_clip_1", "start": 0.04}},
            ],
            tolerance_override={"time": 0.01},
        )
        bindings = bind_entity_refs(state, scenario)
        result = evaluate_constraints(state, scenario, bindings)
        assert not result.all_passed


class TestValidateNamedConstraints:
    def test_full_validation(self):
        initial = _make_simple_state()
        final = deepcopy(initial)
        scenario = _make_scenario(
            named_constraints_required=[
                {"entity_count": {"type": "video_clip", "track": "V1", "expected": 2}},
                {"reference_intact": {}},
            ]
        )
        tsr, result = validate_named_constraints(initial, final, scenario)
        assert tsr is True
        assert result.all_passed


class TestToleranceSystem:
    def test_default_tolerance(self):
        tol = _merge_tolerance(None)
        assert tol["time"] == 0.05
        assert tol["volume"] == 0.5

    def test_override_tolerance(self):
        tol = _merge_tolerance({"time": 0.01, "volume": 0.1})
        assert tol["time"] == 0.01
        assert tol["volume"] == 0.1
        assert tol["speed"] == 0.01  # unchanged default


class TestAllConstraintsRegistered:
    def test_registered_functions(self):
        expected = {
            "entity_exists", "entity_not_exists", "entity_count",
            "entity_count_changed",
            "attribute_equals", "attribute_in_range", "attribute_changed",
            "position_equals", "position_changed",
            "duration_equals", "order",
            "no_overlap", "no_gap", "reference_intact",
            "has_effect", "has_transition", "unchanged_except",
            "has_link", "not_linked",
            "state_changed", "effect_param_changed", "batch_operation",
        }
        assert set(CONSTRAINT_FUNCTIONS.keys()) == expected
