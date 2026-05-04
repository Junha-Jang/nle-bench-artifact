"""
NLEBench Configuration

Configuration management for NLEBench experiments.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Optional

import yaml

# Pricing per 1M tokens (input, output) — updated 2026-02
MODEL_PRICING: dict[str, tuple[float, float]] = {
    # OpenAI
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1-nano": (0.10, 0.40),
    "gpt-4.1": (2.00, 8.00),
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4.5-preview": (75.00, 150.00),
    "o3-mini": (1.10, 4.40),
    # Anthropic
    "claude-opus-4-6": (15.00, 75.00),
    "claude-opus-4-5-20251101": (15.00, 75.00),
    "claude-sonnet-4-5-20250929": (3.00, 15.00),
    "claude-haiku-4-5-20251001": (0.80, 4.00),
    # xAI
    "grok-3": (3.00, 15.00),
    "grok-3-mini": (0.30, 0.50),
    # Local models (via vLLM) — cost is essentially free (hardware only)
    "Qwen/Qwen3-32B": (0.0, 0.0),
    "Qwen/QwQ-32B": (0.0, 0.0),
    "Qwen/Qwen2.5-72B-Instruct": (0.0, 0.0),
    "Qwen/Qwen2.5-32B-Instruct": (0.0, 0.0),
    "Qwen/Qwen2.5-14B-Instruct": (0.0, 0.0),
    "Qwen/Qwen2.5-7B-Instruct": (0.0, 0.0),
    "meta-llama/Llama-3.3-70B-Instruct": (0.0, 0.0),
    "meta-llama/Llama-3.1-70B-Instruct": (0.0, 0.0),
    "meta-llama/Llama-3.1-8B-Instruct": (0.0, 0.0),
    "mistralai/Mistral-Large-Instruct-2411": (0.0, 0.0),
    "deepseek-ai/DeepSeek-V3": (0.0, 0.0),
}


def _lookup_pricing(model: str) -> tuple[float, float]:
    """Look up pricing for a model. Falls back to exact match, then prefix match."""
    if model in MODEL_PRICING:
        return MODEL_PRICING[model]
    # Prefix match (e.g. "gpt-4o-2025-..." → "gpt-4o")
    for key in sorted(MODEL_PRICING.keys(), key=len, reverse=True):
        if model.startswith(key):
            return MODEL_PRICING[key]
    # Unknown model — return 0 so cost is not inflated
    return (0.0, 0.0)


@dataclass
class LLMConfig:
    """LLM provider configuration"""

    provider: Literal["anthropic", "openai", "google", "vllm"] = "anthropic"
    model: str = "claude-sonnet-4-6-2026-02-17"
    temperature: float = 0.0  # Deterministic output
    max_tokens: int = 4096
    base_url: Optional[str] = None  # Custom API base URL (required for vLLM)
    api_key: Optional[str] = None  # API key (uses env var if not set)
    reasoning_effort: Optional[str] = None  # OpenAI o-series/GPT-5.x only


@dataclass
class PremiereConfig:
    """Premiere Pro configuration"""

    version: str = "v25.6"


@dataclass
class OutputConfig:
    """Output configuration"""

    base_dir: Path = field(default_factory=lambda: Path("results"))
    format: Literal["json", "jsonl"] = "jsonl"
    save_states: bool = True  # Save initial/final EditState
    save_xml: bool = False  # Save generated XML


@dataclass
class NLEBenchConfig:
    """Main NLEBench configuration"""

    # Experiment settings
    runs_per_scenario: int = 3  # Number of runs per scenario
    random_seed: int = 42
    timeout_seconds: float = 60.0
    max_turns: int = 10

    # Filtering
    levels: list[str] = field(default_factory=lambda: ["L1", "L2", "L3", "L4", "L4a", "L4b"])
    categories: Optional[list[str]] = None  # None = all categories
    scenario_ids: Optional[list[str]] = None  # None = all scenarios
    feasibilities: Optional[list[str]] = None  # None = all (feasible, infeasible, ambiguous)

    # Quick mode (subset of scenarios)
    quick_mode: bool = False
    quick_scenario_count: int = 10

    # Sub-configs
    llm: LLMConfig = field(default_factory=LLMConfig)
    premiere: PremiereConfig = field(default_factory=PremiereConfig)
    output: OutputConfig = field(default_factory=OutputConfig)

    # Cost estimation (per 1M tokens) — auto-detected from model if not set
    cost_per_1m_input_tokens: float = 0.0
    cost_per_1m_output_tokens: float = 0.0

    def __post_init__(self):
        """Auto-detect pricing from model if not explicitly set."""
        if self.cost_per_1m_input_tokens == 0.0 and self.cost_per_1m_output_tokens == 0.0:
            inp, out = _lookup_pricing(self.llm.model)
            self.cost_per_1m_input_tokens = inp
            self.cost_per_1m_output_tokens = out

    @classmethod
    def from_yaml(cls, path: Path) -> "NLEBenchConfig":
        """Load configuration from YAML file"""
        with open(path) as f:
            data = yaml.safe_load(f)

        llm_data = data.get("llm", {})
        premiere_data = data.get("premiere", {})
        output_data = data.get("output", {})

        return cls(
            runs_per_scenario=data.get("runs_per_scenario", 3),
            random_seed=data.get("random_seed", 42),
            timeout_seconds=data.get("timeout_seconds", 60.0),
            max_turns=data.get("max_turns", 10),
            levels=data.get("levels", ["L1", "L2", "L3", "L4", "L4a", "L4b"]),
            categories=data.get("categories"),
            scenario_ids=data.get("scenario_ids"),
            feasibilities=data.get("feasibilities"),
            quick_mode=data.get("quick_mode", False),
            quick_scenario_count=data.get("quick_scenario_count", 10),
            llm=LLMConfig(
                provider=llm_data.get("provider", "anthropic"),
                model=llm_data.get("model", "claude-sonnet-4-6-2026-02-17"),
                temperature=llm_data.get("temperature", 0.0),
                max_tokens=llm_data.get("max_tokens", 4096),
                base_url=llm_data.get("base_url"),
                api_key=llm_data.get("api_key"),
                reasoning_effort=llm_data.get("reasoning_effort"),
            ),
            premiere=PremiereConfig(
                version=premiere_data.get("version", "v25.6"),
            ),
            output=OutputConfig(
                base_dir=Path(output_data.get("base_dir", "results")),
                format=output_data.get("format", "jsonl"),
                save_states=output_data.get("save_states", True),
                save_xml=output_data.get("save_xml", False),
            ),
            cost_per_1m_input_tokens=data.get("cost_per_1m_input_tokens", 0.0),
            cost_per_1m_output_tokens=data.get("cost_per_1m_output_tokens", 0.0),
        )

    def to_yaml(self, path: Path) -> None:
        """Save configuration to YAML file"""
        data = {
            "runs_per_scenario": self.runs_per_scenario,
            "random_seed": self.random_seed,
            "timeout_seconds": self.timeout_seconds,
            "max_turns": self.max_turns,
            "levels": self.levels,
            "categories": self.categories,
            "scenario_ids": self.scenario_ids,
            "feasibilities": self.feasibilities,
            "quick_mode": self.quick_mode,
            "quick_scenario_count": self.quick_scenario_count,
            "llm": {
                "provider": self.llm.provider,
                "model": self.llm.model,
                "temperature": self.llm.temperature,
                "max_tokens": self.llm.max_tokens,
                "base_url": self.llm.base_url,
                "api_key": self.llm.api_key,
                "reasoning_effort": self.llm.reasoning_effort,
            },
            "premiere": {
                "version": self.premiere.version,
            },
            "output": {
                "base_dir": str(self.output.base_dir),
                "format": self.output.format,
                "save_states": self.output.save_states,
                "save_xml": self.output.save_xml,
            },
            "cost_per_1m_input_tokens": self.cost_per_1m_input_tokens,
            "cost_per_1m_output_tokens": self.cost_per_1m_output_tokens,
        }

        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True)

    @classmethod
    def default(cls) -> "NLEBenchConfig":
        """Create default configuration"""
        return cls()

    @classmethod
    def quick(cls) -> "NLEBenchConfig":
        """Create quick mode configuration for development"""
        return cls(
            quick_mode=True,
            quick_scenario_count=10,
            runs_per_scenario=1,
        )


# Default config file path
DEFAULT_CONFIG_PATH = Path(__file__).parent / "config.yaml"
