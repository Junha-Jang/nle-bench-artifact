"""
Canonical Tool Executor (25 tools)

Executes the 25 canonical tools against an EditProject instance (v4.3 schema).
"""

from __future__ import annotations

import os
from typing import Any, Optional

from nlebench.models import (
    Bin,
    Caption,
    Clip,
    ClipAudio,
    EditProject,
    Media,
    NativeBlock,
    Rational,
    Speed,
    SpeedPoint,
    TextStyle,
    Timeline,
    Title,
    Track,
    Transform,
    Transition,
    VideoProperties,
    AudioProperties,
)
from nlebench.tools.schema import LEGACY_TOOL_NAME_MAP


# ──────────────────────────────────────────────
# ID generation
# ──────────────────────────────────────────────

def _next_id(state: EditProject, prefix: str) -> str:
    """Generate sequential ID like 'clip_5'."""
    max_num = 0
    for eid in state.collect_all_ids():
        if eid.startswith(prefix + "_"):
            suffix = eid[len(prefix) + 1:]
            if suffix.isdigit():
                max_num = max(max_num, int(suffix))
    return f"{prefix}_{max_num + 1}"


# ──────────────────────────────────────────────
# Time helpers
# ──────────────────────────────────────────────

def _to_rational(value: float) -> Rational:
    """Convert float seconds to Rational."""
    return Rational.from_float(value)


def _to_float(r: Optional[Rational]) -> float:
    """Convert Rational to float seconds."""
    return r.to_float() if r else 0.0


# ──────────────────────────────────────────────
# Lookup helpers
# ──────────────────────────────────────────────

def _find_track(state: EditProject, track_id: str) -> tuple[Optional[Track], Optional[Timeline]]:
    """Find a track and its parent timeline."""
    for timeline in state.timelines:
        for track in timeline.tracks:
            if track.id == track_id:
                return track, timeline
    return None, None


def _find_clip(state: EditProject, clip_id: str) -> tuple[Optional[Clip], Optional[Track], Optional[Timeline]]:
    """Find a clip, its parent track, and timeline."""
    for timeline in state.timelines:
        for track in timeline.tracks:
            for clip in track.clips:
                if clip.id == clip_id:
                    return clip, track, timeline
    return None, None, None


def _find_media(state: EditProject, media_id: str) -> Optional[Media]:
    """Find a media asset."""
    for m in state.media:
        if m.id == media_id:
            return m
    return None


def _find_timeline(state: EditProject, timeline_id: str) -> Optional[Timeline]:
    """Find a timeline."""
    for t in state.timelines:
        if t.id == timeline_id:
            return t
    return None


def _find_transition(state: EditProject, transition_id: str) -> tuple[Optional[Transition], Optional[Track]]:
    """Find a transition and its parent track."""
    for timeline in state.timelines:
        for track in timeline.tracks:
            for tr in track.transitions:
                if tr.id == transition_id:
                    return tr, track
    return None, None


def _find_bin(state: EditProject, bin_id: str) -> Optional[Bin]:
    """Find a bin by ID (recursive)."""
    def _search(b: Bin) -> Optional[Bin]:
        if b.id == bin_id:
            return b
        for child in b.bins:
            result = _search(child)
            if result:
                return result
        return None
    return _search(state.bin)


def _clips_on_track(track: Track) -> list[Clip]:
    """Get all clips on a track, sorted by start time."""
    return sorted(track.clips, key=lambda c: c.timeline_start.to_float())


def _check_overlap(clips: list[Clip], new_start: float, new_end: float, exclude_id: str = "") -> bool:
    """Return True if [new_start, new_end) overlaps any clip (excluding exclude_id)."""
    for c in clips:
        if c.id == exclude_id:
            continue
        c_start = c.timeline_start.to_float()
        c_end = c_start + c.duration.to_float()
        if new_start < c_end and new_end > c_start:
            return True
    return False


def _media_kind(media: Media) -> str:
    """Return 'video', 'audio', or 'av' based on media properties."""
    has_video = media.video is not None or media.type in ("video", "image")
    has_audio = media.audio is not None or media.type == "audio"
    if has_video and has_audio:
        return "av"
    elif has_video:
        return "video"
    elif has_audio:
        return "audio"
    return "video"  # default


def _error(code: str, msg: str) -> dict:
    return {"success": False, "error": f"{code}: {msg}"}


# ──────────────────────────────────────────────
# Main dispatch
# ──────────────────────────────────────────────

def execute_tool(state: EditProject, tool_name: str, arguments: dict) -> dict:
    """
    Execute a canonical tool against an EditProject.

    Args:
        state: EditProject to modify (mutated in-place)
        tool_name: One of the 25 canonical tool names (or legacy name)
        arguments: Tool arguments dict

    Returns:
        Result dict with 'success' bool and relevant data
    """
    # Map legacy tool names
    canonical_name = LEGACY_TOOL_NAME_MAP.get(tool_name, tool_name)

    handler = TOOL_HANDLERS.get(canonical_name)
    if handler is None:
        return _error("unknown_tool", f"Unknown tool: {tool_name}")
    return handler(state, arguments)


# ══════════════════════════════════════════════
# CLIP TOOLS (4)
# ══════════════════════════════════════════════

