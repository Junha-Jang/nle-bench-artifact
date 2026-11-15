"""Tests for multi-turn template resolution."""

import pytest

from nlebench.runner.multi_turn import (
    extract_created_id,
    extract_variables,
    resolve_template,
)


class TestExtractCreatedId:
    """Test ID extraction from agent responses."""

    def test_caption_id(self):
        response = "caption_42를 추가했습니다"
        assert extract_created_id(response) == "caption_42"

    def test_clip_id(self):
        response = "I created clip_7 on track V1"
        assert extract_created_id(response) == "clip_7"

    def test_track_id(self):
        response = "Added track_3 to the sequence"
        assert extract_created_id(response) == "track_3"

    def test_no_match(self):
        response = "자막을 추가했습니다"
        assert extract_created_id(response) is None

    def test_custom_pattern(self):
        response = "ID: item-123"
        assert extract_created_id(response, r"(item-\d+)") == "item-123"

    def test_regex_prefix_stripped(self):
        response = "caption_99 created"
        assert extract_created_id(response, "regex: (caption_\\d+)") == "caption_99"


class TestResolveTemplate:
    """Test message template resolution."""

    def test_simple_string(self):
        assert resolve_template("hello", {}) == "hello"

    def test_string_with_variable(self):
        msg = "{created_id}를 강조체로 바꿔줘"
        ctx = {"created_id": "caption_42"}
        assert resolve_template(msg, ctx) == "caption_42를 강조체로 바꿔줘"

    def test_dict_with_text(self):
        msg = {"text": "{created_id}를 삭제해줘", "fallback": "방금 만든 거 삭제해줘"}
        ctx = {"created_id": "clip_5"}
        assert resolve_template(msg, ctx) == "clip_5를 삭제해줘"

    def test_dict_fallback_on_unresolved(self):
        msg = {"text": "{created_id}를 삭제해줘", "fallback": "방금 만든 거 삭제해줘"}
        ctx = {}  # No variable in context
        assert resolve_template(msg, ctx) == "방금 만든 거 삭제해줘"

    def test_dict_no_fallback(self):
        msg = {"text": "{created_id}를 삭제해줘"}
        ctx = {}
        # Without fallback, returns unresolved template
        assert resolve_template(msg, ctx) == "{created_id}를 삭제해줘"


class TestExtractVariables:
    """Test variable extraction from messages."""

    def test_extract_from_dict(self):
        msg = {
            "text": "자막 추가해줘",
            "extract": {"created_id": "regex: (caption_\\d+)"},
        }
        response = "caption_42를 추가했습니다"
        result = extract_variables(msg, response)

        assert result == {"created_id": "caption_42"}

    def test_no_extract_field(self):
        msg = {"text": "자막 추가해줘"}
        result = extract_variables(msg, "caption_42 추가")

        assert result == {}

    def test_string_message(self):
        result = extract_variables("자막 추가해줘", "caption_42 추가")
        assert result == {}

    def test_no_match(self):
        msg = {
            "text": "test",
            "extract": {"created_id": "regex: (caption_\\d+)"},
        }
        result = extract_variables(msg, "자막을 추가했습니다")
        assert result == {}
