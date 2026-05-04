"""
Canonical Tool Schema Definitions (25 tools)

OpenAI function-calling JSON Schema format.
Matches canonical_tools_spec.md v1.0.
"""

from __future__ import annotations

# ──────────────────────────────────────────────
# 3.1 Clip (4 tools)
# ──────────────────────────────────────────────

ADD_CLIP = {
    "type": "function",
    "function": {
        "name": "add_clip",
        "description": "Add a clip to a track.",
        "parameters": {
            "type": "object",
            "properties": {
                "track_id": {"type": "string", "description": "Target track ID."},
                "media_id": {"type": "string", "description": "Source media ID."},
                "start": {"type": "number", "description": "Timeline start position (seconds)."},
                "end": {"type": "number", "description": "Timeline end position (seconds)."},
                "in_point": {"type": "number", "description": "Media start point (seconds). Default: 0.0."},
                "out_point": {"type": "number", "description": "Media end point (seconds). Default: end - start."},
            },
            "required": ["track_id", "media_id", "start", "end"],
        },
    },
}

UPDATE_CLIP = {
    "type": "function",
    "function": {
        "name": "update_clip",
        "description": (
            "Update a clip's attributes. This is the canonical tool for setting clip "
            "properties: timeline position (start/end/track), media trim (in_point/out_point), "
            "transform (opacity, scale_x/y, rotation, position_x/y, anchor_x/y, skew, crop_*), "
            "playback (speed, enabled), and audio (volume, pan, muted). "
            "Do NOT use `add_effect` for these attributes — `add_effect` is only for stackable "
            "post-processing filters (blur, brightness, contrast, saturation, crop) and fade "
            "animations."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "clip_id": {"type": "string", "description": "Target clip ID."},
                # Timeline position
                "start": {"type": "number", "description": "New timeline start position (seconds)."},
                "end": {"type": "number", "description": "New timeline end position (seconds)."},
                "in_point": {"type": "number", "description": "New media source in-point (seconds)."},
                "out_point": {"type": "number", "description": "New media source out-point (seconds)."},
                "track_id": {"type": "string", "description": "Move to this track ID."},
                # Playback
                "speed": {"type": "number", "description": "Playback speed (1.0 = normal, 2.0 = 2x faster, 0.5 = half)."},
                "enabled": {"type": "boolean", "description": "Enable/disable clip."},
                # Transform (spatial)
                "opacity": {"type": "number", "description": "Opacity 0.0 (transparent) to 1.0 (opaque)."},
                "rotation": {"type": "number", "description": "Rotation in degrees."},
                "scale_x": {"type": "number", "description": "Horizontal scale (1.0 = original size)."},
                "scale_y": {"type": "number", "description": "Vertical scale (1.0 = original size)."},
                "position_x": {"type": "number", "description": "Horizontal position (normalized 0.0-1.0, 0.5 = center)."},
                "position_y": {"type": "number", "description": "Vertical position (normalized 0.0-1.0, 0.5 = center)."},
                "anchor_x": {"type": "number", "description": "Horizontal rotation/scale anchor (0.0-1.0)."},
                "anchor_y": {"type": "number", "description": "Vertical rotation/scale anchor (0.0-1.0)."},
                "skew": {"type": "number", "description": "Skew in degrees."},
                "crop_top": {"type": "number", "description": "Top crop (0.0-1.0 of clip height)."},
                "crop_bottom": {"type": "number", "description": "Bottom crop (0.0-1.0 of clip height)."},
                "crop_left": {"type": "number", "description": "Left crop (0.0-1.0 of clip width)."},
                "crop_right": {"type": "number", "description": "Right crop (0.0-1.0 of clip width)."},
                # Audio
                "volume": {"type": "number", "description": "Audio volume in dB (0.0 = unity, negative = quieter)."},
                "pan": {"type": "number", "description": "Audio pan (-1.0 = left, 0.0 = center, 1.0 = right)."},
                "muted": {"type": "boolean", "description": "Mute/unmute audio."},
                "audio": {
                    "type": "object",
                    "description": "Alternative nested form for audio properties: {volume, pan, muted}.",
                },
            },
            "required": ["clip_id"],
        },
    },
}

REMOVE_CLIP = {
    "type": "function",
    "function": {
        "name": "remove_clip",
        "description": "Remove a clip. Cascade-deletes effects, transitions, and link.",
        "parameters": {
            "type": "object",
            "properties": {
                "clip_id": {"type": "string", "description": "Clip ID to remove."},
            },
            "required": ["clip_id"],
        },
    },
}

SPLIT_CLIP = {
    "type": "function",
    "function": {
        "name": "split_clip",
        "description": "Split a clip into two at a given position.",
        "parameters": {
            "type": "object",
            "properties": {
                "clip_id": {"type": "string", "description": "Clip ID to split."},
                "position": {"type": "number", "description": "Split position (seconds, within clip range)."},
            },
            "required": ["clip_id", "position"],
        },
    },
}