def _handle_add_clip(state: EditProject, args: dict) -> dict:
    track_id = args["track_id"]
    clip_type = args.get("type")  # Optional: "video"|"audio"|"title"|"gap"
    media_id = args.get("media_id")
    start = float(args["start"])
    end = float(args["end"])

    track, timeline = _find_track(state, track_id)
    if track is None:
        return _error("entity_not_found", f"track_id '{track_id}' does not exist")

    if end <= start:
        return _error("constraint_violation", "end must be greater than start")

    # Title/gap clips: no media reference needed
    if clip_type in ("title", "gap"):
        if _check_overlap(track.clips, start, end):
            return _error("constraint_violation", "clip overlaps with existing clip on track")

        clip_id = _next_id(state, "clip")
        clip = Clip(
            id=clip_id,
            type=clip_type,
            name=args.get("text", clip_type)[:20] if args.get("text") else clip_type,
            timeline_start=_to_rational(start),
            duration=_to_rational(end - start),
        )
        if clip_type == "title" and args.get("text"):
            style_arg = args.get("style")
            if style_arg is not None and not isinstance(style_arg, dict):
                return _error(
                    "invalid_argument",
                    f"'style' must be a dict of TextStyle fields, got {type(style_arg).__name__}",
                )
            clip.title = Title(
                text=args["text"],
                style=TextStyle.from_dict(style_arg) if style_arg else None,
            )
        track.clips.append(clip)
        return {"success": True, "clip_id": clip_id}

    # Media-based clips: require media_id
    if not media_id:
        return _error("invalid_parameter", "media_id is required for video/audio clips")

    media = _find_media(state, media_id)
    if media is None:
        return _error("entity_not_found", f"media_id '{media_id}' does not exist")

    in_point = float(args.get("in_point", 0.0))
    out_point = float(args.get("out_point", end - start))

    # Check track kind vs media type
    media_kind = _media_kind(media)
    if track.kind == "video" and media_kind == "audio":
        return _error("track_type_mismatch", "cannot add audio-only media to video track")
    if track.kind == "audio" and media_kind == "video":
        return _error("track_type_mismatch", "cannot add video-only media to audio track")

    # Check overlap
    if _check_overlap(track.clips, start, end):
        return _error("constraint_violation", "clip overlaps with existing clip on track")

    # Determine clip type based on track kind if not specified
    if not clip_type:
        clip_type = "video" if track.kind == "video" else "audio"
    clip_id = _next_id(state, "clip")

    clip = Clip(
        id=clip_id,
        type=clip_type,
        name=media.name,
        timeline_start=_to_rational(start),
        duration=_to_rational(end - start),
        ref_id=media_id,
        ref_type="media",
        source_in=_to_rational(in_point),
        source_out=_to_rational(out_point),
    )
    track.clips.append(clip)

    return {"success": True, "clip_id": clip_id}


