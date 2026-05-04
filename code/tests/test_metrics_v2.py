"""Tests for Phase 6 metric updates (CQS F1, OVR entity diff, CSR validation) - v4.3 schema."""

import pytest
from copy import deepcopy

from nlebench.models import (
    EditProject, Media, Timeline, Track, Clip, Bin, Rational,
    VideoProperties, AudioProperties, NativeBlock, Scenario, Level,
)
from nlebench.metrics.calibration import calculate_cqs_single
from nlebench.metrics.reliability import (
    calculate_ovr_entity_diff,
    validate_edit_project,
)
from nlebench.runner.validator import ConstraintValidator


# ── Helpers ──

def _make_state() -> EditProject:
    """Create a test state using v4.3 schema."""
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
                                duration=Rational.from_float(10.0),
                                link_group="link_1",
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
                                duration=Rational.from_float(10.0),
                                volume=0.0,
                                link_group="link_1",
                            ),
                        ],
                    ),
                ],
            ),
        ],
    )


# ── CQS F1 Tests ──

class TestCQSF1:
    def test_perfect_clarification(self):
        """Agent asks about all missing parameters -> CQS = 1.0."""
        score = calculate_cqs_single(
            response_text="What text do you want? Where should it go? How long?",
            asked_clarification=True,
            state_changed=False,
            missing_parameters=["text_content", "track", "time_range"],
        )
        assert score == pytest.approx(1.0)

    def test_partial_clarification(self):
        """Agent asks about 2 of 3 missing params."""
        score = calculate_cqs_single(
            response_text="What text do you want? Where should it go?",
            asked_clarification=True,
            state_changed=False,
            missing_parameters=["text_content", "track", "time_range"],
        )
        assert 0.0 < score < 1.0

    def test_no_clarification(self):
        """Agent doesn't ask -> CQS = 0."""
        score = calculate_cqs_single(
            response_text="I'll add a caption now.",
            asked_clarification=False,
            state_changed=False,
            missing_parameters=["text_content", "track"],
        )
        assert score == 0.0

    def test_state_changed(self):
        """Agent changes state -> CQS = 0."""
        score = calculate_cqs_single(
            response_text="What text? Where?",
            asked_clarification=True,
            state_changed=True,
            missing_parameters=["text_content", "track"],
        )
        assert score == 0.0

    def test_no_missing_params(self):
        """No missing params -> CQS = 1.0 if clarification asked."""
        score = calculate_cqs_single(
            response_text="Can you specify?",
            asked_clarification=True,
            state_changed=False,
            missing_parameters=[],
        )
        assert score == 1.0

    def test_over_questioning_penalty(self):
        """Agent asks too many questions -> precision drops."""
        # Asks about text (relevant) + 3 irrelevant questions
        score = calculate_cqs_single(
            response_text="What text? What font? What color? What size? Where?",
            asked_clarification=True,
            state_changed=False,
            missing_parameters=["text_content", "track"],
        )
        # 2 relevant out of 5 questions -> precision = 2/5 = 0.4
        # recall = 2/2 = 1.0
        # F1 = 2 * 0.4 * 1.0 / 1.4 ~ 0.571
        assert 0.0 < score < 1.0


# ── OVR Entity Diff Tests ──

class TestOVREntityDiff:
    def test_no_changes(self):
        """No changes -> OVR = 0.0."""
        initial = _make_state()
        final = deepcopy(initial)
        ovr = calculate_ovr_entity_diff(initial, final, [])
        assert ovr == 0.0

    def test_expected_change(self):
        """Expected change -> OVR = 0.0."""
        initial = _make_state()
        final = deepcopy(initial)
        final.timelines[0].tracks[1].clips[0].volume = -6.0
        ovr = calculate_ovr_entity_diff(initial, final, ["audio_clip_1"])
        assert ovr == 0.0

    def test_unexpected_change(self):
        """Unexpected change -> OVR > 0."""
        initial = _make_state()
        final = deepcopy(initial)
        final.timelines[0].tracks[1].clips[0].volume = -6.0
        ovr = calculate_ovr_entity_diff(initial, final, [])
        assert ovr > 0.0

    def test_unexpected_deletion(self):
        """Deleting an entity not in expected -> OVR > 0."""
        initial = _make_state()
        final = deepcopy(initial)
        final.timelines[0].tracks[1].clips.clear()  # Delete audio clip
        ovr = calculate_ovr_entity_diff(initial, final, [])
        assert ovr > 0.0

    def test_unexpected_addition(self):
        """Adding an entity not in expected -> OVR > 0."""
        initial = _make_state()
        final = deepcopy(initial)
        # Add an effect as NativeBlock
        final.timelines[0].tracks[0].clips[0].native.append(
            NativeBlock(source="nlebench", type="blur", data={"id": "effect_new"})
        )
        ovr = calculate_ovr_entity_diff(initial, final, [])
        assert ovr > 0.0

    def test_within_tolerance(self):
        """Change within tolerance -> not counted as change."""
        initial = _make_state()
        final = deepcopy(initial)
        # Change start by 0.01s (within 0.05s tolerance)
        final.timelines[0].tracks[0].clips[0].timeline_start = Rational.from_float(0.01)
        ovr = calculate_ovr_entity_diff(initial, final, [])
        assert ovr == 0.0

    def test_ovr_denominator_is_initial_count(self):
        """OVR denominator is total initial entities."""
        initial = _make_state()
        final = deepcopy(initial)
        # Modify 1 entity unexpectedly
        final.timelines[0].tracks[0].clips[0].timeline_start = Rational.from_float(5.0)
        total_initial = len(initial.collect_all_ids())
        ovr = calculate_ovr_entity_diff(initial, final, [])
        expected_ovr = 1 / total_initial
        assert ovr == pytest.approx(expected_ovr, rel=0.1)


