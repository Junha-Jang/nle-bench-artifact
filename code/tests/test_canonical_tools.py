"""Tests for 25 canonical tools against EditProject (v4.3 schema)."""

import pytest

from nlebench.models import (
    EditProject, Media, Timeline, Track, Clip, Bin, Rational,
    VideoProperties, AudioProperties, NativeBlock,
)
from nlebench.tools import CANONICAL_TOOLS, execute_tool


def _make_fixture() -> EditProject:
    """Single clip fixture for testing (v4.3 schema)."""
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
                path="/media/test.mp4",
                duration=Rational.from_float(30.0),
                video=VideoProperties(width=1920, height=1080, fps=Rational(n=24000, d=1000)),
                audio=AudioProperties(),
            ),
        ],
        timelines=[
            Timeline(
                id="timeline_1",
                name="Main",
                width=1920,
                height=1080,
                fps=Rational(n=24000, d=1000),
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
                                volume=0.0,
                                link_group="link_1",
                            ),
                        ],
                    ),
                ],
            ),
        ],
    )


# Helper functions for v4.3 state access
def _get_video_track(state: EditProject, track_id: str = "video_track_1") -> Track:
    for tl in state.timelines:
        for t in tl.tracks:
            if t.id == track_id:
                return t
    raise ValueError(f"Track {track_id} not found")


def _get_audio_track(state: EditProject, track_id: str = "audio_track_1") -> Track:
    for tl in state.timelines:
        for t in tl.tracks:
            if t.id == track_id:
                return t
    raise ValueError(f"Track {track_id} not found")


def _get_video_clips(state: EditProject) -> list[Clip]:
    clips = []
    for tl in state.timelines:
        for t in tl.tracks:
            if t.kind == "video":
                clips.extend(c for c in t.clips if c.type == "video")
    return clips


def _get_audio_clips(state: EditProject) -> list[Clip]:
    clips = []
    for tl in state.timelines:
        for t in tl.tracks:
            if t.kind == "audio":
                clips.extend(c for c in t.clips if c.type == "audio")
    return clips


def _get_caption_clips(state: EditProject) -> list[Clip]:
    clips = []
    for tl in state.timelines:
        for t in tl.tracks:
            clips.extend(c for c in t.clips if c.type == "caption")
    return clips


def _get_all_clips(state: EditProject) -> list[Clip]:
    clips = []
    for tl in state.timelines:
        for t in tl.tracks:
            clips.extend(t.clips)
    return clips


def _get_clip_by_id(state: EditProject, clip_id: str) -> Clip | None:
    for tl in state.timelines:
        for t in tl.tracks:
            for c in t.clips:
                if c.id == clip_id:
                    return c
    return None


def _get_video_tracks(state: EditProject, timeline_id: str = "timeline_1") -> list[Track]:
    for tl in state.timelines:
        if tl.id == timeline_id:
            return [t for t in tl.tracks if t.kind == "video"]
    return []


def _get_audio_tracks(state: EditProject, timeline_id: str = "timeline_1") -> list[Track]:
    for tl in state.timelines:
        if tl.id == timeline_id:
            return [t for t in tl.tracks if t.kind == "audio"]
    return []


def _count_linked_clips(state: EditProject) -> int:
    """Count clip pairs with link_group set."""
    link_groups = set()
    for tl in state.timelines:
        for t in tl.tracks:
            for c in t.clips:
                if c.link_group:
                    link_groups.add(c.link_group)
    return len(link_groups)


def _get_effects_on_clip(clip: Clip) -> list[NativeBlock]:
    """Get effects stored as NativeBlocks on a clip."""
    return [n for n in clip.native if n.type not in ("source", "metadata")]


class TestToolCount:
    def test_25_canonical_tools(self):
        assert len(CANONICAL_TOOLS) == 25

    def test_tool_names(self):
        names = [t["function"]["name"] for t in CANONICAL_TOOLS]
        expected = [
            "add_clip", "update_clip", "remove_clip", "split_clip",
            "add_caption", "update_caption", "remove_caption",
            "add_effect", "update_effect", "remove_effect",
            "add_transition", "update_transition", "remove_transition",
            "add_track", "update_track", "remove_track",
            "import_media", "update_media", "remove_media",
            "add_sequence", "update_sequence",
            "manage_bin",
            "link_clips", "unlink_clips",
            "query_state",
        ]
        assert names == expected