def _handle_update_clip(state: EditProject, args: dict) -> dict:
    clip_id = args["clip_id"]
    clip, track, timeline = _find_clip(state, clip_id)
    if clip is None:
        return _error("entity_not_found", f"clip_id '{clip_id}' does not exist")

    old_start = clip.timeline_start.to_float()
    old_duration = clip.duration.to_float()
    old_rate = float(clip.speed.effective_rate) if clip.speed else 1.0

    # Resolve speed up-front because it affects the default duration when
    # the caller does not supply an explicit end.
    new_rate = old_rate
    if "speed" in args and args["speed"] is not None:
        new_rate = float(args["speed"])
        if new_rate <= 0:
            return _error("constraint_violation", "speed must be positive")

    new_start = float(args["start"]) if "start" in args and args["start"] is not None else old_start
    if "end" in args and args["end"] is not None:
        new_end = float(args["end"])
    elif new_rate != old_rate:
        # Speed change with no explicit end: shrink/stretch the clip's
        # timeline footprint proportionally, matching Premiere/FCP default
        # behavior. A 2x speed change on a 5s clip yields a 2.5s clip;
        # a 0.5x change yields a 10s clip.
        new_end = new_start + old_duration * old_rate / new_rate
    else:
        new_end = new_start + old_duration
    target_track_id = args.get("track_id", track.id)

    if new_end <= new_start:
        return _error("constraint_violation", "end must be greater than start")

    # Whether the clip's timeline position is actually being changed.
    # Pre-existing overlaps in fixtures (e.g., captions on a video track) must
    # not cause rotation/opacity/etc edits to fail, so only re-check overlaps
    # when the clip is actually being moved or resized. A speed change that
    # implicitly resizes the clip also counts.
    position_changed = (
        ("start" in args and args["start"] is not None)
        or ("end" in args and args["end"] is not None)
        or (new_rate != old_rate)
    )

    # Track move check
    if target_track_id != track.id:
        target_track, target_timeline = _find_track(state, target_track_id)
        if target_track is None:
            return _error("entity_not_found", f"track_id '{target_track_id}' does not exist")
        if target_track.kind != track.kind:
            return _error("track_type_mismatch", f"cannot move {track.kind} clip to {target_track.kind} track")

        # Check overlap on target (always, since moving across tracks)
        if _check_overlap(target_track.clips, new_start, new_end):
            return _error("constraint_violation", "clip overlaps on target track")

        # Remove from old track
        track.clips = [c for c in track.clips if c.id != clip_id]

        # Add to new track
        target_track.clips.append(clip)
    elif position_changed:
        # Check overlap on same track only when position is being updated.
        if _check_overlap(track.clips, new_start, new_end, exclude_id=clip_id):
            return _error("constraint_violation", "clip overlaps with existing clip on track")

    clip.timeline_start = _to_rational(new_start)
    clip.duration = _to_rational(new_end - new_start)

    # Models sometimes emit every documented field with explicit nulls for
    # the ones they don't want to change (because the JSON schema lists them
    # all). Treat `None` the same as "not provided" — skip it.
    def _present(key: str) -> bool:
        return key in args and args[key] is not None

    if _present("in_point"):
        clip.source_in = _to_rational(float(args["in_point"]))
    if _present("out_point"):
        clip.source_out = _to_rational(float(args["out_point"]))
    if new_rate != old_rate:
        # new_rate was resolved above; apply the Speed object now.
        clip.speed = Speed(speed_map=[SpeedPoint(time=Rational(0, 1), rate=new_rate)])
    if _present("enabled"):
        clip.enabled = bool(args["enabled"])

    # Audio fields — support both flat (volume=-6) and nested (audio={volume: -6})
    audio_args: dict = {}
    if "audio" in args and isinstance(args["audio"], dict):
        audio_args = {k: v for k, v in args["audio"].items() if v is not None}
    for k in ("volume", "pan", "muted"):
        if _present(k):
            audio_args[k] = args[k]

    if audio_args:
        if clip.audio is None:
            clip.audio = ClipAudio()
        if "volume" in audio_args:
            clip.audio.volume = float(audio_args["volume"])
            clip.volume = clip.audio.volume  # sync legacy
        if "pan" in audio_args:
            clip.audio.pan = float(audio_args["pan"])
        if "muted" in audio_args:
            clip.audio.muted = bool(audio_args["muted"])
            clip.muted = clip.audio.muted  # sync legacy

    # Transform fields
    if "transform" in args and isinstance(args["transform"], dict):
        if clip.transform is None:
            clip.transform = Transform()
        for key, val in args["transform"].items():
            if val is None or not hasattr(clip.transform, key):
                continue
            setattr(clip.transform, key, float(val))
    # Also support flat transform args (opacity, rotation, etc.)
    for tf_key in ("opacity", "rotation", "position_x", "position_y",
                    "scale_x", "scale_y", "anchor_x", "anchor_y", "skew",
                    "crop_top", "crop_bottom", "crop_left", "crop_right"):
        if _present(tf_key):
            if clip.transform is None:
                clip.transform = Transform()
            setattr(clip.transform, tf_key, float(args[tf_key]))

    return {"success": True}


def _handle_remove_clip(state: EditProject, args: dict) -> dict:
    clip_id = args["clip_id"]
    clip, track, timeline = _find_clip(state, clip_id)
    if clip is None:
        return _error("entity_not_found", f"clip_id '{clip_id}' does not exist")

    # Cascade: clear link_group on paired clips
    if clip.link_group:
        link_id = clip.link_group
        for tl in state.timelines:
            for t in tl.tracks:
                for c in t.clips:
                    if c.link_group == link_id and c.id != clip_id:
                        c.link_group = None

    # Cascade: remove transitions referencing this clip
    track.transitions = [t for t in track.transitions
                         if t.clip_before_id != clip_id and t.clip_after_id != clip_id]

    # Remove clip
    track.clips = [c for c in track.clips if c.id != clip_id]

    return {"success": True}


def _handle_split_clip(state: EditProject, args: dict) -> dict:
    clip_id = args["clip_id"]
    position = float(args["position"])

    clip, track, timeline = _find_clip(state, clip_id)
    if clip is None:
        return _error("entity_not_found", f"clip_id '{clip_id}' does not exist")

    clip_start = clip.timeline_start.to_float()
    clip_end = clip_start + clip.duration.to_float()

    if position <= clip_start or position >= clip_end:
        return _error("invalid_parameter",
                      f"position ({position}) must be between start ({clip_start}) and end ({clip_end})")

    # Calculate split point in source coordinates
    clip_duration = clip.duration.to_float()
    source_in = _to_float(clip.source_in)
    source_out = _to_float(clip.source_out)
    source_duration = source_out - source_in
    ratio = source_duration / clip_duration if clip_duration > 0 else 1.0
    split_offset = position - clip_start
    split_source = source_in + split_offset * ratio

    # Save original values
    original_duration = clip_duration
    original_source_out = source_out

    # Modify original clip (left half)
    clip.duration = _to_rational(position - clip_start)
    clip.source_out = _to_rational(split_source)

    # Create right half
    new_id = _next_id(state, "clip")
    # Deep copy native blocks (effects)
    copied_native = [NativeBlock(source=n.source, type=n.type, encoding=n.encoding, data=n.data)
                     for n in clip.native]
    new_clip = Clip(
        id=new_id,
        type=clip.type,
        name=clip.name,
        timeline_start=_to_rational(position),
        duration=_to_rational(clip_end - position),
        enabled=clip.enabled,
        link_group=clip.link_group,
        ref_id=clip.ref_id,
        ref_type=clip.ref_type,
        source_in=_to_rational(split_source),
        source_out=_to_rational(original_source_out),
        transform=clip.transform,
        volume=clip.volume,
        muted=clip.muted,
        native=copied_native,
    )
    track.clips.append(new_clip)

    # Remove transitions on original clip
    track.transitions = [t for t in track.transitions
                         if t.clip_before_id != clip_id and t.clip_after_id != clip_id]

    return {"success": True, "clip_id_1": clip_id, "clip_id_2": new_id}


