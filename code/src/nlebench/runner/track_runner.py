"""
NLEBench Track Runner

Supports both Canonical and Open tracks for benchmark evaluation.

- Canonical Track: Agent makes tool calls, runner executes them
- Open Track: Agent directly produces final EditProject state
"""

import asyncio
import copy
import json
import logging
import time
from datetime import datetime
from typing import Literal, Union

from nlebench.models import (
    BenchmarkTrack,
    EditProject,
    ExecutionResult,
    Scenario,
    ValidationResult,
)
from nlebench.protocols import (
    AgentResponse,
    CanonicalAgent,
    OpenAgent,
    ToolCall,
    ToolSchema,
)
from nlebench.tools import TOOL_HANDLERS, get_tool_schemas
from nlebench.runner.validator import ConstraintValidator
from nlebench.dataset.fixtures import get_fixture

logger = logging.getLogger(__name__)


class TrackRunner:
    """
    Runs NLE-Bench scenarios for both Canonical and Open tracks.

    Usage:
        runner = TrackRunner()

        # Canonical track
        result = await runner.run_scenario(
            scenario, agent, track="canonical"
        )

        # Open track
        result = await runner.run_scenario(
            scenario, agent, track="open"
        )
    """

    def __init__(self):
        self.validator = ConstraintValidator()
        self._tool_schemas: list[ToolSchema] = []

    def get_tool_schemas(self) -> list[ToolSchema]:
        """Get the 25 canonical tool schemas."""
        if not self._tool_schemas:
            self._tool_schemas = get_tool_schemas()
        return self._tool_schemas

    async def run_scenario(
        self,
        scenario: Scenario,
        agent: Union[CanonicalAgent, OpenAgent],
        track: Literal["canonical", "open"] = "canonical",
        run_number: int = 0,
        timeout_seconds: float = 120.0,
    ) -> ExecutionResult:
        """
        Run a single scenario with the specified track.

        Args:
            scenario: Scenario to run
            agent: Agent implementing CanonicalAgent or OpenAgent protocol
            track: "canonical" or "open"
            run_number: Run number (0-indexed)
            timeout_seconds: Timeout for agent execution

        Returns:
            ExecutionResult with metrics and validation
        """
        started_at = datetime.now()

        # Load initial state from fixture
        initial_state = get_fixture(scenario.fixture)
        initial_state_json = json.dumps(initial_state.to_dict())

        # Build messages from scenario
        messages = self._build_messages(scenario)

        try:
            if track == "canonical":
                final_state, tool_calls, response = await asyncio.wait_for(
                    self._run_canonical(initial_state, messages, agent),
                    timeout=timeout_seconds,
                )
            else:  # open
                final_state, tool_calls, response = await asyncio.wait_for(
                    self._run_open(initial_state, messages, agent),
                    timeout=timeout_seconds,
                )
        except asyncio.TimeoutError:
            return ExecutionResult(
                scenario_id=scenario.id,
                run_number=run_number,
                success=False,
                validation=ValidationResult(
                    tsr=False,
                    csr=False,
                    ovr=1.0,
                    feasibility=scenario.feasibility,
                    behavior="noop",
                    state_changed=False,
                    error_message="Timeout",
                ),
                track=track,
                latency_ms=timeout_seconds * 1000,
                error_message=f"Timeout after {timeout_seconds}s",
                started_at=started_at,
                completed_at=datetime.now(),
            )
        except Exception as e:
            import traceback
            err_detail = f"{type(e).__name__}: {e}" if str(e) else type(e).__name__
            logger.error(f"Scenario {scenario.id} failed in {track} track: {err_detail}")
            logger.error(f"Traceback:\n{traceback.format_exc()}")
            return ExecutionResult(
                scenario_id=scenario.id,
                run_number=run_number,
                success=False,
                validation=ValidationResult(
                    tsr=False,
                    csr=False,
                    ovr=1.0,
                    feasibility=scenario.feasibility,
                    behavior="noop",
                    state_changed=False,
                    error_message=err_detail,
                ),
                track=track,
                error_message=err_detail,
                started_at=started_at,
                completed_at=datetime.now(),
            )

        final_state_json = json.dumps(final_state.to_dict())

        # Validate constraints
        validation = self.validator.validate(
            initial_state,
            final_state,
            scenario,
        )

        # Behavioral fields — populated for ALL scenarios (needed for BPM + unified SR)
        from nlebench.metrics.calibration import check_refusal, check_clarification, check_state_unchanged
        validation.feasibility = scenario.feasibility
        state_unchanged = check_state_unchanged(
            json.dumps(initial_state.to_dict()),
            final_state_json,
        )
        validation.state_changed = not state_unchanged
        refused = check_refusal(response.message or "")
        asked = check_clarification(response.message or "")
        validation.refusal_appropriate = refused
        validation.asked_clarification = asked
        if tool_calls:
            validation.behavior = "execute"
        elif refused:
            validation.behavior = "refuse"
        elif asked:
            validation.behavior = "clarify"
        else:
            validation.behavior = "noop"

        completed_at = datetime.now()
        latency_ms = (completed_at - started_at).total_seconds() * 1000

        # Extract token usage if available
        input_tokens = 0
        output_tokens = 0
        if response.token_usage:
            if hasattr(response.token_usage, "input_tokens"):
                input_tokens = response.token_usage.input_tokens
            if hasattr(response.token_usage, "output_tokens"):
                output_tokens = response.token_usage.output_tokens

        return ExecutionResult(
            scenario_id=scenario.id,
            run_number=run_number,
            success=validation.passed,
            validation=validation,
            track=track,
            initial_state_json=initial_state_json,
            final_state_json=final_state_json,
            latency_ms=latency_ms,
            token_usage=input_tokens + output_tokens,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            tool_calls=[self._serialize_tool_call(tc) for tc in tool_calls],
            agent_response=response.message,
            started_at=started_at,
            completed_at=completed_at,
        )

    async def _run_canonical(
        self,
        initial_state: EditProject,
        messages: list[dict],
        agent: CanonicalAgent,
    ) -> tuple[EditProject, list[ToolCall], AgentResponse]:
        """
        Run canonical track: agent makes tool calls, we execute them.

        Returns:
            (final_state, tool_calls, response)
        """
        state = copy.deepcopy(initial_state)
        tools = self.get_tool_schemas()
        all_tool_calls: list[ToolCall] = []

        # Agent generates response with tool calls
        response = await agent.generate_response(state, tools, messages)

        if response.tool_calls:
            for tool_call in response.tool_calls:
                all_tool_calls.append(tool_call)

                # Execute tool call against state
                handler = TOOL_HANDLERS.get(tool_call.name)
                if handler is None:
                    logger.warning(f"Unknown tool: {tool_call.name}")
                    continue

                try:
                    result = handler(state, tool_call.arguments)
                except (KeyError, TypeError) as exc:
                    # Model supplied malformed / missing arguments. Treat as
                    # a tool-level error rather than a scenario-level crash
                    # so the pipeline records `behavior=execute` (the model
                    # *tried* to call a tool) and continues with the next
                    # tool call. Other exception types propagate — those are
                    # likely genuine bugs in our handler code.
                    logger.warning(
                        f"Tool {tool_call.name} raised {type(exc).__name__}: "
                        f"{exc} (args={tool_call.arguments})"
                    )
                    continue

                if result.get("status") == "error":
                    logger.warning(
                        f"Tool {tool_call.name} failed: {result.get('message')}"
                    )

        return state, all_tool_calls, response

    async def _run_open(
        self,
        initial_state: EditProject,
        messages: list[dict],
        agent: OpenAgent,
    ) -> tuple[EditProject, list[ToolCall], AgentResponse]:
        """
        Run open track: agent directly produces final state.

        Returns:
            (final_state, tool_calls (empty), response)
        """
        response = await agent.generate_state(initial_state, messages)

        if response.final_state is None:
            raise ValueError("OpenAgent did not return final_state")

        return response.final_state, [], response

    def _build_messages(self, scenario: Scenario) -> list[dict]:
        """Build message list from scenario."""
        messages = []

        # Use turns if available, else user_messages
        if scenario.turns:
            for turn in scenario.turns:
                messages.append({"role": "user", "content": turn.user})
        else:
            for msg in scenario.user_messages:
                messages.append({"role": "user", "content": msg})

        return messages

    def _serialize_tool_call(self, tool_call: ToolCall) -> dict:
        """Serialize tool call for JSON storage."""
        return {
            "name": tool_call.name,
            "arguments": tool_call.arguments,
            "id": tool_call.id,
        }


# Convenience function
async def run_with_track(
    scenario: Scenario,
    agent: Union[CanonicalAgent, OpenAgent],
    track: Literal["canonical", "open"] = "canonical",
) -> ExecutionResult:
    """
    Convenience function to run a single scenario with track support.

    Args:
        scenario: Scenario to run
        agent: Agent implementing CanonicalAgent or OpenAgent
        track: "canonical" or "open"

    Returns:
        ExecutionResult
    """
    runner = TrackRunner()
    return await runner.run_scenario(scenario, agent, track=track)
