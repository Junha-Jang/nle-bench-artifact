"""
Anthropic Provider

Supports Claude models (Opus, Sonnet, Haiku).
Uses the official anthropic Python SDK.

Uses sync client + asyncio.to_thread() to avoid MemoryError from
asyncio selector transport SSL buffer leak (see agent-001 ADR).
"""

import asyncio
import os
from typing import Any

from nlebench.models import EditProject
from nlebench.protocols import AgentResponse, ToolSchema
from nlebench.providers.base import CanonicalProvider, OpenProvider, TokenUsage


class AnthropicProvider(CanonicalProvider, OpenProvider):
    """
    Anthropic provider supporting both Canonical and Open tracks.

    Requires:
        - anthropic package: pip install anthropic
        - ANTHROPIC_API_KEY environment variable (or pass api_key)
    """

    def __init__(
        self,
        model: str = "claude-sonnet-4-6-2026-02-17",
        temperature: float = 0.0,
        max_tokens: int = 4096,
        base_url: str | None = None,
        api_key: str | None = None,
    ):
        super().__init__(
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            base_url=base_url,
            api_key=api_key,
        )
        self._client = None

    @property
    def provider_name(self) -> str:
        return "anthropic"

    def _get_client(self):
        """Lazy initialization of Anthropic sync client.

        Uses sync client to avoid asyncio selector transport MemoryError
        (CPython SSL buffer leak + httpx circular refs, see agent-001 ADR).
        """
        if self._client is None:
            try:
                from anthropic import Anthropic
            except ImportError:
                raise ImportError(
                    "anthropic package not installed. "
                    "Install with: pip install anthropic"
                )

            api_key = self.api_key or os.environ.get("ANTHROPIC_API_KEY")
            if not api_key:
                raise ValueError(
                    "Anthropic API key not provided. "
                    "Set ANTHROPIC_API_KEY environment variable or pass api_key."
                )

            kwargs = {"api_key": api_key}
            if self.base_url:
                kwargs["base_url"] = self.base_url

            self._client = Anthropic(**kwargs)

        return self._client

    def _tools_to_anthropic_format(self, tools: list[ToolSchema]) -> list[dict]:
        """Convert ToolSchema list to Anthropic tool format."""
        anthropic_tools = []
        for tool in tools:
            anthropic_tools.append({
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.parameters,
            })
        return anthropic_tools

    async def generate_response(
        self,
        state: EditProject,
        tools: list[ToolSchema],
        messages: list[dict],
    ) -> AgentResponse:
        """Generate tool calls using Anthropic API."""
        client = self._get_client()

        system_prompt = self._build_system_prompt(state)
        anthropic_tools = self._tools_to_anthropic_format(tools)

        # Convert messages to Anthropic format
        api_messages = []
        for msg in messages:
            api_messages.append({
                "role": msg["role"],
                "content": msg["content"],
            })

        # Thinking mode: Sonnet 4.6 / Haiku 4.5 support extended thinking via `thinking` param.
        # When enabled, temperature must be 1.0 and max_tokens must exceed budget_tokens.
        thinking_budgets = {
            "claude-sonnet-4-6": 8192,
            "claude-sonnet-4.6": 8192,
            "claude-haiku-4-5": 4096,
            "claude-haiku-4.5": 4096,
        }
        thinking_budget = next((b for k, b in thinking_budgets.items() if k in self.model), None)
        call_kwargs = dict(
            model=self.model,
            system=system_prompt,
            messages=api_messages,
            tools=anthropic_tools,
            max_tokens=max(self.max_tokens, thinking_budget + 2048) if thinking_budget else self.max_tokens,
        )
        if thinking_budget:
            call_kwargs["thinking"] = {"type": "enabled", "budget_tokens": thinking_budget}
            call_kwargs["temperature"] = 1.0
        else:
            call_kwargs["temperature"] = self.temperature
        response = await asyncio.to_thread(
            client.messages.create,
            **call_kwargs,
        )

        # Parse response (skip thinking blocks; extract text + tool_use)
        message_content = ""
        tool_calls = []

        for block in response.content:
            if block.type == "text":
                message_content = block.text
            elif block.type == "tool_use":
                from nlebench.protocols import ToolCall
                tool_calls.append(ToolCall(
                    name=block.name,
                    arguments=block.input,
                    id=block.id,
                ))

        # Token usage
        usage = TokenUsage()
        if response.usage:
            usage.input_tokens = response.usage.input_tokens
            usage.output_tokens = response.usage.output_tokens
            usage.total_tokens = usage.input_tokens + usage.output_tokens

        return AgentResponse(
            message=message_content,
            tool_calls=tool_calls if tool_calls else None,
            token_usage=usage,
        )

    async def generate_state(
        self,
        initial_state: EditProject,
        messages: list[dict],
    ) -> AgentResponse:
        """Generate final state using Anthropic API (Open Track)."""
        client = self._get_client()

        from nlebench.providers.base import OpenProvider
        system_prompt = OpenProvider._build_system_prompt(self, initial_state)

        # Convert messages to Anthropic format
        api_messages = []
        for msg in messages:
            api_messages.append({
                "role": msg["role"],
                "content": msg["content"],
            })

        thinking_budgets = {
            "claude-sonnet-4-6": 8192,
            "claude-sonnet-4.6": 8192,
            "claude-haiku-4-5": 4096,
            "claude-haiku-4.5": 4096,
        }
        thinking_budget = next((b for k, b in thinking_budgets.items() if k in self.model), None)
        call_kwargs = dict(
            model=self.model,
            system=system_prompt,
            messages=api_messages,
            max_tokens=max(self.max_tokens, thinking_budget + 2048) if thinking_budget else self.max_tokens,
        )
        if thinking_budget:
            call_kwargs["thinking"] = {"type": "enabled", "budget_tokens": thinking_budget}
            call_kwargs["temperature"] = 1.0
        else:
            call_kwargs["temperature"] = self.temperature
        response = await asyncio.to_thread(
            client.messages.create,
            **call_kwargs,
        )

        # Extract text content (skip thinking blocks)
        content = ""
        for block in response.content:
            if block.type == "text":
                content = block.text
                break

        # Parse final state from response
        final_state = self._parse_final_state(content)

        # Token usage
        usage = TokenUsage()
        if response.usage:
            usage.input_tokens = response.usage.input_tokens
            usage.output_tokens = response.usage.output_tokens
            usage.total_tokens = usage.input_tokens + usage.output_tokens

        return AgentResponse(
            message=content,
            final_state=final_state,
            token_usage=usage,
        )