# ══════════════════════════════════════════════
# CAPTION TOOLS (3)
# ══════════════════════════════════════════════

def _handle_add_caption(state: EditProject, args: dict) -> dict:
    track_id = args["track_id"]
    text = args["text"]
    start = float(args["start"])
    end = float(args["end"])
    style_data = args.get("style", {})
    # Models sometimes pass style as a string (e.g., "bold") instead of a dict.
    # Reject at the boundary with a structured error so the pipeline doesn't crash.
    if style_data and not isinstance(style_data, dict):
        return _error(
            "invalid_argument",
            f"'style' must be a dict of TextStyle fields, got {type(style_data).__name__}",
        )

    track, timeline = _find_track(state, track_id)
    if track is None:
        return _error("entity_not_found", f"track_id '{track_id}' does not exist")
    if track.kind not in ("video", "caption"):
        return _error("track_type_mismatch", "captions can only be added to video or caption tracks")
    if end <= start:
        return _error("constraint_violation", "end must be greater than start")

    # Check caption overlap (only among caption clips)
    caption_clips = [c for c in track.clips if c.type == "caption"]
    if _check_overlap(caption_clips, start, end):
        return _error("constraint_violation", "caption overlaps with existing caption on track")

    caption_id = _next_id(state, "caption")
    style = TextStyle.from_dict(style_data) if style_data else TextStyle()

    clip = Clip(
        id=caption_id,
        type="caption",
        name=text[:20] if len(text) > 20 else text,
        timeline_start=_to_rational(start),
        duration=_to_rational(end - start),
        caption=Caption(text=text, style=style),
    )
    track.clips.append(clip)

    return {"success": True, "caption_id": caption_id}


def _handle_update_caption(state: EditProject, args: dict) -> dict:
    caption_id = args["caption_id"]
    clip, track, timeline = _find_clip(state, caption_id)
    if clip is None or clip.type != "caption":
        return _error("entity_not_found", f"caption_id '{caption_id}' does not exist")

    old_start = clip.timeline_start.to_float()
    old_duration = clip.duration.to_float()

    new_start = float(args["start"]) if "start" in args else old_start
    new_end = float(args["end"]) if "end" in args else old_start + old_duration

    if new_end <= new_start:
        return _error("constraint_violation", "end must be greater than start")

    # Check overlap (excluding self)
    caption_clips = [c for c in track.clips if c.type == "caption" and c.id != caption_id]
    if _check_overlap(caption_clips, new_start, new_end):
        return _error("constraint_violation", "caption overlaps with existing caption")

    clip.timeline_start = _to_rational(new_start)
    clip.duration = _to_rational(new_end - new_start)

    if "text" in args:
        if clip.caption:
            clip.caption.text = args["text"]
        else:
            clip.caption = Caption(text=args["text"])

    if "style" in args:
        style_arg = args["style"]
        # Models sometimes pass style as a string (e.g., "bold",
        # "font-size:24px") instead of the expected dict of field updates.
        # Tolerate this at the boundary: if not a dict, skip the update
        # with a soft error rather than crashing the whole scenario.
        if not isinstance(style_arg, dict):
            return _error(
                "invalid_argument",
                f"'style' must be a dict of TextStyle fields, got {type(style_arg).__name__}",
            )
        if clip.caption is None:
            clip.caption = Caption(text="")
        if clip.caption.style is None:
            clip.caption.style = TextStyle()
        for key, val in style_arg.items():
            if hasattr(clip.caption.style, key):
                setattr(clip.caption.style, key, val)

    return {"success": True}


def _handle_remove_caption(state: EditProject, args: dict) -> dict:
    caption_id = args["caption_id"]
    clip, track, timeline = _find_clip(state, caption_id)
    if clip is None or clip.type != "caption":
        return _error("entity_not_found", f"caption_id '{caption_id}' does not exist")

    track.clips = [c for c in track.clips if c.id != caption_id]
    return {"success": True}


# ══════════════════════════════════════════════
# EFFECT TOOLS (3)
# ══════════════════════════════════════════════

VALID_EFFECT_TYPES = {
    "blur", "brightness", "contrast", "saturation",
    "crop", "fade_in", "fade_out",
}

VIDEO_ONLY_EFFECTS = {"blur", "brightness", "contrast", "saturation", "crop"}


def _handle_add_effect(state: EditProject, args: dict) -> dict:
    clip_id = args["clip_id"]
    effect_type = args["effect_type"]
    params = args.get("params", {})
    enabled = args.get("enabled", True)

    if effect_type not in VALID_EFFECT_TYPES:
        return _error("invalid_parameter", f"unsupported effect_type: '{effect_type}'")

    clip, track, timeline = _find_clip(state, clip_id)
    if clip is None:
        return _error("entity_not_found", f"clip_id '{clip_id}' does not exist")

    if clip.type == "audio" and effect_type in VIDEO_ONLY_EFFECTS:
        return _error("track_type_mismatch",
                      f"cannot apply video-only effect '{effect_type}' to audio clip")

    # Effects are stored as NativeBlocks in v4.3
    effect_id = _next_id(state, "effect")
    from nlebench.models import NativeBlock
    effect_block = NativeBlock(
        source="nlebench",
        type=effect_type,
        encoding="json",
        data={"id": effect_id, "params": params, "enabled": enabled},
    )
    clip.native.append(effect_block)

    return {"success": True, "effect_id": effect_id}


