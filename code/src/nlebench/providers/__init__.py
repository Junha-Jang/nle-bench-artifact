"""
NLE-Bench LLM Providers

Provides unified interface for different LLM backends:
- OpenAI (GPT-5.x, o-series, GPT-4.x, etc.)
- Anthropic (Claude)
- Google (Gemini)
- vLLM (OpenAI-compatible local models)
"""

import os

from nlebench.providers.base import (
    BaseProvider,
    CanonicalProvider,
    OpenProvider,
)
from nlebench.providers.openai_provider import OpenAIProvider
from nlebench.providers.anthropic_provider import AnthropicProvider
from nlebench.providers.google_provider import GoogleProvider
from nlebench.providers.vllm_provider import VLLMProvider


def get_provider(
    provider_name: str,
    model: str,
    temperature: float = 0.0,
    max_tokens: int = 4096,
    base_url: str | None = None,
    api_key: str | None = None,
    tool_mode: str = "auto",
    reasoning_effort: str | None = None,
) -> BaseProvider:
    """
    Get a provider instance by name.

    Args:
        provider_name: "openai", "anthropic", "google", or "vllm"
        model: Model identifier (e.g., "gpt-5.4", "claude-sonnet-4-6-2026-02-17", "Qwen/Qwen3-32B")
        temperature: Sampling temperature
        max_tokens: Max tokens for response
        base_url: Base URL for API (required for vLLM, optional for others)
        api_key: API key (uses env var if not provided)
        tool_mode: Tool calling mode for vLLM ("native", "text", "auto")
        reasoning_effort: OpenAI reasoning effort. Falls back to
            OPENAI_REASONING_EFFORT when omitted.

    Returns:
        Provider instance

    Raises:
        ValueError: If provider_name is not recognized
    """
    provider_name = provider_name.lower()

    if provider_name == "openai":
        effective_reasoning_effort = reasoning_effort or os.environ.get("OPENAI_REASONING_EFFORT")
        return OpenAIProvider(
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            base_url=base_url,
            api_key=api_key,
            reasoning_effort=effective_reasoning_effort,
        )
    elif provider_name == "anthropic":
        return AnthropicProvider(
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            api_key=api_key,
        )
    elif provider_name in ("google", "gemini"):
        return GoogleProvider(
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            api_key=api_key,
        )
    elif provider_name == "vllm":
        return VLLMProvider(
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            base_url=base_url,
            api_key=api_key,
            tool_mode=tool_mode,
        )
    else:
        raise ValueError(
            f"Unknown provider: {provider_name}. "
            f"Supported providers: openai, anthropic, google, vllm"
        )


__all__ = [
    "BaseProvider",
    "CanonicalProvider",
    "OpenProvider",
    "OpenAIProvider",
    "AnthropicProvider",
    "GoogleProvider",
    "VLLMProvider",
    "get_provider",
]
