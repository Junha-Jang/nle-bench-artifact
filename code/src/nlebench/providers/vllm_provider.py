"""
vLLM Provider

Supports local models served via vLLM's OpenAI-compatible API.
Uses the openai Python SDK with custom base_url.

vLLM serves models with an OpenAI-compatible API at:
    http://localhost:8000/v1

Start vLLM server:
    python -m vllm.entrypoints.openai.api_server \\
        --model Qwen/Qwen3-32B \\
        --tensor-parallel-size 4

Environment variables:
    VLLM_BASE_URL: Base URL for vLLM server (default: http://localhost:8000/v1)
    VLLM_API_KEY: API key if required (default: "EMPTY")
"""

import os
from typing import Any

from nlebench.models import EditProject
from nlebench.protocols import AgentResponse, ToolSchema
from nlebench.providers.base import CanonicalProvider, OpenProvider, TokenUsage


# Default vLLM server URL
DEFAULT_VLLM_BASE_URL = "http://localhost:8000/v1"
DEFAULT_VLLM_API_KEY = "EMPTY"  # vLLM uses "EMPTY" as placeholder


class VLLMProvider(CanonicalProvider, OpenProvider):
    """
    vLLM provider supporting both Canonical and Open tracks.

    vLLM serves models with an OpenAI-compatible API, so this provider
    uses the openai SDK with a custom base_url.

    Requires:
        - openai package: pip install openai
        - Running vLLM server

    Example:
        # Start vLLM server
        python -m vllm.entrypoints.openai.api_server \\
            --model Qwen/Qwen3-32B

        # Use provider
        provider = VLLMProvider(
            model="Qwen/Qwen3-32B",
            base_url="http://localhost:8000/v1"
        )
    """

    def __init__(
        self,
        model: str,
        temperature: float = 0.0,
        # 1024 is sufficient for tool-call JSON (text mode output is rarely
        # longer than a few hundred tokens) and halves tail latency vs 2048.
        max_tokens: int = 1024,
        base_url: str | None = None,
        api_key: str | None = None,
        tool_mode: str = "auto",
        seed: int | None = 42,
    ):
        # Use environment variables or defaults
        base_url = base_url or os.environ.get("VLLM_BASE_URL", DEFAULT_VLLM_BASE_URL)
        api_key = api_key or os.environ.get("VLLM_API_KEY", DEFAULT_VLLM_API_KEY)

        super().__init__(
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            base_url=base_url,
            api_key=api_key,
        )
        self._client = None
        # Tool calling mode:
        #   "native" = use vLLM's OpenAI-compatible tool calling (requires --tool-call-parser on server)
        #   "text"   = skip native, go straight to text-based JSON prompting
        #   "auto"   = try native first, fallback to text (legacy behavior)
        self.tool_mode = tool_mode
        self.seed = seed
        # Tri-state cache for "does this model accept a separate system role?"
        #   None  = unknown, will try and detect
        #   True  = confirmed supported (happy path)
        #   False = confirmed unsupported (e.g. Gemma-2 family), merge system
        #           prompt into the first user message before sending.
        self._supports_system_role: bool | None = None

    @property
    def provider_name(self) -> str:
        return "vllm"

    def _extra_body(self) -> dict | None:
        """Return provider-level extras for chat.completions.create (e.g. Qwen3.5 thinking toggle).

        Qwen3.5 <=9B defaults to thinking OFF in its chat template; pin it ON
        so small-tier results are comparable with Qwen3.5 >=27B (default ON).
        """
        m = self.model.lower()
        qwen35_small = ("qwen3.5-0.8b", "qwen3.5-2b", "qwen3.5-4b", "qwen3.5-9b")
        if any(tag in m for tag in qwen35_small):
            return {"chat_template_kwargs": {"enable_thinking": True}}
        return None

    def _get_client(self):
        """Lazy initialization of OpenAI client pointing to vLLM."""
        if self._client is None:
            try:
                from openai import AsyncOpenAI
            except ImportError:
                raise ImportError(
                    "openai package not installed. "
                    "Install with: pip install openai"
                )

            self._client = AsyncOpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
            )

        return self._client

    def _tools_to_openai_format(self, tools: list[ToolSchema]) -> list[dict]:
        """Convert ToolSchema list to OpenAI function format."""
        return [tool.to_openai_format() for tool in tools]

    def _compose_messages(
        self, system_prompt: str, user_messages: list[dict]
    ) -> list[dict]:
        """
        Build the message list to send to the model, honouring the cached
        system-role capability flag.

        If the model has been confirmed to NOT support a separate system role
        (e.g. Gemma-2 family), the system prompt is prepended to the first
        user message. Additionally, consecutive user messages are merged into
        one because the same strict models also typically require alternating
        user/assistant roles.
        """
        if self._supports_system_role is False:
            merged = [dict(m) for m in user_messages]
            if merged and merged[0].get("role") == "user":
                merged[0]["content"] = (
                    f"{system_prompt}\n\n---\n\n"
                    f"{merged[0].get('content', '')}"
                )
            else:
                merged.insert(
                    0, {"role": "user", "content": system_prompt}
                )

            # Collapse consecutive user messages (strict models like Gemma-2
            # require alternating user/assistant/user/...). We join multi-turn
            # user inputs with a clear separator so the model can still
            # distinguish them.
            collapsed: list[dict] = []
            for msg in merged:
                if (
                    collapsed
                    and collapsed[-1]["role"] == "user"
                    and msg["role"] == "user"
                ):
                    collapsed[-1] = dict(collapsed[-1])
                    collapsed[-1]["content"] = (
                        f"{collapsed[-1]['content']}\n\n"
                        f"[next user turn]\n{msg['content']}"
                    )
                else:
                    collapsed.append(msg)
            return collapsed
        # Default (None or True): send system role separately.
        return [{"role": "system", "content": system_prompt}] + list(user_messages)

    @staticmethod
    def _is_system_role_unsupported_error(exc: Exception) -> bool:
        """Detect a 400 response from the server complaining about system role."""
        msg = str(exc).lower()
        return "system role" in msg and ("not supported" in msg or "unsupported" in msg)

    @staticmethod
    def _parse_context_overflow(exc: Exception) -> tuple[int, int] | None:
        """
        If the exception is a context-length 400 error, extract the context
        limit and input token count reported by the server. Returns
        (context_limit, input_tokens) or None if it isn't that kind of error.

        Example server message:
            "This model's maximum context length is 8192 tokens. However, you
            requested 4096 output tokens and your prompt contains at least
            4097 input tokens..."
        """
        import re
        msg = str(exc)
        if "maximum context length" not in msg.lower():
            return None
        m_ctx = re.search(r"maximum context length is (\d+)", msg)
        m_in = re.search(r"prompt contains at least (\d+)", msg)
        if not (m_ctx and m_in):
            return None
        return int(m_ctx.group(1)), int(m_in.group(1))

    def _shrink_max_tokens_for_context(self, exc: Exception) -> bool:
        """
        If `exc` is a context-overflow error, reduce `self.max_tokens` to fit
        under the limit with a small safety margin and return True. Otherwise
        return False.
        """
        parsed = self._parse_context_overflow(exc)
        if parsed is None:
            return False
        context_limit, input_tokens = parsed
        # Leave 128-token safety margin for tokenization rounding.
        new_max = max(256, context_limit - input_tokens - 128)
        if new_max >= self.max_tokens:
            return False  # already at or below the fitting budget
        self.max_tokens = new_max
        return True

    async def generate_response(
        self,
        state: EditProject,
        tools: list[ToolSchema],
        messages: list[dict],
    ) -> AgentResponse:
        """Generate tool calls using vLLM's OpenAI-compatible API."""
        # If tool_mode is "text", skip native tool calling entirely
        if self.tool_mode == "text":
            return await self._generate_response_without_tools(
                state, tools, messages
            )

        client = self._get_client()

        system_prompt = self._build_system_prompt(state)
        openai_tools = self._tools_to_openai_format(tools)

        extra_body = self._extra_body()
        async def _call(api_msgs: list[dict]):
            return await client.chat.completions.create(
                model=self.model,
                messages=api_msgs,
                tools=openai_tools,
                tool_choice="auto",
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                seed=self.seed,
                extra_body=extra_body,
            )

        api_messages = self._compose_messages(system_prompt, messages)

        # Note: Not all vLLM models support tool calling.
        # For models without native tool support, we fall back to
        # parsing tool calls from the text response.
        try:
            response = await _call(api_messages)
        except Exception as e:
            # If the model doesn't accept a separate system role (e.g. Gemma-2),
            # flip the cached flag and retry with the system prompt merged into
            # the first user message. The detection happens once per provider
            # instance; subsequent calls skip the probe.
            final_exc: Exception | None = e
            if (
                self._supports_system_role is None
                and self._is_system_role_unsupported_error(e)
            ):
                self._supports_system_role = False
                api_messages = self._compose_messages(system_prompt, messages)
                try:
                    response = await _call(api_messages)
                    final_exc = None
                except Exception as retry_e:
                    final_exc = retry_e
            # Shrink max_tokens iteratively on context-length overflow until
            # we either fit or can't shrink any further.
            for _ in range(4):
                if final_exc is None:
                    break
                if not self._shrink_max_tokens_for_context(final_exc):
                    break
                try:
                    response = await _call(api_messages)
                    final_exc = None
                except Exception as retry_e:
                    final_exc = retry_e
            if final_exc is not None:
                if self.tool_mode == "auto" and "tool" in str(final_exc).lower():
                    return await self._generate_response_without_tools(
                        state, tools, messages
                    )
                raise final_exc from None
        else:
            if self._supports_system_role is None:
                self._supports_system_role = True

        choice = response.choices[0]
        message = choice.message

        # Parse tool calls
        tool_calls = []
        if message.tool_calls:
            tool_calls = self._parse_tool_calls(message.tool_calls)

        # If no tool calls from native API, try text-based parsing
        if not tool_calls and message.content:
            tool_calls = self._parse_tool_calls_from_text(message.content)

        # If still no tool calls and auto mode, fallback to text-based prompt
        if not tool_calls and self.tool_mode == "auto":
            return await self._generate_response_without_tools(
                state, tools, messages
            )

        # Token usage
        usage = TokenUsage()
        if response.usage:
            usage.input_tokens = response.usage.prompt_tokens or 0
            usage.output_tokens = response.usage.completion_tokens or 0
            usage.total_tokens = response.usage.total_tokens or 0

        return AgentResponse(
            message=message.content or "",
            tool_calls=tool_calls if tool_calls else None,
            token_usage=usage,
        )

    async def _generate_response_without_tools(
        self,
        state: EditProject,
        tools: list[ToolSchema],
        messages: list[dict],
    ) -> AgentResponse:
        """
        Fallback for models without native tool support.

        Instructs the model to output tool calls in a specific JSON format
        that we can parse.
        """
        client = self._get_client()

        # Build tool descriptions for the prompt
        tool_descriptions = []
        for tool in tools:
            tool_descriptions.append(
                f"- {tool.name}: {tool.description}\n"
                f"  Parameters: {tool.parameters}"
            )
        tools_text = "\n".join(tool_descriptions)

        system_prompt = self._build_system_prompt(state)
        system_prompt += f"""

Available tools:
{tools_text}

To use a tool, respond with JSON in this exact format:
```json
{{"tool_calls": [{{"name": "tool_name", "arguments": {{"arg1": "value1"}}}}]}}
```

You may call multiple tools by adding more objects to the tool_calls array.
"""

        api_messages = self._compose_messages(system_prompt, messages)

        extra_body = self._extra_body()
        async def _call(api_msgs: list[dict]):
            return await client.chat.completions.create(
                model=self.model,
                messages=api_msgs,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                seed=self.seed,
                extra_body=extra_body,
            )

        try:
            response = await _call(api_messages)
        except Exception as e:
            final_exc: Exception | None = e
            if (
                self._supports_system_role is None
                and self._is_system_role_unsupported_error(e)
            ):
                self._supports_system_role = False
                api_messages = self._compose_messages(system_prompt, messages)
                try:
                    response = await _call(api_messages)
                    final_exc = None
                except Exception as retry_e:
                    final_exc = retry_e
            for _ in range(4):
                if final_exc is None:
                    break
                if not self._shrink_max_tokens_for_context(final_exc):
                    break
                try:
                    response = await _call(api_messages)
                    final_exc = None
                except Exception as retry_e:
                    final_exc = retry_e
            if final_exc is not None:
                raise final_exc from None
        else:
            if self._supports_system_role is None:
                self._supports_system_role = True

        choice = response.choices[0]
        content = choice.message.content or ""

        # Parse tool calls from text
        tool_calls = self._parse_tool_calls_from_text(content)

        # Token usage
        usage = TokenUsage()
        if response.usage:
            usage.input_tokens = response.usage.prompt_tokens or 0
            usage.output_tokens = response.usage.completion_tokens or 0
            usage.total_tokens = response.usage.total_tokens or 0

        return AgentResponse(
            message=content,
            tool_calls=tool_calls if tool_calls else None,
            token_usage=usage,
        )

    def _parse_tool_calls_from_text(self, text: str) -> list:
        """Parse tool calls from text response."""
        import json
        import re
        from nlebench.protocols import ToolCall

        tool_calls = []

        # Look for JSON code block
        json_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
        if json_match:
            json_str = json_match.group(1).strip()
        else:
            # Try to find raw JSON
            json_match = re.search(r'\{"tool_calls":\s*\[[\s\S]*?\]\}', text)
            if json_match:
                json_str = json_match.group(0)
            else:
                return []

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError:
            return []

        # Accept only two well-formed shapes:
        #   {"tool_calls": [{"name": ..., "arguments": ...}, ...]}  — wrapped form
        #   [{"name": ..., "arguments": ...}, ...]                   — bare list
        # A single bare dict is NOT accepted because it triggers too many
        # false positives (models sometimes emit JSON where a plain string
        # field happens to be called "name"). A genuine single tool call
        # can always be expressed as a one-element list.
        if isinstance(data, dict) and isinstance(data.get("tool_calls"), list):
            raw_calls = data["tool_calls"]
        elif isinstance(data, list):
            raw_calls = data
        else:
            return []

        # Every element must look like a tool call (dict with "name" key).
        # If any element fails this, reject the whole batch — a mixed parse
        # is almost certainly the model emitting non-tool JSON.
        if not all(isinstance(tc, dict) and "name" in tc for tc in raw_calls):
            return []

        for tc in raw_calls:
            tool_calls.append(ToolCall(
                name=tc.get("name", ""),
                arguments=tc.get("arguments", tc.get("parameters", {})),
                id=tc.get("id", ""),
            ))

        return tool_calls

    async def generate_state(
        self,
        initial_state: EditProject,
        messages: list[dict],
    ) -> AgentResponse:
        """Generate final state using vLLM's OpenAI-compatible API (Open Track)."""
        client = self._get_client()

        system_prompt = self._build_system_prompt(initial_state)
        api_messages = self._compose_messages(system_prompt, messages)

        extra_body = self._extra_body()
        async def _call(api_msgs: list[dict]):
            return await client.chat.completions.create(
                model=self.model,
                messages=api_msgs,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                seed=self.seed,
                extra_body=extra_body,
            )

        try:
            response = await _call(api_messages)
        except Exception as e:
            final_exc: Exception | None = e
            if (
                self._supports_system_role is None
                and self._is_system_role_unsupported_error(e)
            ):
                self._supports_system_role = False
                api_messages = self._compose_messages(system_prompt, messages)
                try:
                    response = await _call(api_messages)
                    final_exc = None
                except Exception as retry_e:
                    final_exc = retry_e
            for _ in range(4):
                if final_exc is None:
                    break
                if not self._shrink_max_tokens_for_context(final_exc):
                    break
                try:
                    response = await _call(api_messages)
                    final_exc = None
                except Exception as retry_e:
                    final_exc = retry_e
            if final_exc is not None:
                raise final_exc from None
        else:
            if self._supports_system_role is None:
                self._supports_system_role = True

        choice = response.choices[0]
        content = choice.message.content or ""

        # Parse final state from response
        final_state = self._parse_final_state(content)

        # Token usage
        usage = TokenUsage()
        if response.usage:
            usage.input_tokens = response.usage.prompt_tokens or 0
            usage.output_tokens = response.usage.completion_tokens or 0
            usage.total_tokens = response.usage.total_tokens or 0

        return AgentResponse(
            message=content,
            final_state=final_state,
            token_usage=usage,
        )