def _handle_update_effect(state: EditProject, args: dict) -> dict:
    if "effect_id" not in args:
        return _error("invalid_argument", "'effect_id' is required")
    effect_id = args["effect_id"]

    # Search for effect in all clips' native blocks
    for timeline in state.timelines:
        for track in timeline.tracks:
            for clip in track.clips:
                for native in clip.native:
                    if native.source == "nlebench" and isinstance(native.data, dict):
                        if native.data.get("id") == effect_id:
                            if "params" in args:
                                native.data["params"].update(args["params"])
                            if "enabled" in args:
                                native.data["enabled"] = bool(args["enabled"])
                            return {"success": True}

    return _error("entity_not_found", f"effect_id '{effect_id}' does not exist")


def _handle_remove_effect(state: EditProject, args: dict) -> dict:
    if "effect_id" not in args:
        return _error("invalid_argument", "'effect_id' is required")
    effect_id = args["effect_id"]

    # Search and remove effect from all clips
    for timeline in state.timelines:
        for track in timeline.tracks:
            for clip in track.clips:
                original_len = len(clip.native)
                clip.native = [n for n in clip.native
                               if not (n.source == "nlebench" and
                                       isinstance(n.data, dict) and
                                       n.data.get("id") == effect_id)]
                if len(clip.native) < original_len:
                    return {"success": True}

    return _error("entity_not_found", f"effect_id '{effect_id}' does not exist")


# ══════════════════════════════════════════════
# TRANSITION TOOLS (3)
# ══════════════════════════════════════════════

VALID_TRANSITION_TYPES = {"cross_dissolve", "dip_to_black", "dip_to_white", "wipe", "slide", "constant_power"}


def _handle_add_transition(state: EditProject, args: dict) -> dict:
    track_id = args["track_id"]
    clip_id_1 = args["clip_id_1"]
    clip_id_2 = args["clip_id_2"]
    transition_type = args["transition_type"]
    duration = float(args.get("duration", 1.0))

    if transition_type not in VALID_TRANSITION_TYPES:
        return _error("invalid_parameter", f"unsupported transition_type: '{transition_type}'")

    track, timeline = _find_track(state, track_id)
    if track is None:
        return _error("entity_not_found", f"track_id '{track_id}' does not exist")

    clip1, _, _ = _find_clip(state, clip_id_1)
    clip2, _, _ = _find_clip(state, clip_id_2)
    if clip1 is None:
        return _error("entity_not_found", f"clip_id_1 '{clip_id_1}' does not exist")
    if clip2 is None:
        return _error("entity_not_found", f"clip_id_2 '{clip_id_2}' does not exist")

    # Both clips must be on the same track
    track_clips = {c.id for c in track.clips}
    if clip_id_1 not in track_clips or clip_id_2 not in track_clips:
        return _error("constraint_violation", "both clips must be on the specified track")

    # Clips must be adjacent (clip1.end == clip2.start, with tolerance)
    clip1_end = clip1.timeline_start.to_float() + clip1.duration.to_float()
    clip2_start = clip2.timeline_start.to_float()
    if abs(clip1_end - clip2_start) > 0.05:
        return _error("constraint_violation",
                      f"clips are not adjacent (clip1.end={clip1_end}, clip2.start={clip2_start})")

    # Check no existing transition between these clips
    for t in track.transitions:
        if {t.clip_before_id, t.clip_after_id} == {clip_id_1, clip_id_2}:
            return _error("constraint_violation", "transition already exists between these clips")

    transition_id = _next_id(state, "transition")
    transition = Transition(
        id=transition_id,
        type=transition_type,
        duration=_to_rational(duration),
        clip_before_id=clip_id_1,
        clip_after_id=clip_id_2,
    )
    track.transitions.append(transition)

    return {"success": True, "transition_id": transition_id}


def _handle_update_transition(state: EditProject, args: dict) -> dict:
    transition_id = args["transition_id"]
    tr, track = _find_transition(state, transition_id)
    if tr is None:
        return _error("entity_not_found", f"transition_id '{transition_id}' does not exist")

    if "transition_type" in args:
        if args["transition_type"] not in VALID_TRANSITION_TYPES:
            return _error("invalid_parameter", "unsupported transition_type")
        tr.type = args["transition_type"]
    if "duration" in args:
        tr.duration = _to_rational(float(args["duration"]))

    return {"success": True}


def _handle_remove_transition(state: EditProject, args: dict) -> dict:
    transition_id = args["transition_id"]

    for timeline in state.timelines:
        for track in timeline.tracks:
            original_len = len(track.transitions)
            track.transitions = [t for t in track.transitions if t.id != transition_id]
            if len(track.transitions) < original_len:
                return {"success": True}

    return _error("entity_not_found", f"transition_id '{transition_id}' does not exist")


# ══════════════════════════════════════════════
# TRACK TOOLS (3)
# ══════════════════════════════════════════════

