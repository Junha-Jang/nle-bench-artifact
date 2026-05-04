"""
Google Gemini Provider

Supports Gemini 2.x / 3.x preview models via google-genai SDK.
Uses sync client + asyncio.to_thread() to match the pattern of
openai_provider.py and anthropic_provider.py (avoids asyncio selector
transport SSL buffer leak).
"""

import asyncio
import json
import os
import re

from nlebench.models import EditProject
from nlebench.protocols import AgentResponse, ToolCall, ToolSchema
from nlebench.providers.base import CanonicalProvider, OpenProvider, TokenUsage


async def _call_with_retry(fn, *args, max_retries: int = 5, **kwargs):
    """Retry Gemini API calls on 429 (rate limit) and 503 (overload).

    Honours the retryDelay suggested by Google when present; falls back to
    exponential backoff otherwise.
    """
    last_exc = None
    delay = 2.0
    for attempt in range(max_retries + 1):
        try:
            return await asyncio.to_thread(fn, *args, **kwargs)
        except Exception as e:
            msg = str(e)
            is_429 = "429" in msg or "RESOURCE_EXHAUSTED" in msg
            is_503 = "503" in msg or "UNAVAILABLE" in msg
            if not (is_429 or is_503) or attempt == max_retries:
                raise
            # Try to extract retryDelay like "10.334765837s" or "19s"
            m = re.search(r"retryDelay['\"]?:\s*['\"]?(\d+(?:\.\d+)?)s", msg)
            wait = float(m.group(1)) + 1.0 if m else delay
            await asyncio.sleep(wait)
            delay = min(delay * 2, 60.0)
            last_exc = e
    raise last_exc  # unreachable