# ──────────────────────────────────────────────
# 3.2 Caption (3 tools)
# ──────────────────────────────────────────────

ADD_CAPTION = {
    "type": "function",
    "function": {
        "name": "add_caption",
        "description": "Add a caption to a video track.",
        "parameters": {
            "type": "object",
            "properties": {
                "track_id": {"type": "string", "description": "Target video track ID."},
                "text": {"type": "string", "description": "Caption text."},
                "start": {"type": "number", "description": "Start position (seconds)."},
                "end": {"type": "number", "description": "End position (seconds)."},
                "style": {
                    "type": "object",
                    "description": "Style object: {font_family, font_size, font_color, background_color, position, bold, italic}.",
                    "properties": {
                        "font_family": {"type": "string"},
                        "font_size": {"type": "integer"},
                        "font_color": {"type": "string"},
                        "background_color": {"type": ["string", "null"]},
                        "position": {
                            "type": "string",
                            "enum": ["top_left", "top_center", "top_right", "center",
                                     "bottom_left", "bottom_center", "bottom_right"],
                        },
                        "bold": {"type": "boolean"},
                        "italic": {"type": "boolean"},
                    },
                },
            },
            "required": ["track_id", "text", "start", "end"],
        },
    },
}

UPDATE_CAPTION = {
    "type": "function",
    "function": {
        "name": "update_caption",
        "description": "Update a caption's properties.",
        "parameters": {
            "type": "object",
            "properties": {
                "caption_id": {"type": "string", "description": "Target caption ID."},
                "text": {"type": "string", "description": "New text."},
                "start": {"type": "number", "description": "New start position (seconds)."},
                "end": {"type": "number", "description": "New end position (seconds)."},
                "style": {
                    "type": "object",
                    "description": "Style updates (merged with existing, not replaced).",
                },
            },
            "required": ["caption_id"],
        },
    },
}

REMOVE_CAPTION = {
    "type": "function",
    "function": {
        "name": "remove_caption",
        "description": "Remove a caption.",
        "parameters": {
            "type": "object",
            "properties": {
                "caption_id": {"type": "string", "description": "Caption ID to remove."},
            },
            "required": ["caption_id"],
        },
    },
}

# ──────────────────────────────────────────────
# 3.3 Effect (3 tools)
# ──────────────────────────────────────────────

ADD_EFFECT = {
    "type": "function",
    "function": {
        "name": "add_effect",
        "description": (
            "Add a stackable post-processing effect or time-bounded animation to a clip. "
            "Use this for visual filters (blur, brightness, contrast, saturation, crop) and "
            "fade animations (fade_in, fade_out). "
            "Do NOT use this for clip attributes like opacity, scale, rotation, position, "
            "speed, volume, muted, or pan — those are set via `update_clip`."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "clip_id": {"type": "string", "description": "Target clip ID (video or audio)."},
                "effect_type": {
                    "type": "string",
                    "enum": ["blur", "brightness", "contrast", "saturation",
                             "crop", "fade_in", "fade_out"],
                    "description": "Effect type. Note: opacity/speed/volume are clip attributes, not effects — use update_clip.",
                },
                "params": {"type": "object", "description": "Effect parameters (type-specific)."},
                "enabled": {"type": "boolean", "description": "Enable/disable. Default: true."},
            },
            "required": ["clip_id", "effect_type"],
        },
    },
}

UPDATE_EFFECT = {
    "type": "function",
    "function": {
        "name": "update_effect",
        "description": "Update an effect's parameters.",
        "parameters": {
            "type": "object",
            "properties": {
                "effect_id": {"type": "string", "description": "Target effect ID."},
                "params": {"type": "object", "description": "New parameters (merged)."},
                "enabled": {"type": "boolean", "description": "Enable/disable."},
            },
            "required": ["effect_id"],
        },
    },
}

REMOVE_EFFECT = {
    "type": "function",
    "function": {
        "name": "remove_effect",
        "description": "Remove an effect.",
        "parameters": {
            "type": "object",
            "properties": {
                "effect_id": {"type": "string", "description": "Effect ID to remove."},
            },
            "required": ["effect_id"],
        },
    },
}

# ──────────────────────────────────────────────
# 3.4 Transition (3 tools)
# ──────────────────────────────────────────────