def _handle_add_track(state: EditProject, args: dict) -> dict:
    timeline_id = args.get("timeline_id") or args.get("sequence_id")  # Legacy alias
    if not timeline_id:
        return _error("invalid_parameter", "timeline_id or sequence_id is required")
    track_type = args.get("type") or args.get("kind")  # Accept both "type" and "kind"
    if not track_type:
        return _error("invalid_parameter", "type (or kind) is required")
    name = args.get("name")

    timeline = _find_timeline(state, timeline_id)
    if timeline is None:
        return _error("entity_not_found", f"timeline_id '{timeline_id}' does not exist")

    if track_type == "video":
        kind = "video"
        existing_count = len([t for t in timeline.tracks if t.kind == "video"])
        track_name = name or f"V{existing_count + 1}"
    elif track_type == "audio":
        kind = "audio"
        existing_count = len([t for t in timeline.tracks if t.kind == "audio"])
        track_name = name or f"A{existing_count + 1}"
    else:
        return _error("invalid_parameter", f"type must be 'video' or 'audio', got '{track_type}'")

    track_id = _next_id(state, "track")
    track = Track(
        id=track_id,
        kind=kind,
        name=track_name,
    )
    timeline.tracks.append(track)

    return {"success": True, "track_id": track_id}


def _handle_update_track(state: EditProject, args: dict) -> dict:
    track_id = args["track_id"]
    track, timeline = _find_track(state, track_id)
    if track is None:
        return _error("entity_not_found", f"track_id '{track_id}' does not exist")

    if "name" in args:
        track.name = args["name"]
    if "enabled" in args:
        track.visible = bool(args["enabled"])
    if "locked" in args:
        track.locked = bool(args["locked"])
    if "muted" in args:
        track.muted = bool(args["muted"])

    return {"success": True}


def _handle_remove_track(state: EditProject, args: dict) -> dict:
    track_id = args["track_id"]
    track, timeline = _find_track(state, track_id)
    if track is None:
        return _error("entity_not_found", f"track_id '{track_id}' does not exist")

    # Check minimum track constraint
    same_kind_tracks = [t for t in timeline.tracks if t.kind == track.kind]
    if len(same_kind_tracks) <= 1:
        return _error("constraint_violation",
                      f"cannot remove last {track.kind} track from timeline")

    # Remove track
    timeline.tracks = [t for t in timeline.tracks if t.id != track_id]

    return {"success": True}


# ══════════════════════════════════════════════
# MEDIA TOOLS (3)
# ══════════════════════════════════════════════

# Extension -> media type mapping
_MEDIA_TYPE_BY_EXT = {
    ".mp4": "video", ".mov": "video", ".avi": "video", ".mkv": "video",
    ".mp3": "audio", ".wav": "audio", ".aac": "audio", ".flac": "audio",
    ".jpg": "image", ".jpeg": "image", ".png": "image", ".bmp": "image",
    ".tiff": "image", ".gif": "image",
}


def _handle_import_media(state: EditProject, args: dict) -> dict:
    file_path = args.get("file_path") or args.get("path")
    if not file_path:
        return _error("invalid_parameter", "file_path (or path) is required")
    bin_id = args.get("bin_id")

    # Determine target bin
    if bin_id:
        target_bin = _find_bin(state, bin_id)
        if target_bin is None:
            return _error("entity_not_found", f"bin_id '{bin_id}' does not exist")
    else:
        target_bin = state.bin

    # Determine media type from extension
    _, ext = os.path.splitext(file_path.lower())
    media_type = _MEDIA_TYPE_BY_EXT.get(ext, "video")
    name = os.path.basename(file_path)

    # Default duration for imported media (harness simulation)
    default_duration = _to_rational(30.0)

    media_id = _next_id(state, "media")

    # Set video/audio properties based on type
    video_props = None
    audio_props = None
    if media_type in ("video", "image"):
        video_props = VideoProperties(width=1920, height=1080, fps=Rational(n=30000, d=1001))
        audio_props = AudioProperties() if media_type == "video" else None
    elif media_type == "audio":
        audio_props = AudioProperties()

    media = Media(
        id=media_id,
        name=name,
        type=media_type,
        path=file_path,
        duration=default_duration,
        video=video_props,
        audio=audio_props,
    )
    state.media.append(media)
    target_bin.media_ids.append(media_id)

    return {"success": True, "media_id": media_id}


def _handle_update_media(state: EditProject, args: dict) -> dict:
    media_id = args["media_id"]
    media = _find_media(state, media_id)
    if media is None:
        return _error("entity_not_found", f"media_id '{media_id}' does not exist")

    if "name" in args:
        media.name = args["name"]

    return {"success": True}


def _handle_remove_media(state: EditProject, args: dict) -> dict:
    media_id = args["media_id"]
    media = _find_media(state, media_id)
    if media is None:
        return _error("entity_not_found", f"media_id '{media_id}' does not exist")

    # Check if in use
    for timeline in state.timelines:
        for track in timeline.tracks:
            for clip in track.clips:
                if clip.ref_id == media_id:
                    return _error("reference_error", f"media '{media_id}' is in use by clip '{clip.id}'")

    # Remove from all bins
    def _remove_from_bin(b: Bin):
        if media_id in b.media_ids:
            b.media_ids.remove(media_id)
        for child in b.bins:
            _remove_from_bin(child)
    _remove_from_bin(state.bin)

    # Remove media
    state.media = [m for m in state.media if m.id != media_id]

    return {"success": True}