class GoogleProvider(CanonicalProvider, OpenProvider):
    """
    Google Gemini provider supporting both Canonical and Open tracks.

    Requires:
        - google-genai package: pip install google-genai
        - GOOGLE_API_KEY (or GEMINI_API_KEY) environment variable
    """

    def __init__(
        self,
        model: str = "gemini-3-flash-preview",
        temperature: float = 0.0,
        max_tokens: int = 8192,
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
        return "google"

    def _get_client(self):
        if self._client is None:
            try:
                from google import genai
            except ImportError:
                raise ImportError(
                    "google-genai package not installed. "
                    "Install with: pip install google-genai"
                )
            api_key = (
                self.api_key
                or os.environ.get("GOOGLE_API_KEY")
                or os.environ.get("GEMINI_API_KEY")
            )
            if not api_key:
                raise ValueError(
                    "Google API key not provided. "
                    "Set GOOGLE_API_KEY environment variable or pass api_key."
                )
            self._client = genai.Client(api_key=api_key)
        return self._client

    def _tools_to_gemini_format(self, tools: list[ToolSchema]):
        """Convert ToolSchema list to Gemini Tool object with functionDeclarations."""
        from google.genai import types

        declarations = []
        for tool in tools:
            # Gemini accepts OpenAPI-style parameter schemas; strip unsupported keys.
            params = self._clean_schema(tool.parameters)
            declarations.append(
                types.FunctionDeclaration(
                    name=tool.name,
                    description=tool.description,
                    parameters=params,
                )
            )
        return [types.Tool(function_declarations=declarations)]

    def _clean_schema(self, schema: dict) -> dict:
        """Normalize OpenAPI/JSON Schema to Gemini's stricter subset.

        Gemini's FunctionDeclaration expects:
          - `type` as a single string (STRING/NUMBER/INTEGER/BOOLEAN/ARRAY/OBJECT/NULL),
            not a list like ["string", "null"]. Convert nullable-type lists to
            `type: <T>` + `nullable: true`.
          - No `additionalProperties`, `$schema`, `$defs`, `definitions`.
        """
        if not isinstance(schema, dict):
            return schema
        drop_keys = {"additionalProperties", "$schema", "$defs", "definitions"}
        cleaned: dict = {}
        for k, v in schema.items():
            if k in drop_keys:
                continue
            if k == "type" and isinstance(v, list):
                # OpenAPI-style nullable: ["string", "null"] → "string" + nullable=true
                non_null = [t for t in v if t != "null"]
                has_null = "null" in v
                if non_null:
                    cleaned["type"] = non_null[0]
                    if has_null:
                        cleaned["nullable"] = True
                else:
                    cleaned["type"] = "null"
                continue
            if isinstance(v, dict):
                cleaned[k] = self._clean_schema(v)
            elif isinstance(v, list):
                cleaned[k] = [self._clean_schema(x) if isinstance(x, dict) else x for x in v]
            else:
                cleaned[k] = v
        return cleaned

    def _messages_to_gemini_contents(self, messages: list[dict]):
        """Convert OpenAI-style messages to Gemini Content list.

        Gemini uses role='user' or role='model' (not 'assistant'). System
        messages are handled separately via system_instruction.
        """
        from google.genai import types

        contents = []
        for msg in messages:
            role = msg["role"]
            if role == "system":
                continue  # hoisted into system_instruction
            gemini_role = "model" if role == "assistant" else "user"
            contents.append(
                types.Content(
                    role=gemini_role,
                    parts=[types.Part(text=msg["content"])],
                )
            )
        return contents

    async def generate_response(
        self,
        state: EditProject,
        tools: list[ToolSchema],
        messages: list[dict],
    ) -> AgentResponse:
        """Generate tool calls via Gemini function calling (Canonical track)."""
        from google.genai import types

        client = self._get_client()
        system_prompt = self._build_system_prompt(state)
        gemini_tools = self._tools_to_gemini_format(tools)
        contents = self._messages_to_gemini_contents(messages)

        config = types.GenerateContentConfig(
            temperature=self.temperature,
            max_output_tokens=self.max_tokens,
            system_instruction=system_prompt,
            tools=gemini_tools,
            tool_config=types.ToolConfig(
                function_calling_config=types.FunctionCallingConfig(mode="AUTO")
            ),
        )

        response = await _call_with_retry(
            client.models.generate_content,
            model=self.model,
            contents=contents,
            config=config,
        )

        message_text = ""
        tool_calls: list[ToolCall] = []
        if response.candidates:
            candidate = response.candidates[0]
            if candidate.content and candidate.content.parts:
                for part in candidate.content.parts:
                    fc = getattr(part, "function_call", None)
                    if fc is not None and getattr(fc, "name", None):
                        args = dict(fc.args) if fc.args else {}
                        tool_calls.append(
                            ToolCall(name=fc.name, arguments=args, id="")
                        )
                    elif getattr(part, "text", None):
                        message_text = part.text

        usage = self._extract_usage(response)
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
        """Generate final EditProject JSON directly (Open track / Direct-Generation)."""
        from google.genai import types

        client = self._get_client()
        system_prompt = OpenProvider._build_system_prompt(self, initial_state)
        contents = self._messages_to_gemini_contents(messages)

        config = types.GenerateContentConfig(
            temperature=self.temperature,
            max_output_tokens=self.max_tokens,
            system_instruction=system_prompt,
        )

        response = await _call_with_retry(
            client.models.generate_content,
            model=self.model,
            contents=contents,
            config=config,
        )

        content = ""
        if response.candidates:
            candidate = response.candidates[0]
            if candidate.content and candidate.content.parts:
                for part in candidate.content.parts:
                    if getattr(part, "text", None):
                        content = part.text
                        break

        final_state = self._parse_final_state(content)
        usage = self._extract_usage(response)
        return AgentResponse(
            message=content,
            final_state=final_state,
            token_usage=usage,
        )

    def _extract_usage(self, response) -> TokenUsage:
        """Gemini usage_metadata includes prompt/candidate/thoughts tokens; thinking
        tokens are billed as output per Google pricing, so we fold them into output."""
        usage = TokenUsage()
        meta = getattr(response, "usage_metadata", None)
        if meta is None:
            return usage
        prompt_t = getattr(meta, "prompt_token_count", 0) or 0
        cand_t = getattr(meta, "candidates_token_count", 0) or 0
        thought_t = getattr(meta, "thoughts_token_count", 0) or 0
        total_t = getattr(meta, "total_token_count", 0) or 0
        usage.input_tokens = prompt_t
        usage.output_tokens = cand_t + thought_t
        usage.total_tokens = total_t or (prompt_t + cand_t + thought_t)
        return usage