class TestQueryState:
    def test_query_all(self):
        state = _make_fixture()
        r = execute_tool(state, "query_state", {"entity_type": "all"})
        assert r["success"]
        assert "clips" in r["data"]
        assert "tracks" in r["data"]

    def test_query_by_type(self):
        state = _make_fixture()
        r = execute_tool(state, "query_state", {"entity_type": "clip"})
        assert r["success"]
        assert len(r["data"]["clips"]) == 2  # 1 video + 1 audio

    def test_query_by_id(self):
        state = _make_fixture()
        r = execute_tool(state, "query_state", {"entity_id": "video_clip_1"})
        assert r["success"]
        assert r["data"]["id"] == "video_clip_1"

    def test_query_not_found(self):
        state = _make_fixture()
        r = execute_tool(state, "query_state", {"entity_id": "nonexistent"})
        assert not r["success"]


class TestClipTools:
    def test_add_clip(self):
        state = _make_fixture()
        r = execute_tool(state, "add_clip", {
            "track_id": "video_track_1", "media_id": "av_media_1",
            "start": 5.0, "end": 10.0,
        })
        assert r["success"]
        assert r["clip_id"].startswith("video_clip_") or r["clip_id"].startswith("clip_")
        assert len(_get_video_clips(state)) == 2

    def test_add_clip_overlap_blocked(self):
        state = _make_fixture()
        r = execute_tool(state, "add_clip", {
            "track_id": "video_track_1", "media_id": "av_media_1",
            "start": 3.0, "end": 7.0,
        })
        assert not r["success"]
        assert "overlap" in r["error"]

    def test_update_clip(self):
        state = _make_fixture()
        r = execute_tool(state, "update_clip", {
            "clip_id": "video_clip_1", "enabled": False,
        })
        assert r["success"]
        clip = _get_clip_by_id(state, "video_clip_1")
        assert clip.enabled is False

    def test_remove_clip_cascade(self):
        state = _make_fixture()
        initial_links = _count_linked_clips(state)
        assert initial_links == 1

        # Remove clip -> cascade unlinks
        r = execute_tool(state, "remove_clip", {"clip_id": "video_clip_1"})
        assert r["success"]
        assert len(_get_video_clips(state)) == 0
        # Audio clip should have its link_group cleared
        audio_clip = _get_clip_by_id(state, "audio_clip_1")
        assert audio_clip.link_group is None

    def test_split_clip(self):
        state = _make_fixture()
        r = execute_tool(state, "split_clip", {
            "clip_id": "video_clip_1", "position": 2.5,
        })
        assert r["success"]
        clips = _get_video_clips(state)
        assert len(clips) == 2
        # First half ends at 2.5
        clip1 = _get_clip_by_id(state, r["clip_id_1"])
        assert clip1.duration.to_float() == pytest.approx(2.5, rel=0.01)
        # Second half starts at 2.5
        clip2 = _get_clip_by_id(state, r["clip_id_2"])
        assert clip2.timeline_start.to_float() == pytest.approx(2.5, rel=0.01)

    def test_split_clip_copies_effects(self):
        state = _make_fixture()
        execute_tool(state, "add_effect", {
            "clip_id": "video_clip_1", "effect_type": "brightness",
            "params": {"value": 10},
        })
        r = execute_tool(state, "split_clip", {
            "clip_id": "video_clip_1", "position": 2.5,
        })
        assert r["success"]
        # Both halves should have the brightness effect
        clip1 = _get_clip_by_id(state, r["clip_id_1"])
        clip2 = _get_clip_by_id(state, r["clip_id_2"])
        effects1 = _get_effects_on_clip(clip1)
        effects2 = _get_effects_on_clip(clip2)
        assert len(effects1) >= 1
        assert len(effects2) >= 1


