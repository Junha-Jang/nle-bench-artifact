"""Tests for Canonical and Open track support."""

import asyncio
import pytest
import copy
from dataclasses import dataclass

from nlebench.models import (
    BenchmarkTrack,
    EditProject,
    Bin,
    Media,
    Timeline,
    Track,
    Clip,
    Rational,
    Scenario,
    VideoProperties,
    AudioProperties,
)
from nlebench.protocols import (
    CanonicalAgent,
    OpenAgent,
    ToolSchema,
    ToolCall,
    AgentResponse,
)
from nlebench.tools import get_tool_schemas, TOOL_HANDLERS
from nlebench.runner import TrackRunner


# ── Test Fixtures ──

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
                            ),
                        ],
                    ),
                    Track(
                        id="audio_track_1",
                        kind="audio",
                        name="A1",
                        clips=[],
                    ),
                ],
            ),
        ],
    )


def _make_scenario(expect_change: bool = True) -> Scenario:
    """Create a simple test scenario.

    Args:
        expect_change: If True, include video_clip_1 in expected_changed_entities
    """
    from nlebench.models import Level
    return Scenario(
        id="test_001",
        name="Test scenario",
        level=Level.L1,
        category="clip",
        description="Move clip to 5 seconds",
        fixture="single_clip",
        user_messages=["Move the clip to start at 5 seconds"],
        named_constraints_required=[
            {
                "attribute_equals": {
                    "entity": "$video_clip_1",
                    "field": "timeline_start",
                    "value": 5.0,
                },
            }
        ],
        expected_changed_entities=["video_clip_1"] if expect_change else [],
    )


# ── Mock Agents ──

class MockCanonicalAgent:
    """Mock agent for canonical track testing."""

    def __init__(self, tool_calls: list[ToolCall]):
        self._tool_calls = tool_calls

    async def generate_response(
        self,
        state: EditProject,
        tools: list[ToolSchema],
        messages: list[dict],
    ) -> AgentResponse:
        return AgentResponse(
            message="Executing tool calls",
            tool_calls=self._tool_calls,
        )


class MockOpenAgent:
    """Mock agent for open track testing."""

    def __init__(self, state_modifier):
        """
        Args:
            state_modifier: Function that takes initial_state and returns modified state
        """
        self._state_modifier = state_modifier

    async def generate_state(
        self,
        initial_state: EditProject,
        messages: list[dict],
    ) -> AgentResponse:
        final_state = self._state_modifier(copy.deepcopy(initial_state))
        return AgentResponse(
            message="Generated final state",
            final_state=final_state,
        )


# ── BenchmarkTrack Enum Tests ──

class TestBenchmarkTrack:
    def test_track_values(self):
        assert BenchmarkTrack.CANONICAL.value == "canonical"
        assert BenchmarkTrack.OPEN.value == "open"

    def test_track_from_string(self):
        assert BenchmarkTrack("canonical") == BenchmarkTrack.CANONICAL
        assert BenchmarkTrack("open") == BenchmarkTrack.OPEN


# ── Protocol Tests ──

class TestToolSchema:
    def test_get_tool_schemas(self):
        schemas = get_tool_schemas()
        assert len(schemas) == 25

    def test_tool_schema_structure(self):
        schemas = get_tool_schemas()
        for schema in schemas:
            assert schema.name
            assert schema.description
            assert isinstance(schema.parameters, dict)

    def test_tool_schema_to_openai_format(self):
        schema = ToolSchema(
            name="test_tool",
            description="A test tool",
            parameters={"type": "object", "properties": {}},
        )
        openai_fmt = schema.to_openai_format()
        assert openai_fmt["type"] == "function"
        assert openai_fmt["function"]["name"] == "test_tool"


class TestToolCall:
    def test_tool_call_creation(self):
        tc = ToolCall(name="update_clip", arguments={"clip_id": "c1", "start": 5.0})
        assert tc.name == "update_clip"
        assert tc.arguments["clip_id"] == "c1"


# ── TrackRunner Tests ──

class TestTrackRunner:
    def test_runner_initialization(self):
        runner = TrackRunner()
        assert runner.validator is not None

    def test_get_tool_schemas(self):
        runner = TrackRunner()
        schemas = runner.get_tool_schemas()
        assert len(schemas) == 25


