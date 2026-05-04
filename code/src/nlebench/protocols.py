"""Protocol definitions for NLE-Bench agent abstraction.

Defines protocols for two benchmark tracks:
- Canonical Track: Agent makes tool calls using 25 canonical tools
- Open Track: Agent directly produces final EditProject state
"""

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from nlebench.models import EditProject


# ============================================================
# Tool Schema and Tool Call Types
# ============================================================

@dataclass
class ToolSchema:
    """Schema for a canonical tool."""
    name: str
    description: str
    parameters: dict  # JSON Schema for parameters

    def to_openai_format(self) -> dict:
        """Convert to OpenAI function-calling format."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            }
        }


@dataclass
class ToolCall:
    """A single tool call made by an agent."""
    name: str
    arguments: dict
    id: str = ""  # Optional call ID for tracking


@dataclass
class AgentResponse:
    """Response from an agent execution."""
    message: str = ""
    tool_calls: list[ToolCall] | None = None
    final_state: EditProject | None = None  # For open track
    token_usage: Any = None  # Provider-specific token info


# ============================================================
# Canonical Track Protocol
# ============================================================

@runtime_checkable
class CanonicalAgent(Protocol):
    """Protocol for Canonical Track agents.

    Agents on the Canonical Track receive:
    - Initial EditProject state
    - List of 25 canonical tool schemas
    - User messages

    They produce:
    - Tool calls that NLE-Bench executes against the state
    """

    async def generate_response(
        self,
        state: EditProject,
        tools: list[ToolSchema],
        messages: list[dict],  # [{"role": "user", "content": "..."}]
    ) -> AgentResponse:
        """Generate tool calls based on the current state and messages.

        Args:
            state: Current EditProject state (read-only reference)
            tools: Available canonical tool schemas
            messages: Conversation history

        Returns:
            AgentResponse with tool_calls to execute
        """
        ...


# ============================================================
# Open Track Protocol
# ============================================================

@runtime_checkable
class OpenAgent(Protocol):
    """Protocol for Open Track agents.

    Agents on the Open Track receive:
    - Initial EditProject state
    - User messages

    They produce:
    - Final EditProject state directly (any method allowed)
    """

    async def generate_state(
        self,
        initial_state: EditProject,
        messages: list[dict],  # [{"role": "user", "content": "..."}]
    ) -> AgentResponse:
        """Generate final state based on initial state and messages.

        Args:
            initial_state: Starting EditProject state
            messages: Conversation history

        Returns:
            AgentResponse with final_state
        """
        ...


# ============================================================
# Legacy Protocol (backwards compatibility)
# ============================================================

@runtime_checkable
class EditAgent(Protocol):
    """Protocol for editing agents that can be benchmarked.

    DEPRECATED: Use CanonicalAgent or OpenAgent instead.

    Any agent that implements this interface can be used with NLE-Bench.
    This is the legacy interface where agents maintain internal state.
    """

    @property
    def state(self) -> EditProject:
        """Current EditProject state of the agent."""
        ...

    async def chat(self, message: str) -> Any:
        """Process a user message and modify the EditProject.

        Args:
            message: User instruction for editing

        Returns:
            Agent response (implementation-specific)
        """
        ...


@runtime_checkable
class ToolEnabledAgent(EditAgent, Protocol):
    """EditAgent that exposes its tool schemas.

    Agents implementing this protocol declare the tools they support,
    enabling NLE-Bench to verify tool usage patterns.
    """

    @property
    def tools(self) -> list[dict]:
        """List of tool schemas in OpenAI function-calling format."""
        ...


@runtime_checkable
class LLMProvider(Protocol):
    """Protocol for LLM providers."""

    @property
    def model(self) -> str:
        """Model identifier."""
        ...