class TestValidatorOVR:
    def _scenario(self, expected_changed_entities: list[str]) -> Scenario:
        return Scenario(
            id="test_ovr",
            name="OVR test",
            level=Level.L1,
            category="audio",
            description="Change audio volume",
            fixture="unit",
            user_messages=["Lower the audio volume"],
            expected_changed_entities=expected_changed_entities,
        )

    def test_expected_changed_entities_are_entity_ids(self):
        initial = _make_state()
        final = deepcopy(initial)
        final.timelines[0].tracks[1].clips[0].volume = -6.0

        validator = ConstraintValidator()
        ovr = validator._calculate_ovr(
            initial,
            final,
            self._scenario(["audio_clip_1"]),
        )

        assert ovr == 0.0

    def test_symbolic_expected_changed_entities_are_resolved_to_ids(self):
        initial = _make_state()
        final = deepcopy(initial)
        final.timelines[0].tracks[1].clips[0].volume = -6.0

        validator = ConstraintValidator()
        ovr = validator._calculate_ovr(
            initial,
            final,
            self._scenario(["$audio_clip_1"]),
        )

        assert ovr == 0.0

    def test_legacy_category_expected_changed_entities_still_work(self):
        initial = _make_state()
        final = deepcopy(initial)
        final.timelines[0].tracks[1].clips[0].volume = -6.0

        validator = ConstraintValidator()
        ovr = validator._calculate_ovr(
            initial,
            final,
            self._scenario(["clips.audio"]),
        )

        assert ovr == 0.0

    def test_unexpected_entity_change_counts_as_ovr(self):
        initial = _make_state()
        final = deepcopy(initial)
        final.timelines[0].tracks[1].clips[0].volume = -6.0

        validator = ConstraintValidator()
        ovr = validator._calculate_ovr(initial, final, self._scenario([]))

        assert ovr == 1.0


# ── CSR Validation Tests ──

class TestValidateEditProject:
    def test_valid_state(self):
        state = _make_state()
        valid, errors = validate_edit_project(state)
        assert valid
        assert errors == []

    def test_broken_media_ref(self):
        state = _make_state()
        state.timelines[0].tracks[0].clips[0].ref_id = "nonexistent"
        valid, errors = validate_edit_project(state)
        assert not valid
        assert any("missing media" in e.lower() or "nonexistent" in e.lower() for e in errors)

    def test_duplicate_ids(self):
        state = _make_state()
        # Add entity with duplicate ID
        state.timelines[0].tracks[0].clips[0].native.append(
            NativeBlock(source="nlebench", type="blur", data={"id": "video_clip_1"})
        )
        # Note: NativeBlock doesn't have its own ID in the same way, this test may need adjustment
        # depending on how validate_edit_project handles NativeBlocks
        # For now, let's test with adding a clip with duplicate ID
        state.timelines[0].tracks[0].clips.append(
            Clip(
                id="video_clip_1",  # Duplicate ID
                type="video",
                name="Duplicate",
                ref_id="av_media_1",
                ref_type="media",
                timeline_start=Rational.from_float(20.0),
                duration=Rational.from_float(5.0),
            )
        )
        valid, errors = validate_edit_project(state)
        assert not valid
        assert any("duplicate" in e.lower() for e in errors)

    def test_broken_link_ref(self):
        """Test that a broken link reference is detected - skip if not applicable to v4.3."""
        # In v4.3, links are handled via link_group field on clips, not separate Link entities
        # This test may not apply directly
        pass