# ══════════════════════════════════════════════
# TIMELINE TOOLS (2)
# ══════════════════════════════════════════════

def _handle_add_timeline(state: EditProject, args: dict) -> dict:
    name = args["name"]
    width = int(args.get("width", 1920))
    height = int(args.get("height", 1080))
    fps = float(args.get("fps", 29.97))

    timeline_id = _next_id(state, "timeline")
    video_track_id = _next_id(state, "track")
    audio_track_id = f"track_{int(video_track_id.split('_')[1]) + 1}"

    timeline = Timeline(
        id=timeline_id,
        name=name,
        width=width,
        height=height,
        fps=_to_rational(fps),
        tracks=[
            Track(id=video_track_id, kind="video", name="V1"),
            Track(id=audio_track_id, kind="audio", name="A1"),
        ],
    )
    state.timelines.append(timeline)
    state.bin.timeline_ids.append(timeline_id)

    return {"success": True, "timeline_id": timeline_id, "sequence_id": timeline_id}


def _handle_update_timeline(state: EditProject, args: dict) -> dict:
    timeline_id = args.get("timeline_id") or args.get("sequence_id")  # Legacy alias
    if not timeline_id:
        return _error("invalid_parameter", "timeline_id or sequence_id is required")
    timeline = _find_timeline(state, timeline_id)
    if timeline is None:
        return _error("entity_not_found", f"timeline_id '{timeline_id}' does not exist")

    if "name" in args:
        timeline.name = args["name"]
    if "width" in args:
        timeline.width = int(args["width"])
    if "height" in args:
        timeline.height = int(args["height"])
    if "fps" in args:
        timeline.fps = _to_rational(float(args["fps"]))

    return {"success": True}


# ══════════════════════════════════════════════
# BIN TOOL (1)
# ══════════════════════════════════════════════

def _handle_manage_bin(state: EditProject, args: dict) -> dict:
    action = args["action"]

    if action == "create":
        name = args.get("name")
        if not name:
            return _error("invalid_parameter", "name is required for create")

        parent_bin_id = args.get("parent_bin_id")
        if parent_bin_id:
            parent_bin = _find_bin(state, parent_bin_id)
            if parent_bin is None:
                return _error("entity_not_found", f"parent_bin_id '{parent_bin_id}' does not exist")
        else:
            parent_bin = state.bin

        bin_id = _next_id(state, "bin")
        new_bin = Bin(id=bin_id, name=name)
        parent_bin.bins.append(new_bin)

        return {"success": True, "bin_id": bin_id}

    elif action == "rename":
        bin_id = args.get("bin_id")
        name = args.get("name")
        if not bin_id or not name:
            return _error("invalid_parameter", "bin_id and name required for rename")

        target = _find_bin(state, bin_id)
        if target is None:
            return _error("entity_not_found", f"bin_id '{bin_id}' does not exist")

        target.name = name
        return {"success": True}

    elif action == "delete":
        bin_id = args.get("bin_id")
        if not bin_id:
            return _error("invalid_parameter", "bin_id required for delete")
        if bin_id == state.bin.id:
            return _error("constraint_violation", "cannot delete root bin")

        # Find and remove from parent
        def _remove_from_parent(parent: Bin) -> bool:
            for i, child in enumerate(parent.bins):
                if child.id == bin_id:
                    parent.bins.pop(i)
                    return True
                if _remove_from_parent(child):
                    return True
            return False

        if not _remove_from_parent(state.bin):
            return _error("entity_not_found", f"bin_id '{bin_id}' does not exist")

        return {"success": True}

    elif action == "move_media":
        bin_id = args.get("bin_id")
        media_ids = args.get("media_ids", [])
        if not bin_id or not media_ids:
            return _error("invalid_parameter", "bin_id and media_ids required for move_media")

        target = _find_bin(state, bin_id)
        if target is None:
            return _error("entity_not_found", f"bin_id '{bin_id}' does not exist")

        for mid in media_ids:
            media = _find_media(state, mid)
            if media is None:
                return _error("entity_not_found", f"media_id '{mid}' does not exist")

            # Remove from all bins
            def _remove_media_from_bin(b: Bin):
                if mid in b.media_ids:
                    b.media_ids.remove(mid)
                for child in b.bins:
                    _remove_media_from_bin(child)
            _remove_media_from_bin(state.bin)

            # Add to target
            target.media_ids.append(mid)

        return {"success": True}

    return _error("invalid_parameter", f"unknown action: '{action}'")


# ══════════════════════════════════════════════
# LINK TOOLS (2)
# ══════════════════════════════════════════════

def _handle_link_clips(state: EditProject, args: dict) -> dict:
    video_clip_id = args["video_clip_id"]
    audio_clip_id = args["audio_clip_id"]

    vc, _, _ = _find_clip(state, video_clip_id)
    if vc is None or vc.type != "video":
        return _error("entity_not_found", f"video_clip_id '{video_clip_id}' is not a valid video clip")

    ac, _, _ = _find_clip(state, audio_clip_id)
    if ac is None or ac.type != "audio":
        return _error("entity_not_found", f"audio_clip_id '{audio_clip_id}' is not a valid audio clip")

    # Check not already linked
    if vc.link_group and vc.link_group == ac.link_group:
        return _error("constraint_violation", "clips are already linked")

    # Create new link group
    link_id = _next_id(state, "link")
    vc.link_group = link_id
    ac.link_group = link_id

    return {"success": True, "link_id": link_id}