ADD_TRANSITION = {
    "type": "function",
    "function": {
        "name": "add_transition",
        "description": "Add a transition between two adjacent clips.",
        "parameters": {
            "type": "object",
            "properties": {
                "track_id": {"type": "string", "description": "Target track ID."},
                "clip_id_1": {"type": "string", "description": "Preceding clip ID."},
                "clip_id_2": {"type": "string", "description": "Following clip ID."},
                "transition_type": {
                    "type": "string",
                    "enum": ["cross_dissolve", "dip_to_black", "dip_to_white", "wipe", "slide"],
                    "description": "Transition type.",
                },
                "duration": {"type": "number", "description": "Transition duration (seconds). Default: 1.0."},
                "alignment": {
                    "type": "string", "enum": ["center", "start", "end"],
                    "description": "Transition alignment. Default: 'center'.",
                },
            },
            "required": ["track_id", "clip_id_1", "clip_id_2", "transition_type"],
        },
    },
}

UPDATE_TRANSITION = {
    "type": "function",
    "function": {
        "name": "update_transition",
        "description": "Update a transition's properties.",
        "parameters": {
            "type": "object",
            "properties": {
                "transition_id": {"type": "string", "description": "Target transition ID."},
                "transition_type": {"type": "string", "description": "New transition type."},
                "duration": {"type": "number", "description": "New duration (seconds)."},
                "alignment": {"type": "string", "enum": ["center", "start", "end"]},
            },
            "required": ["transition_id"],
        },
    },
}

REMOVE_TRANSITION = {
    "type": "function",
    "function": {
        "name": "remove_transition",
        "description": "Remove a transition.",
        "parameters": {
            "type": "object",
            "properties": {
                "transition_id": {"type": "string", "description": "Transition ID to remove."},
            },
            "required": ["transition_id"],
        },
    },
}

# ──────────────────────────────────────────────
# 3.5 Track (3 tools)
# ──────────────────────────────────────────────

ADD_TRACK = {
    "type": "function",
    "function": {
        "name": "add_track",
        "description": "Add a track to a sequence.",
        "parameters": {
            "type": "object",
            "properties": {
                "sequence_id": {"type": "string", "description": "Target sequence ID."},
                "type": {"type": "string", "enum": ["video", "audio"], "description": "Track type."},
                "name": {"type": "string", "description": "Track name."},
            },
            "required": ["sequence_id", "type"],
        },
    },
}

UPDATE_TRACK = {
    "type": "function",
    "function": {
        "name": "update_track",
        "description": "Update a track's properties.",
        "parameters": {
            "type": "object",
            "properties": {
                "track_id": {"type": "string", "description": "Target track ID."},
                "name": {"type": "string", "description": "New name."},
                "enabled": {"type": "boolean", "description": "Enable/disable."},
                "locked": {"type": "boolean", "description": "Lock/unlock."},
            },
            "required": ["track_id"],
        },
    },
}

REMOVE_TRACK = {
    "type": "function",
    "function": {
        "name": "remove_track",
        "description": "Remove a track and all its contents (cascade).",
        "parameters": {
            "type": "object",
            "properties": {
                "track_id": {"type": "string", "description": "Track ID to remove."},
            },
            "required": ["track_id"],
        },
    },
}

# ──────────────────────────────────────────────
# 3.6 Media (3 tools)
# ──────────────────────────────────────────────

IMPORT_MEDIA = {
    "type": "function",
    "function": {
        "name": "import_media",
        "description": "Import a media file into the project.",
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Media file path."},
                "bin_id": {"type": "string", "description": "Target bin ID (default: root bin)."},
            },
            "required": ["file_path"],
        },
    },
}

UPDATE_MEDIA = {
    "type": "function",
    "function": {
        "name": "update_media",
        "description": "Update media properties.",
        "parameters": {
            "type": "object",
            "properties": {
                "media_id": {"type": "string", "description": "Target media ID."},
                "name": {"type": "string", "description": "New display name."},
            },
            "required": ["media_id"],
        },
    },
}

REMOVE_MEDIA = {
    "type": "function",
    "function": {
        "name": "remove_media",
        "description": "Remove media from project. Fails if media is in use on timeline.",
        "parameters": {
            "type": "object",
            "properties": {
                "media_id": {"type": "string", "description": "Media ID to remove."},
            },
            "required": ["media_id"],
        },
    },
}

# ──────────────────────────────────────────────
# 3.7 Sequence (2 tools)
# ──────────────────────────────────────────────

ADD_SEQUENCE = {
    "type": "function",
    "function": {
        "name": "add_sequence",
        "description": "Create a new sequence with default V1+A1 tracks.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Sequence name."},
                "width": {"type": "integer", "description": "Resolution width (default: 1920)."},
                "height": {"type": "integer", "description": "Resolution height (default: 1080)."},
                "fps": {"type": "number", "description": "Frame rate (default: 24.0)."},
            },
            "required": ["name"],
        },
    },
}

