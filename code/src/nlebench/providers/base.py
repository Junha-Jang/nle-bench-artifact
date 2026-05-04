"""
Base Provider Classes

Abstract base classes for LLM providers implementing
Canonical and Open track protocols.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from nlebench.models import EditProject
from nlebench.protocols import AgentResponse, ToolCall, ToolSchema


@dataclass
class TokenUsage:
    """Token usage statistics."""
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0


class BaseProvider(ABC):
    """Base class for LLM providers."""

    def __init__(
        self,
        model: str,
        temperature: float = 0.0,
        max_tokens: int = 4096,
        base_url: str | None = None,
        api_key: str | None = None,
    ):
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.base_url = base_url
        self.api_key = api_key

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Return provider name (e.g., 'openai', 'anthropic', 'vllm')."""
        ...


class CanonicalProvider(BaseProvider, ABC):
    """
    Provider for Canonical Track.

    Implements CanonicalAgent protocol: receives state and tools,
    returns tool calls for execution.
    """

    @abstractmethod
    async def generate_response(
        self,
        state: EditProject,
        tools: list[ToolSchema],
        messages: list[dict],
    ) -> AgentResponse:
        """
        Generate tool calls based on state and messages.

        Args:
            state: Current EditProject state
            tools: Available tool schemas
            messages: Conversation messages

        Returns:
            AgentResponse with tool_calls
        """
        ...

    def _build_system_prompt(self, state: EditProject) -> str:
        """Build system prompt with state context."""
        import json
        state_json = json.dumps(state.to_dict(), indent=2)
        return f"""You are a video editing assistant. The tools provided to you are the ONLY tools available. No additional capabilities exist beyond what these tools offer.

Current EditProject state:
```json
{state_json}
```

Analyze the user's request and use the appropriate tools to modify the project.
Always prefer using tools over just describing what should be done.
If the request is infeasible with the available tools, decline and explain why.
If the request is ambiguous or missing required parameters, ask for clarification instead of guessing.
"""

    def _parse_tool_calls(self, raw_tool_calls: list[Any]) -> list[ToolCall]:
        """Parse raw tool calls from API response."""
        tool_calls = []
        for tc in raw_tool_calls:
            if hasattr(tc, "function"):
                # OpenAI format
                import json
                name = tc.function.name
                args = json.loads(tc.function.arguments)
                call_id = tc.id if hasattr(tc, "id") else ""
            elif isinstance(tc, dict):
                name = tc.get("name") or tc.get("function", {}).get("name", "")
                args = tc.get("arguments") or tc.get("input", {})
                if isinstance(args, str):
                    import json
                    args = json.loads(args)
                call_id = tc.get("id", "")
            else:
                continue

            tool_calls.append(ToolCall(name=name, arguments=args, id=call_id))

        return tool_calls


class OpenProvider(BaseProvider, ABC):
    """
    Provider for Open Track.

    Implements OpenAgent protocol: receives initial state,
    returns final state directly.
    """

    @abstractmethod
    async def generate_state(
        self,
        initial_state: EditProject,
        messages: list[dict],
    ) -> AgentResponse:
        """
        Generate final state based on initial state and messages.

        Args:
            initial_state: Starting EditProject state
            messages: Conversation messages

        Returns:
            AgentResponse with final_state
        """
        ...

    def _build_system_prompt(self, initial_state: EditProject) -> str:
        """Build system prompt for open track."""
        import json
        state_json = json.dumps(initial_state.to_dict(), indent=2)
        return f"""You are a video editing assistant. Your task is to modify the EditProject state based on the user's request.

Initial EditProject state:
```json
{state_json}
```

Return the COMPLETE modified EditProject as valid JSON.
Only modify what the user requests - keep everything else unchanged.
Respond with ONLY the JSON, no explanations.
"""

    def _parse_final_state(self, response_text: str) -> EditProject | None:
        """Parse final state from response text."""
        import json
        import re

        # Try to extract JSON from response
        # Look for JSON code block first
        json_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", response_text)
        if json_match:
            json_str = json_match.group(1).strip()
        else:
            # Try to find raw JSON object
            json_match = re.search(r"\{[\s\S]*\}", response_text)
            if json_match:
                json_str = json_match.group(0)
            else:
                return None

        try:
            data = json.loads(json_str)
            return EditProject.from_dict(data)
        except (json.JSONDecodeError, Exception):
            return None