class TestCanonicalTrack:
    def test_canonical_executes_tool_calls(self):
        """Canonical track should execute tool calls against state."""
        async def _test():
            runner = TrackRunner()

            # Agent that updates clip start to 5.0
            agent = MockCanonicalAgent([
                ToolCall(
                    name="update_clip",
                    arguments={"clip_id": "video_clip_1", "start": 5.0},
                )
            ])

            scenario = _make_scenario()
            result = await runner.run_scenario(scenario, agent, track="canonical")

            assert result.track == "canonical"
            assert len(result.tool_calls) == 1
            assert result.tool_calls[0]["name"] == "update_clip"

        asyncio.run(_test())

    def test_canonical_validates_constraints(self):
        """Canonical track should validate final state against constraints."""
        async def _test():
            runner = TrackRunner()

            # Agent that correctly moves clip to start at 5.0
            agent = MockCanonicalAgent([
                ToolCall(
                    name="update_clip",
                    arguments={"clip_id": "video_clip_1", "start": 5.0},
                )
            ])

            scenario = _make_scenario()
            result = await runner.run_scenario(scenario, agent, track="canonical")

            # Should pass since clip was moved to 5.0
            assert result.success is True
            assert result.validation.tsr is True

        asyncio.run(_test())

    def test_canonical_multiple_tool_calls(self):
        """Canonical track should execute multiple tool calls."""
        async def _test():
            runner = TrackRunner()

            # Agent that makes multiple tool calls
            agent = MockCanonicalAgent([
                ToolCall(
                    name="update_clip",
                    arguments={"clip_id": "video_clip_1", "start": 5.0},
                ),
                ToolCall(
                    name="update_clip",
                    arguments={"clip_id": "audio_clip_1", "start": 5.0},
                ),
            ])

            scenario = _make_scenario()
            result = await runner.run_scenario(scenario, agent, track="canonical")

            assert result.track == "canonical"
            assert len(result.tool_calls) == 2

        asyncio.run(_test())


class TestOpenTrack:
    def test_open_accepts_final_state(self):
        """Open track should accept final state directly."""
        async def _test():
            runner = TrackRunner()

            # Agent that directly modifies state
            def modify_state(state: EditProject) -> EditProject:
                state.timelines[0].tracks[0].clips[0].timeline_start = Rational.from_float(5.0)
                return state

            agent = MockOpenAgent(modify_state)

            scenario = _make_scenario()
            result = await runner.run_scenario(scenario, agent, track="open")

            assert result.track == "open"
            assert result.tool_calls == []  # No tool calls in open track
            assert result.validation.tsr is True  # Constraint should be met (clip at 5.0)

        asyncio.run(_test())

    def test_open_validates_constraints(self):
        """Open track should validate final state against constraints."""
        async def _test():
            runner = TrackRunner()

            # Agent that incorrectly modifies state
            def modify_state(state: EditProject) -> EditProject:
                state.timelines[0].tracks[0].clips[0].timeline_start = Rational.from_float(10.0)  # Wrong!
                return state

            agent = MockOpenAgent(modify_state)

            scenario = _make_scenario()
            result = await runner.run_scenario(scenario, agent, track="open")

            # Should fail since clip is at 10.0, not 5.0
            assert result.success is False

        asyncio.run(_test())

    def test_open_requires_final_state(self):
        """Open track should error if agent doesn't return final_state."""
        async def _test():
            runner = TrackRunner()

            class BadOpenAgent:
                async def generate_state(self, initial_state, messages):
                    return AgentResponse(message="Oops, forgot final_state")

            scenario = _make_scenario()
            result = await runner.run_scenario(scenario, BadOpenAgent(), track="open")

            assert result.success is False
            assert "final_state" in result.error_message.lower()

        asyncio.run(_test())


class TestExecutionResult:
    def test_result_includes_track(self):
        """ExecutionResult should include track field."""
        async def _test():
            runner = TrackRunner()
            agent = MockCanonicalAgent([])
            scenario = _make_scenario()

            result = await runner.run_scenario(scenario, agent, track="canonical")
            assert result.track == "canonical"

            # Open track
            agent2 = MockOpenAgent(lambda s: s)
            result2 = await runner.run_scenario(scenario, agent2, track="open")
            assert result2.track == "open"

        asyncio.run(_test())

    def test_result_to_dict_includes_track(self):
        """ExecutionResult.to_dict() should include track."""
        async def _test():
            runner = TrackRunner()
            agent = MockCanonicalAgent([])
            scenario = _make_scenario()

            result = await runner.run_scenario(scenario, agent, track="canonical")
            result_dict = result.to_dict()

            assert "track" in result_dict
            assert result_dict["track"] == "canonical"

        asyncio.run(_test())