UPDATE_SEQUENCE = {
    "type": "function",
    "function": {
        "name": "update_sequence",
        "description": "Update a sequence's properties.",
        "parameters": {
            "type": "object",
            "properties": {
                "sequence_id": {"type": "string", "description": "Target sequence ID."},
                "name": {"type": "string", "description": "New name."},
                "width": {"type": "integer", "description": "New width."},
                "height": {"type": "integer", "description": "New height."},
                "fps": {"type": "number", "description": "New frame rate."},
            },
            "required": ["sequence_id"],
        },
    },
}

# ──────────────────────────────────────────────
# 3.8 Bin (1 tool)
# ──────────────────────────────────────────────

MANAGE_BIN = {
    "type": "function",
    "function": {
        "name": "manage_bin",
        "description": "Manage bins (folders): create, rename, delete, or move media.",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["create", "rename", "delete", "move_media"],
                    "description": "Bin action.",
                },
                "bin_id": {"type": "string", "description": "Target bin ID (for rename/delete/move_media)."},
                "name": {"type": "string", "description": "Bin name (for create/rename)."},
                "parent_bin_id": {"type": "string", "description": "Parent bin ID (for create, default: root)."},
                "media_ids": {
                    "type": "array", "items": {"type": "string"},
                    "description": "Media IDs to move (for move_media).",
                },
            },
            "required": ["action"],
        },
    },
}

# ──────────────────────────────────────────────
# 3.9 Link (2 tools)
# ──────────────────────────────────────────────

LINK_CLIPS = {
    "type": "function",
    "function": {
        "name": "link_clips",
        "description": "Link a video clip and an audio clip (1:1 pair).",
        "parameters": {
            "type": "object",
            "properties": {
                "video_clip_id": {"type": "string", "description": "Video clip ID."},
                "audio_clip_id": {"type": "string", "description": "Audio clip ID."},
            },
            "required": ["video_clip_id", "audio_clip_id"],
        },
    },
}

UNLINK_CLIPS = {
    "type": "function",
    "function": {
        "name": "unlink_clips",
        "description": "Unlink a video-audio clip pair.",
        "parameters": {
            "type": "object",
            "properties": {
                "link_id": {"type": "string", "description": "Link ID to remove."},
            },
            "required": ["link_id"],
        },
    },
}

# ──────────────────────────────────────────────
# 3.10 Query (1 tool)
# ──────────────────────────────────────────────

QUERY_STATE = {
    "type": "function",
    "function": {
        "name": "query_state",
        "description": "Query the project state. The only way to read state in Canonical Track.",
        "parameters": {
            "type": "object",
            "properties": {
                "entity_type": {
                    "type": "string",
                    "enum": ["clip", "caption", "effect", "transition", "track",
                             "media", "sequence", "bin", "link", "all"],
                    "description": "Filter by entity type (default: 'all').",
                },
                "entity_id": {"type": "string", "description": "Query a specific entity by ID."},
                "track_id": {"type": "string", "description": "Filter to a specific track's children."},
                "fields": {
                    "type": "array", "items": {"type": "string"},
                    "description": "Fields to return (default: all).",
                },
            },
            "required": [],
        },
    },
}

# ──────────────────────────────────────────────
# Aggregated lists
# ──────────────────────────────────────────────

CANONICAL_TOOLS = [
    # Clip (4)
    ADD_CLIP, UPDATE_CLIP, REMOVE_CLIP, SPLIT_CLIP,
    # Caption (3)
    ADD_CAPTION, UPDATE_CAPTION, REMOVE_CAPTION,
    # Effect (3)
    ADD_EFFECT, UPDATE_EFFECT, REMOVE_EFFECT,
    # Transition (3)
    ADD_TRANSITION, UPDATE_TRANSITION, REMOVE_TRANSITION,
    # Track (3)
    ADD_TRACK, UPDATE_TRACK, REMOVE_TRACK,
    # Media (3)
    IMPORT_MEDIA, UPDATE_MEDIA, REMOVE_MEDIA,
    # Sequence (2)
    ADD_SEQUENCE, UPDATE_SEQUENCE,
    # Bin (1)
    MANAGE_BIN,
    # Link (2)
    LINK_CLIPS, UNLINK_CLIPS,
    # Query (1)
    QUERY_STATE,
]

# Legacy aliases (backwards compat with PDSP-era tool names)
LEGACY_TOOL_NAME_MAP = {
    "create_caption": "add_caption",
    "delete_caption": "remove_caption",
    "create_clip": "add_clip",
    "delete_clip": "remove_clip",
    "create_track": "add_track",
    "delete_track": "remove_track",
    "read_caption": "query_state",
    "read_clip": "query_state",
    "read_sequence": "query_state",
}

# Legacy exports (backwards compat)
CORE_TOOLS = CANONICAL_TOOLS[:7]  # Clip + Caption
SUPPLEMENTARY_TOOLS = CANONICAL_TOOLS[7:]
TOOL_SCHEMAS = CANONICAL_TOOLS