def _handle_unlink_clips(state: EditProject, args: dict) -> dict:
    link_id = args.get("link_id") or args.get("link_group")
    if not link_id:
        return _error("invalid_parameter", "link_id (or link_group) is required")

    # Find and unlink clips with this link_group
    found = False
    for timeline in state.timelines:
        for track in timeline.tracks:
            for clip in track.clips:
                if clip.link_group == link_id:
                    clip.link_group = None
                    found = True

    if not found:
        return _error("entity_not_found", f"link_id '{link_id}' does not exist")

    return {"success": True}


# ══════════════════════════════════════════════
# QUERY TOOL (1)
# ══════════════════════════════════════════════

def _entity_info(entity: Any, fields: list[str] | None = None) -> dict:
    """Convert an entity to a dict, optionally filtering fields."""
    if hasattr(entity, "to_dict"):
        d = entity.to_dict()
    else:
        d = {}
        for key in dir(entity):
            if not key.startswith("_") and not callable(getattr(entity, key)):
                d[key] = getattr(entity, key)

    if fields:
        d = {k: v for k, v in d.items() if k in fields or k == "id"}

    return d


def _handle_query_state(state: EditProject, args: dict) -> dict:
    entity_type = args.get("entity_type", "all")
    entity_id = args.get("entity_id")
    track_id = args.get("track_id")
    fields = args.get("fields")

    # Single entity lookup
    if entity_id:
        # Try to find by ID
        entity = state.get_clip_by_id(entity_id)
        if entity is None:
            entity = state.get_media_by_id(entity_id)
        if entity is None:
            entity = state.get_timeline_by_id(entity_id)
        if entity is None:
            track, _ = _find_track(state, entity_id)
            entity = track
        if entity is None:
            return _error("entity_not_found", f"entity_id '{entity_id}' does not exist")
        return {"success": True, "data": _entity_info(entity, fields)}

    data: dict[str, list] = {}

    if entity_type in ("all", "clip"):
        clips = []
        for timeline in state.timelines:
            for track in timeline.tracks:
                if track_id and track.id != track_id:
                    continue
                clips.extend(track.clips)
        data["clips"] = [_entity_info(c, fields) for c in clips]

    if entity_type in ("all", "track"):
        tracks = []
        for timeline in state.timelines:
            tracks.extend(timeline.tracks)
        data["tracks"] = [_entity_info(t, fields) for t in tracks]

    if entity_type in ("all", "media"):
        data["media"] = [_entity_info(m, fields) for m in state.media]

    if entity_type in ("all", "timeline"):
        data["timelines"] = [_entity_info(t, fields) for t in state.timelines]

    if entity_type in ("all", "transition"):
        transitions = []
        for timeline in state.timelines:
            for track in timeline.tracks:
                transitions.extend(track.transitions)
        data["transitions"] = [_entity_info(t, fields) for t in transitions]

    if entity_type in ("all", "effect"):
        effects = []
        for timeline in state.timelines:
            for track in timeline.tracks:
                for clip in track.clips:
                    for native in clip.native:
                        if native.source == "nlebench" and isinstance(native.data, dict):
                            eff = {"clip_id": clip.id, "effect_id": native.data.get("id"),
                                   "effect_type": native.type, **native.data}
                            effects.append(eff)
        data["effects"] = effects

    if entity_type in ("all", "bin"):
        bins = state.bins
        data["bins"] = [_entity_info(b, fields) for b in bins]

    return {"success": True, "data": data}


# ──────────────────────────────────────────────
# Handler registry
# ──────────────────────────────────────────────

TOOL_HANDLERS: dict[str, Any] = {
    # Clip (4)
    "add_clip": _handle_add_clip,
    "update_clip": _handle_update_clip,
    "remove_clip": _handle_remove_clip,
    "split_clip": _handle_split_clip,
    # Caption (3)
    "add_caption": _handle_add_caption,
    "update_caption": _handle_update_caption,
    "remove_caption": _handle_remove_caption,
    # Effect (3)
    "add_effect": _handle_add_effect,
    "update_effect": _handle_update_effect,
    "remove_effect": _handle_remove_effect,
    # Transition (3)
    "add_transition": _handle_add_transition,
    "update_transition": _handle_update_transition,
    "remove_transition": _handle_remove_transition,
    # Track (3)
    "add_track": _handle_add_track,
    "update_track": _handle_update_track,
    "remove_track": _handle_remove_track,
    # Media (3)
    "import_media": _handle_import_media,
    "update_media": _handle_update_media,
    "remove_media": _handle_remove_media,
    # Timeline/Sequence (2)
    "add_sequence": _handle_add_timeline,  # Legacy name
    "add_timeline": _handle_add_timeline,
    "update_sequence": _handle_update_timeline,  # Legacy name
    "update_timeline": _handle_update_timeline,
    # Bin (1)
    "manage_bin": _handle_manage_bin,
    # Link (2)
    "link_clips": _handle_link_clips,
    "unlink_clips": _handle_unlink_clips,
    # Query (1)
    "query_state": _handle_query_state,
}
