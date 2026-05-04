"""
OpenAI Provider

Supports GPT-5.x, o-series, GPT-4.x, and other OpenAI models.
Uses the official openai Python SDK.

Uses sync client + asyncio.to_thread() to avoid MemoryError from
asyncio selector transport SSL buffer leak (see agent-001 ADR).
"""

import asyncio
import os
from typing import Any

from nlebench.models import EditProject
from nlebench.protocols import AgentResponse, ToolSchema
from nlebench.providers.base import CanonicalProvider, OpenProvider, TokenUsage


class OpenAIProvider(CanonicalProvider, OpenProvider):
    """
    OpenAI provider supporting both Canonical and Open tracks.

    Requires:
        - openai package: pip install openai
        - OPENAI_API_KEY environment variable (or pass api_key)
    """

    def __init__(
        self,
        model: str = "gpt-5.4",
        temperature: float = 0.0,
        max_tokens: int = 4096,
        base_url: str | None = None,
        api_key: str | None = None,
        reasoning_effort: str | None = None,
    ):
        super().__init__(
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            base_url=base_url,
            api_key=api_key,
        )
        self._client = None
        # When set ("low" | "medium" | "high"), route GPT-5.x canonical (tools+reasoning)
        # to the Responses API since chat.completions rejects reasoning_effort+tools.
        self.reasoning_effort = reasoning_effort

    @property
    def provider_name(self) -> str:
        return "openai"

    def _get_client(self):
        """Lazy initialization of OpenAI sync client.

        Uses sync client to avoid asyncio selector transport MemoryError
        (CPython SSL buffer leak + httpx circular refs, see agent-001 ADR).
        """
        if self._client is None:
            try:
                from openai import OpenAI
            except ImportError:
                raise ImportError(
                    "openai package not installed. "
                    "Install with: pip install openai"
                )

            api_key = self.api_key or os.environ.get("OPENAI_API_KEY")
            if not api_key:
                raise ValueError(
                    "OpenAI API key not provided. "
                    "Set OPENAI_API_KEY environment variable or pass api_key."
                )

            kwargs = {"api_key": api_key}
            if self.base_url:
                kwargs["base_url"] = self.base_url

            self._client = OpenAI(**kwargs)

        return self._client

    def _tools_to_openai_format(self, tools: list[ToolSchema]) -> list[dict]:
        """Convert ToolSchema list to OpenAI function format."""
        return [tool.to_openai_format() for tool in tools]

    def _tools_to_responses_format(self, tools: list[ToolSchema]) -> list[dict]:
        """Responses API expects flat tool dicts (no 'function' nesting).

        Chat Completions: {"type":"function","function":{"name":..,"parameters":..}}
        Responses API:    {"type":"function","name":..,"parameters":..}
        """
        out = []
        for tool in tools:
            d = tool.to_openai_format()
            fn = d.get("function") or {}
            out.append({
                "type": "function",
                "name": fn.get("name", d.get("name", "")),
                "description": fn.get("description", d.get("description", "")),
                "parameters": fn.get("parameters", d.get("parameters", {})),
            })
        return out

    def _use_responses_api(self) -> bool:
        """Route to Responses API when GPT-5.x + explicit reasoning_effort.

        Chat Completions rejects reasoning_effort when tools are supplied.
        """
        return self.model.startswith("gpt-5") and self.reasoning_effort is not None

    async def generate_response(
        self,
        state: EditProject,
        tools: list[ToolSchema],
        messages: list[dict],
    ) -> AgentResponse:
        """Generate tool calls using OpenAI API (canonical track)."""
        client = self._get_client()
        system_prompt = self._build_system_prompt(state)

        if self._use_responses_api():
            return await self._generate_via_responses(system_prompt, tools, messages)

        openai_tools = self._tools_to_openai_format(tools)
        api_messages = [{"role": "system", "content": system_prompt}]
        api_messages.extend(messages)

        # GPT-5+ uses max_completion_tokens instead of max_tokens
        token_param = "max_completion_tokens" if "gpt-5" in self.model or "o3" in self.model or "o4" in self.model else "max_tokens"
        # Reasoning models (o1/o3/o4) don't support temperature
        is_reasoning = self.model.startswith("o1") or self.model.startswith("o3") or self.model.startswith("o4")
        kwargs = dict(
            model=self.model,
            messages=api_messages,
            tools=openai_tools,
            tool_choice="auto",
            **{token_param: self.max_tokens},
        )
        if not is_reasoning:
            kwargs["temperature"] = self.temperature
        # o-series accepts reasoning_effort via chat.completions (architectural reasoning)
        if is_reasoning and self.reasoning_effort:
            kwargs["reasoning_effort"] = self.reasoning_effort
        response = await asyncio.to_thread(client.chat.completions.create, **kwargs)

        choice = response.choices[0]
        message = choice.message

        # Parse tool calls
        tool_calls = []
        if message.tool_calls:
            tool_calls = self._parse_tool_calls(message.tool_calls)

        # Token usage
        usage = TokenUsage()
        if response.usage:
            usage.input_tokens = response.usage.prompt_tokens
            usage.output_tokens = response.usage.completion_tokens
            usage.total_tokens = response.usage.total_tokens

        return AgentResponse(
            message=message.content or "",
            tool_calls=tool_calls if tool_calls else None,
            token_usage=usage,
        )

    async def _generate_via_responses(
        self,
        system_prompt: str,
        tools: list[ToolSchema],
        messages: list[dict],
    ) -> AgentResponse:
        """GPT-5.x canonical generation via /v1/responses (supports reasoning_effort + tools)."""
        import json as _json
        from nlebench.protocols import ToolCall

        client = self._get_client()
        responses_tools = self._tools_to_responses_format(tools)
        # Responses API accepts a similar messages-shaped `input` (system+user+assistant)
        api_input = [{"role": "system", "content": system_prompt}]
        api_input.extend(messages)

        kwargs = dict(
            model=self.model,
            input=api_input,
            tools=responses_tools,
            reasoning={"effort": self.reasoning_effort},
            max_output_tokens=self.max_tokens,
        )
        # Responses API allows tool_choice="auto" by default; explicit not needed.
        response = await asyncio.to_thread(client.responses.create, **kwargs)

        message_text = ""
        tool_calls: list[ToolCall] = []
        for item in (response.output or []):
            t = getattr(item, "type", None)
            if t == "function_call":
                args_raw = getattr(item, "arguments", "{}")
                try:
                    args = _json.loads(args_raw) if isinstance(args_raw, str) else args_raw
                except Exception:
                    args = {}
                tool_calls.append(ToolCall(
                    name=getattr(item, "name", ""),
                    arguments=args,
                    id=getattr(item, "call_id", None) or getattr(item, "id", "") or "",
                ))
            elif t == "message":
                for c in (getattr(item, "content", []) or []):
                    if getattr(c, "type", "") == "output_text":
                        message_text = getattr(c, "text", "") or message_text
            # type "reasoning" → skip (internal reasoning trace)

        usage = TokenUsage()
        u = getattr(response, "usage", None)
        if u is not None:
            usage.input_tokens = getattr(u, "input_tokens", 0) or 0
            usage.output_tokens = getattr(u, "output_tokens", 0) or 0  # includes reasoning_tokens
            usage.total_tokens = getattr(u, "total_tokens", 0) or (usage.input_tokens + usage.output_tokens)

        return AgentResponse(
            message=message_text,
            tool_calls=tool_calls if tool_calls else None,
            token_usage=usage,
        )

    async def generate_state(
        self,
        initial_state: EditProject,
        messages: list[dict],
    ) -> AgentResponse:
        """Generate final state using OpenAI API (Open Track)."""
        client = self._get_client()

        system_prompt = OpenProvider._build_system_prompt(self, initial_state)

        api_messages = [{"role": "system", "content": system_prompt}]
        api_messages.extend(messages)

        token_param = "max_completion_tokens" if "gpt-5" in self.model or "o3" in self.model or "o4" in self.model else "max_tokens"
        is_reasoning = self.model.startswith("o1") or self.model.startswith("o3") or self.model.startswith("o4")
        kwargs = dict(
            model=self.model,
            messages=api_messages,
            **{token_param: self.max_tokens},
        )
        if not is_reasoning:
            kwargs["temperature"] = self.temperature
        if self.model.startswith("gpt-5"):
            kwargs["reasoning_effort"] = "medium"
        response = await asyncio.to_thread(client.chat.completions.create, **kwargs)

        choice = response.choices[0]
        message = choice.message
        content = message.content or ""

        # Parse final state from response
        final_state = self._parse_final_state(content)

        # Token usage
        usage = TokenUsage()
        if response.usage:
            usage.input_tokens = response.usage.prompt_tokens
            usage.output_tokens = response.usage.completion_tokens
            usage.total_tokens = response.usage.total_tokens

        return AgentResponse(
            message=content,
            final_state=final_state,
            token_usage=usage,
        )