class TestCaptionTools:
    def test_add_caption_with_style(self):
        state = _make_fixture()
        r = execute_tool(state, "add_caption", {
            "track_id": "video_track_1", "text": "Hello",
            "start": 6.0, "end": 9.0,
            "style": {"font_size": 36, "bold": True},
        })
        assert r["success"]
        captions = _get_caption_clips(state)
        assert len(captions) == 1
        assert captions[0].caption.style.font_size == 36
        assert captions[0].caption.style.bold is True

    def test_add_caption_audio_track_blocked(self):
        state = _make_fixture()
        r = execute_tool(state, "add_caption", {
            "track_id": "audio_track_1", "text": "No",
            "start": 0.0, "end": 1.0,
        })
        assert not r["success"]
        assert "track_type_mismatch" in r["error"] or "audio" in r["error"].lower()

    def test_update_caption_style_merge(self):
        state = _make_fixture()
        execute_tool(state, "add_caption", {
            "track_id": "video_track_1", "text": "Hi",
            "start": 6.0, "end": 8.0,
        })
        captions = _get_caption_clips(state)
        cap_id = captions[0].id
        r = execute_tool(state, "update_caption", {
            "caption_id": cap_id, "style": {"font_size": 72},
        })
        assert r["success"]
        captions = _get_caption_clips(state)
        assert captions[0].caption.style.font_size == 72

    def test_remove_caption(self):
        state = _make_fixture()
        execute_tool(state, "add_caption", {
            "track_id": "video_track_1", "text": "Bye",
            "start": 6.0, "end": 7.0,
        })
        captions = _get_caption_clips(state)
        cap_id = captions[0].id
        r = execute_tool(state, "remove_caption", {"caption_id": cap_id})
        assert r["success"]
        assert len(_get_caption_clips(state)) == 0


class TestEffectTools:
    def test_add_effect(self):
        state = _make_fixture()
        r = execute_tool(state, "add_effect", {
            "clip_id": "video_clip_1", "effect_type": "blur",
            "params": {"intensity": 50},
        })
        assert r["success"]
        clip = _get_clip_by_id(state, "video_clip_1")
        effects = _get_effects_on_clip(clip)
        assert any(e.type == "blur" for e in effects)

    def test_video_only_effect_on_audio_blocked(self):
        state = _make_fixture()
        r = execute_tool(state, "add_effect", {
            "clip_id": "audio_clip_1", "effect_type": "blur",
        })
        assert not r["success"]

    def test_audio_compatible_effect_allowed(self):
        state = _make_fixture()
        r = execute_tool(state, "add_effect", {
            "clip_id": "audio_clip_1", "effect_type": "fade_in",
            "params": {"duration": 0.5},
        })
        assert r["success"]

    def test_update_effect(self):
        state = _make_fixture()
        add_r = execute_tool(state, "add_effect", {
            "clip_id": "video_clip_1", "effect_type": "brightness",
            "params": {"value": 10},
        })
        eff_id = add_r.get("effect_id")
        r = execute_tool(state, "update_effect", {
            "effect_id": eff_id, "params": {"value": 20},
        })
        assert r["success"]


class TestTransitionTools:
    def _setup_adjacent(self):
        state = _make_fixture()
        execute_tool(state, "add_clip", {
            "track_id": "video_track_1", "media_id": "av_media_1",
            "start": 5.0, "end": 10.0,
        })
        return state

    def test_add_transition(self):
        state = self._setup_adjacent()
        clips = _get_video_clips(state)
        clip2_id = clips[1].id
        r = execute_tool(state, "add_transition", {
            "track_id": "video_track_1",
            "clip_id_1": "video_clip_1", "clip_id_2": clip2_id,
            "transition_type": "cross_dissolve",
        })
        assert r["success"]

    def test_non_adjacent_blocked(self):
        state = _make_fixture()
        execute_tool(state, "add_clip", {
            "track_id": "video_track_1", "media_id": "av_media_1",
            "start": 10.0, "end": 15.0,
        })
        clips = _get_video_clips(state)
        clip2_id = clips[1].id
        r = execute_tool(state, "add_transition", {
            "track_id": "video_track_1",
            "clip_id_1": "video_clip_1", "clip_id_2": clip2_id,
            "transition_type": "cross_dissolve",
        })
        assert not r["success"]
        assert "adjacent" in r["error"]


