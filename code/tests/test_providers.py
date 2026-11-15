"""Tests for LLM provider system."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from nlebench.providers import get_provider
from nlebench.providers.base import (
    BaseProvider,
    CanonicalProvider,
    OpenProvider,
    TokenUsage,
)
from nlebench.providers.openai_provider import OpenAIProvider
from nlebench.providers.anthropic_provider import AnthropicProvider
from nlebench.providers.vllm_provider import VLLMProvider
from nlebench.protocols import ToolSchema, AgentResponse


class TestGetProvider:
    def test_get_openai_provider(self):
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
            provider = get_provider("openai", model="gpt-4o")
            assert isinstance(provider, OpenAIProvider)
            assert provider.model == "gpt-4o"
            assert provider.provider_name == "openai"

    def test_get_anthropic_provider(self):
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            provider = get_provider("anthropic", model="claude-sonnet-4-6-2026-02-17")
            assert isinstance(provider, AnthropicProvider)
            assert provider.model == "claude-sonnet-4-6-2026-02-17"
            assert provider.provider_name == "anthropic"

    def test_get_vllm_provider(self):
        provider = get_provider(
            "vllm",
            model="Qwen/Qwen3-32B",
            base_url="http://localhost:8000/v1",
        )
        assert isinstance(provider, VLLMProvider)
        assert provider.model == "Qwen/Qwen3-32B"
        assert provider.provider_name == "vllm"
        assert provider.base_url == "http://localhost:8000/v1"

    def test_get_unknown_provider(self):
        with pytest.raises(ValueError) as excinfo:
            get_provider("unknown", model="model")
        assert "Unknown provider" in str(excinfo.value)

    def test_case_insensitive(self):
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
            provider = get_provider("OpenAI", model="gpt-4o")
            assert isinstance(provider, OpenAIProvider)


class TestTokenUsage:
    def test_token_usage_creation(self):
        usage = TokenUsage(input_tokens=100, output_tokens=50, total_tokens=150)
        assert usage.input_tokens == 100
        assert usage.output_tokens == 50
        assert usage.total_tokens == 150

    def test_token_usage_defaults(self):
        usage = TokenUsage()
        assert usage.input_tokens == 0
        assert usage.output_tokens == 0
        assert usage.total_tokens == 0


class TestOpenAIProvider:
    def test_initialization(self):
        provider = OpenAIProvider(
            model="gpt-4o",
            temperature=0.5,
            max_tokens=2048,
            api_key="test-key",
        )
        assert provider.model == "gpt-4o"
        assert provider.temperature == 0.5
        assert provider.max_tokens == 2048
        assert provider.provider_name == "openai"

    def test_is_canonical_provider(self):
        provider = OpenAIProvider(model="gpt-4o", api_key="test-key")
        assert isinstance(provider, CanonicalProvider)

    def test_is_open_provider(self):
        provider = OpenAIProvider(model="gpt-4o", api_key="test-key")
        assert isinstance(provider, OpenProvider)

    def test_tools_to_openai_format(self):
        provider = OpenAIProvider(model="gpt-4o", api_key="test-key")
        tools = [
            ToolSchema(
                name="test_tool",
                description="A test tool",
                parameters={"type": "object", "properties": {}},
            )
        ]
        openai_tools = provider._tools_to_openai_format(tools)
        assert len(openai_tools) == 1
        assert openai_tools[0]["type"] == "function"
        assert openai_tools[0]["function"]["name"] == "test_tool"


class TestAnthropicProvider:
    def test_initialization(self):
        provider = AnthropicProvider(
            model="claude-sonnet-4-6-2026-02-17",
            temperature=0.0,
            max_tokens=4096,
            api_key="test-key",
        )
        assert provider.model == "claude-sonnet-4-6-2026-02-17"
        assert provider.temperature == 0.0
        assert provider.provider_name == "anthropic"

    def test_is_canonical_provider(self):
        provider = AnthropicProvider(model="claude-sonnet-4-6-2026-02-17", api_key="test-key")
        assert isinstance(provider, CanonicalProvider)

    def test_is_open_provider(self):
        provider = AnthropicProvider(model="claude-sonnet-4-6-2026-02-17", api_key="test-key")
        assert isinstance(provider, OpenProvider)

    def test_tools_to_anthropic_format(self):
        provider = AnthropicProvider(model="claude-sonnet-4-6-2026-02-17", api_key="test-key")
        tools = [
            ToolSchema(
                name="test_tool",
                description="A test tool",
                parameters={"type": "object", "properties": {"arg1": {"type": "string"}}},
            )
        ]
        anthropic_tools = provider._tools_to_anthropic_format(tools)
        assert len(anthropic_tools) == 1
        assert anthropic_tools[0]["name"] == "test_tool"
        assert anthropic_tools[0]["description"] == "A test tool"
        assert anthropic_tools[0]["input_schema"]["type"] == "object"


class TestVLLMProvider:
    def test_initialization(self):
        provider = VLLMProvider(
            model="Qwen/Qwen3-32B",
            base_url="http://localhost:8000/v1",
        )
        assert provider.model == "Qwen/Qwen3-32B"
        assert provider.base_url == "http://localhost:8000/v1"
        assert provider.provider_name == "vllm"

    def test_default_base_url(self):
        with patch.dict("os.environ", {}, clear=True):
            provider = VLLMProvider(model="test-model")
            assert provider.base_url == "http://localhost:8000/v1"

    def test_env_base_url(self):
        with patch.dict("os.environ", {"VLLM_BASE_URL": "http://custom:9000/v1"}):
            provider = VLLMProvider(model="test-model")
            assert provider.base_url == "http://custom:9000/v1"

    def test_explicit_base_url_overrides_env(self):
        with patch.dict("os.environ", {"VLLM_BASE_URL": "http://env:9000/v1"}):
            provider = VLLMProvider(
                model="test-model",
                base_url="http://explicit:8000/v1",
            )
            assert provider.base_url == "http://explicit:8000/v1"

    def test_is_canonical_provider(self):
        provider = VLLMProvider(model="test-model")
        assert isinstance(provider, CanonicalProvider)

    def test_is_open_provider(self):
        provider = VLLMProvider(model="test-model")
        assert isinstance(provider, OpenProvider)

    def test_parse_tool_calls_from_text(self):
        provider = VLLMProvider(model="test-model")
        text = """Here is my response:
```json
{"tool_calls": [{"name": "update_clip", "arguments": {"clip_id": "c1", "start": 5.0}}]}
```
"""
        tool_calls = provider._parse_tool_calls_from_text(text)
        assert len(tool_calls) == 1
        assert tool_calls[0].name == "update_clip"
        assert tool_calls[0].arguments == {"clip_id": "c1", "start": 5.0}

    def test_parse_tool_calls_from_text_no_json(self):
        provider = VLLMProvider(model="test-model")
        text = "Just some text without JSON"
        tool_calls = provider._parse_tool_calls_from_text(text)
        assert len(tool_calls) == 0


class TestBaseProviderMethods:
    def test_build_system_prompt(self):
        provider = OpenAIProvider(model="gpt-4o", api_key="test-key")

        from nlebench.models import EditProject, Bin
        state = EditProject(
            schema_version="4.3",
            title="Test",
            bin=Bin(id="bin_1", name="Root"),
            media=[],
            timelines=[],
        )

        prompt = provider._build_system_prompt(state)
        assert "video editing assistant" in prompt.lower()
        assert "EditProject" in prompt
        assert "Test" in prompt  # Title should be in state JSON

    def test_parse_tool_calls_openai_format(self):
        provider = OpenAIProvider(model="gpt-4o", api_key="test-key")

        # Mock OpenAI tool call format
        mock_tc = MagicMock()
        mock_tc.function.name = "update_clip"
        mock_tc.function.arguments = '{"clip_id": "c1", "start": 5.0}'
        mock_tc.id = "call_123"

        tool_calls = provider._parse_tool_calls([mock_tc])
        assert len(tool_calls) == 1
        assert tool_calls[0].name == "update_clip"
        assert tool_calls[0].arguments == {"clip_id": "c1", "start": 5.0}
        assert tool_calls[0].id == "call_123"

    def test_parse_final_state(self):
        provider = OpenAIProvider(model="gpt-4o", api_key="test-key")

        # First read a fixture to have a valid state to parse
        from nlebench.models import EditProject, Bin
        state = EditProject(
            schema_version="4.3",
            title="Modified",
            bin=Bin(id="bin_1", name="Root"),
            media=[],
            timelines=[],
        )
        state_json = '{"schema_version": "4.3", "title": "Modified", "bin": {"id": "bin_1", "name": "Root", "media_ids": [], "timeline_ids": [], "bins": []}, "media": [], "timelines": []}'

        response_text = f"""Here is the modified state:
```json
{state_json}
```
"""
        parsed = provider._parse_final_state(response_text)
        assert parsed is not None
        assert parsed.title == "Modified"
        assert parsed.schema_version == "4.3"

    def test_parse_final_state_invalid_json(self):
        provider = OpenAIProvider(model="gpt-4o", api_key="test-key")

        response_text = "This is not JSON"
        parsed = provider._parse_final_state(response_text)
        assert parsed is None


class TestConfigIntegration:
    def test_config_supports_vllm(self):
        from nlebench.config import LLMConfig

        config = LLMConfig(
            provider="vllm",
            model="Qwen/Qwen3-32B",
            base_url="http://localhost:8000/v1",
        )
        assert config.provider == "vllm"
        assert config.base_url == "http://localhost:8000/v1"

    def test_config_from_yaml_with_vllm(self, tmp_path):
        from nlebench.config import NLEBenchConfig

        config_yaml = """
llm:
  provider: vllm
  model: Qwen/Qwen3-32B
  base_url: http://localhost:8000/v1
  temperature: 0.0
  max_tokens: 4096
"""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(config_yaml)

        config = NLEBenchConfig.from_yaml(config_file)
        assert config.llm.provider == "vllm"
        assert config.llm.model == "Qwen/Qwen3-32B"
        assert config.llm.base_url == "http://localhost:8000/v1"

    def test_vllm_model_pricing(self):
        from nlebench.config import MODEL_PRICING

        # Local models should have 0.0 pricing
        assert "Qwen/Qwen3-32B" in MODEL_PRICING
        assert MODEL_PRICING["Qwen/Qwen3-32B"] == (0.0, 0.0)