class TestTrackTools:
    def test_add_track(self):
        state = _make_fixture()
        r = execute_tool(state, "add_track", {
            "sequence_id": "timeline_1", "type": "video", "name": "V2",
        })
        assert r["success"]
        assert len(_get_video_tracks(state)) == 2

    def test_remove_last_track_blocked(self):
        state = _make_fixture()
        r = execute_tool(state, "remove_track", {"track_id": "video_track_1"})
        assert not r["success"]
        assert "last" in r["error"]

    def test_update_track(self):
        state = _make_fixture()
        r = execute_tool(state, "update_track", {
            "track_id": "video_track_1", "name": "Main", "locked": True,
        })
        assert r["success"]
        track = _get_video_track(state)
        assert track.locked is True


class TestMediaTools:
    def test_import_media(self):
        state = _make_fixture()
        r = execute_tool(state, "import_media", {"file_path": "/media/new.mp4"})
        assert r["success"]
        assert len(state.media) == 2

    def test_import_audio(self):
        state = _make_fixture()
        r = execute_tool(state, "import_media", {"file_path": "/media/song.mp3"})
        assert r["success"]
        audio_media = [m for m in state.media if m.type == "audio"]
        assert len(audio_media) == 1

    def test_remove_media_in_use_blocked(self):
        state = _make_fixture()
        r = execute_tool(state, "remove_media", {"media_id": "av_media_1"})
        assert not r["success"]
        assert "reference_error" in r["error"] or "in use" in r["error"].lower()


class TestSequenceTools:
    def test_add_sequence(self):
        state = _make_fixture()
        r = execute_tool(state, "add_sequence", {"name": "Second"})
        assert r["success"]
        assert len(state.timelines) == 2
        # Should auto-create V1 + A1
        new_tl_id = r["sequence_id"]
        new_tl = state.get_timeline_by_id(new_tl_id)
        assert new_tl is not None
        video_tracks = [t for t in new_tl.tracks if t.kind == "video"]
        audio_tracks = [t for t in new_tl.tracks if t.kind == "audio"]
        assert len(video_tracks) == 1
        assert len(audio_tracks) == 1

    def test_update_sequence(self):
        state = _make_fixture()
        r = execute_tool(state, "update_sequence", {
            "sequence_id": "timeline_1", "fps": 30.0,
        })
        assert r["success"]
        tl = state.get_timeline_by_id("timeline_1")
        assert tl.fps.to_float() == pytest.approx(30.0, rel=0.01)


class TestBinTool:
    def test_create_bin(self):
        state = _make_fixture()
        r = execute_tool(state, "manage_bin", {"action": "create", "name": "Footage"})
        assert r["success"]
        assert len(state.bins) == 2

    def test_rename_bin(self):
        state = _make_fixture()
        r = execute_tool(state, "manage_bin", {
            "action": "rename", "bin_id": "bin_1", "name": "Main Bin",
        })
        assert r["success"]
        assert state.bin.name == "Main Bin"


class TestLinkTools:
    def test_link_and_unlink(self):
        state = _make_fixture()
        # Remove existing link first
        execute_tool(state, "unlink_clips", {"link_id": "link_1"})
        video_clip = _get_clip_by_id(state, "video_clip_1")
        audio_clip = _get_clip_by_id(state, "audio_clip_1")
        assert video_clip.link_group is None
        assert audio_clip.link_group is None

        r = execute_tool(state, "link_clips", {
            "video_clip_id": "video_clip_1",
            "audio_clip_id": "audio_clip_1",
        })
        assert r["success"]
        video_clip = _get_clip_by_id(state, "video_clip_1")
        audio_clip = _get_clip_by_id(state, "audio_clip_1")
        assert video_clip.link_group is not None
        assert video_clip.link_group == audio_clip.link_group


class TestLegacyNames:
    def test_create_caption_maps_to_add_caption(self):
        state = _make_fixture()
        r = execute_tool(state, "create_caption", {
            "track_id": "video_track_1", "text": "Legacy",
            "start": 6.0, "end": 7.0,
        })
        assert r["success"]

    def test_delete_clip_maps_to_remove_clip(self):
        state = _make_fixture()
        r = execute_tool(state, "delete_clip", {"clip_id": "video_clip_1"})
        assert r["success"]
