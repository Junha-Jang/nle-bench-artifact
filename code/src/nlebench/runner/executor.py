"""
NLEBench Scenario Executor

Executes benchmark scenarios against EditProject-based agents.
"""

import asyncio
import copy
import gc
import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from nlebench.models import EditProject
from nlebench.config import NLEBenchConfig
from nlebench.protocols import EditAgent

# Type alias for agent factory
AgentFactory = Callable[[EditProject, "NLEBenchConfig"], EditAgent]
from nlebench.dataset.fixtures import get_fixture
from nlebench.models import (
    ExecutionResult,
    Level,
    Scenario,
    ValidationResult,
)
from nlebench.runner.validator import ConstraintValidator
from nlebench.runner.scenario_loader import load_scenarios as load_scenario_set
from nlebench.metrics.calibration import check_refusal, check_state_unchanged, check_clarification
from nlebench.runner.multi_turn import resolve_template, extract_variables, extract_created_id

logger = logging.getLogger(__name__)


# HTTP status codes that indicate transient errors worth retrying
_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 529}
_MAX_RETRIES = 3
_BASE_DELAY_SECONDS = 2.0  # 2s, 4s, 8s exponential backoff


def _is_retryable_error(exc: Exception) -> bool:
    """Check if an exception is a transient API error worth retrying."""
    exc_str = str(exc).lower()

    # Check for HTTP status codes in exception message
    for code in _RETRYABLE_STATUS_CODES:
        if str(code) in str(exc):
            return True

    # Common patterns from API client libraries
    if any(pattern in exc_str for pattern in [
        "rate limit",
        "rate_limit",
        "too many requests",
        "overloaded",
        "server error",
        "bad gateway",
        "service unavailable",
        "connection error",
        "connection reset",
    ]):
        return True

    # Check for status_code attribute (httpx, requests, etc.)
    if hasattr(exc, "status_code") and exc.status_code in _RETRYABLE_STATUS_CODES:
        return True

    # Anthropic SDK uses .status_code on APIStatusError
    if hasattr(exc, "response") and hasattr(exc.response, "status_code"):
        if exc.response.status_code in _RETRYABLE_STATUS_CODES:
            return True

    return False


class NLEBenchRunner:
    """
    Runs NLEBench scenarios against EditStateAgent.

    Supports:
    - Loading scenarios from YAML files
    - Executing scenarios with multiple runs
    - Collecting metrics (latency, token usage, cost)
    - Validating results against constraints
    """

    def __init__(
        self,
        config: NLEBenchConfig,
        agent_factory: Optional[AgentFactory] = None,
    ):
        self.config = config
        self.agent_factory = agent_factory
        self.validator = ConstraintValidator()
        self._results: list[ExecutionResult] = []
        self._scenarios: list[Scenario] = []
        self._output_dir: Optional[Path] = None

    def _prepare_output_dir(self) -> Path:
        """Create and return the output directory for this run."""
        if self._output_dir is not None:
            return self._output_dir
        model_slug = (
            self.config.llm.model.replace("/", "_").replace(":", "_")
            if self.config.llm.model
            else "unknown"
        )
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        self._output_dir = self.config.output.base_dir / f"{timestamp}_{model_slug}"
        self._output_dir.mkdir(parents=True, exist_ok=True)
        return self._output_dir

    @staticmethod
    async def _chat_with_retry(agent: EditAgent, message: str) -> object:
        """Call agent.chat() with exponential backoff on transient errors."""
        last_exc: Exception | None = None
        for attempt in range(_MAX_RETRIES + 1):
            try:
                return await agent.chat(message)
            except Exception as exc:
                last_exc = exc
                if attempt < _MAX_RETRIES and _is_retryable_error(exc):
                    delay = _BASE_DELAY_SECONDS * (2 ** attempt)  # 2, 4, 8
                    logger.warning(
                        f"Retryable error (attempt {attempt + 1}/{_MAX_RETRIES + 1}): "
                        f"{exc!r} — retrying in {delay:.0f}s"
                    )
                    await asyncio.sleep(delay)
                else:
                    raise
        raise last_exc  # Should not reach here, but satisfy type checker

    def load_scenarios(self, scenarios_dir: Optional[Path] = None) -> list[Scenario]:
        """
        Load scenarios from YAML files.

        Args:
            scenarios_dir: Directory containing scenario YAML files.
                          If None, uses default location.

        Returns:
            List of loaded Scenario objects
        """
        scenarios = load_scenario_set(
            scenarios_dir=scenarios_dir,
            levels=self.config.levels,
            categories=self.config.categories,
            scenario_ids=self.config.scenario_ids,
            feasibilities=self.config.feasibilities,
        )

        # Apply quick mode: stratified sampling across levels/feasibilities
        if self.config.quick_mode:
            scenarios = self._stratified_sample(
                scenarios, self.config.quick_scenario_count, seed=self.config.random_seed
            )

        self._scenarios = scenarios
        logger.info(f"Loaded {len(scenarios)} scenarios")
        return scenarios

    @staticmethod
    def _stratified_sample(
        scenarios: list[Scenario], count: int, seed: int = 42
    ) -> list[Scenario]:
        """Sample scenarios proportionally across levels and feasibilities.

        Groups scenarios by (level, feasibility) and picks from each group
        so that every group is represented in the sample.  Within each group
        scenarios are shuffled using *seed* so that the selection is
        deterministic yet not biased toward alphabetically-first items.
        """
        from collections import defaultdict
        import math
        import random

        if len(scenarios) <= count:
            return scenarios

        rng = random.Random(seed)

        # Group by (level, feasibility)
        groups: dict[tuple[str, str], list[Scenario]] = defaultdict(list)
        for s in scenarios:
            groups[(s.level, s.feasibility)].append(s)

        # Shuffle within each group (seed-deterministic)
        for group in groups.values():
            rng.shuffle(group)

        # Guarantee at least 1 per group, distribute remainder proportionally
        n_groups = len(groups)
        remaining = max(count - n_groups, 0)

        sampled: list[Scenario] = []
        for key, group in sorted(groups.items()):
            # Base: 1 per group
            base = 1
            # Extra: proportional to group size
            extra = math.floor(remaining * len(group) / len(scenarios))
            take = min(base + extra, len(group))
            sampled.extend(group[:take])

        # If still under target, fill from largest groups
        if len(sampled) < count:
            already = set(id(s) for s in sampled)
            for key, group in sorted(
                groups.items(), key=lambda kv: len(kv[1]), reverse=True
            ):
                for s in group:
                    if id(s) not in already:
                        sampled.append(s)
                        already.add(id(s))
                        if len(sampled) >= count:
                            break
                if len(sampled) >= count:
                    break

        # Trim if over
        return sampled[:count]

    # Number of consecutive identical errors before aborting
    _CONSECUTIVE_ERROR_ABORT_THRESHOLD = 3

    async def run_all(self) -> list[ExecutionResult]:
        """
        Run all loaded scenarios.

        Results are streamed to disk (JSONL) as they complete to minimise
        memory usage.  The in-memory ``_results`` list stores lightweight
        copies without state JSON payloads.

        Returns:
            List of ExecutionResult for all runs
        """
        if not self._scenarios:
            self.load_scenarios()

        results: list[ExecutionResult] = []
        total_runs = len(self._scenarios) * self.config.runs_per_scenario

        # Running stats for progress bar
        ok_count = 0
        fail_count = 0
        total_cost = 0.0

        # Early abort tracking
        consecutive_error_msg: str | None = None
        consecutive_error_count = 0

        try:
            from tqdm import tqdm
            pbar = tqdm(
                total=total_runs,
                desc=f"NLEBench ({self.config.llm.model})",
                bar_format=(
                    "{l_bar}{bar}| {n_fmt}/{total_fmt} "
                    "[{elapsed}<{remaining}, {rate_fmt}] "
                    "{postfix}"
                ),
                ncols=120,
            )
        except ImportError:
            pbar = None

        def _write(msg: str) -> None:
            """Write message without breaking tqdm progress bar."""
            if pbar is not None:
                pbar.write(msg)
            else:
                logger.error(msg)

        # Prepare streaming output file so results flush to disk immediately
        self._prepare_output_dir()
        results_file = self._output_dir / "results.jsonl"
        stream_f = open(results_file, "w", encoding="utf-8")

        aborted = False
        try:
            for scenario in self._scenarios:
                if aborted:
                    break
                for run_number in range(self.config.runs_per_scenario):
                    logger.info(
                        f"Running {scenario.id} (run {run_number + 1}/{self.config.runs_per_scenario})"
                    )

                    try:
                        result = await self.run_scenario(scenario, run_number)
                        # Reset consecutive error tracking on success
                        consecutive_error_msg = None
                        consecutive_error_count = 0
                    except Exception as e:
                        error_str = (
                            f"{type(e).__name__}: {e}" if str(e)
                            else type(e).__name__
                        )
                        _write(f"[FAIL] {scenario.id}: {error_str}")
                        # Create failed result
                        result = ExecutionResult(
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
                                error_message=error_str,
                            ),
                            error_message=error_str,
                        )

                        # Track consecutive identical errors
                        if error_str == consecutive_error_msg:
                            consecutive_error_count += 1
                        else:
                            consecutive_error_msg = error_str
                            consecutive_error_count = 1

                        if consecutive_error_count >= self._CONSECUTIVE_ERROR_ABORT_THRESHOLD:
                            _write(
                                f"\n[ABORT] {consecutive_error_count} consecutive identical errors. "
                                f"Likely a configuration issue:\n  {error_str}\n"
                            )
                            aborted = True
                            # Still record this last result before breaking
                            stream_f.write(json.dumps(result.to_dict(), ensure_ascii=False) + "\n")
                            stream_f.flush()
                            results.append(result)
                            break

                    # Stream result to disk immediately
                    stream_f.write(json.dumps(result.to_dict(), ensure_ascii=False) + "\n")
                    stream_f.flush()

                    # Keep lightweight copy in memory (drop heavy payloads
                    # that are already persisted to the JSONL stream).
                    result.initial_state_json = None
                    result.final_state_json = None
                    result.tool_calls = []
                    result.agent_response = ""
                    results.append(result)

                    # Update running stats
                    if result.success:
                        ok_count += 1
                    else:
                        fail_count += 1
                    total_cost += result.cost_usd

                    if pbar is not None:
                        done = ok_count + fail_count
                        tsr_pct = ok_count / done * 100 if done else 0
                        pbar.set_postfix_str(
                            f"{scenario.id}  "
                            f"TSR={tsr_pct:.0f}% ({ok_count}/{done})  "
                            f"${total_cost:.2f}"
                        )
                        pbar.update(1)

                    # Free memory from this iteration.
                    del result
                    gc.collect()

        finally:
            stream_f.close()

        if pbar is not None:
            pbar.close()

        self._results = results
        return results

    async def run_scenario(
        self,
        scenario: Scenario,
        run_number: int = 0,
    ) -> ExecutionResult:
        """
        Run a single scenario.

        Args:
            scenario: Scenario to run
            run_number: Run number (0-indexed)

        Returns:
            ExecutionResult with metrics and validation
        """
        started_at = datetime.now()

        # Load initial state from fixture (with optional perturbation)
        perturb = scenario.perturb_fixture
        perturb_seed = (getattr(self.config, 'random_seed', 0) + run_number) if perturb else 0
        initial_state = get_fixture(scenario.fixture, perturb=perturb, seed=perturb_seed)
        initial_state_json = json.dumps(initial_state.to_dict()) if self.config.output.save_states else None

        # Create a deep copy for agent manipulation
        agent_state = copy.deepcopy(initial_state)

        # Create agent via factory
        if self.agent_factory is None:
            raise RuntimeError(
                "No agent_factory provided. Pass an agent_factory to NLEBenchRunner "
                "that creates an EditAgent from (state, config)."
            )
        agent = self.agent_factory(agent_state, self.config)

        # Execute user messages
        total_latency_ms = 0.0
        total_input_tokens = 0
        total_output_tokens = 0
        all_tool_calls = []
        agent_response = ""
        multi_turn_context: dict[str, str] = {}

        per_turn_failures: list[str] = []

        try:
            # Build turn list: use Turn objects if available, else wrap user_messages
            if scenario.turns:
                turns = scenario.turns
            else:
                from nlebench.models import Turn
                turns = [Turn(user=msg) for msg in scenario.user_messages]

            for turn_idx, turn in enumerate(turns):
                # Snapshot state before this turn for per-turn validation
                previous_state = copy.deepcopy(agent.state)

                # Resolve multi-turn templates (e.g., {created_id})
                resolved_message = resolve_template(turn.user, multi_turn_context)
                if resolved_message == turn.user and turn.fallback:
                    # Template unresolved, use fallback
                    resolved_message = turn.fallback

                start_time = time.time()

                # Run with timeout (includes retry delays)
                response = await asyncio.wait_for(
                    self._chat_with_retry(agent, resolved_message),
                    timeout=scenario.timeout_seconds,
                )

                latency_ms = (time.time() - start_time) * 1000
                total_latency_ms += latency_ms

                # Collect metrics
                if hasattr(response, "token_usage") and response.token_usage:
                    total_input_tokens += response.token_usage.input_tokens
                    total_output_tokens += response.token_usage.output_tokens

                if hasattr(response, "tool_calls"):
                    all_tool_calls.extend(response.tool_calls or [])

                agent_response = response.message if hasattr(response, "message") else str(response)

                # Extract variables for multi-turn context
                extracted = extract_variables(turn.user, agent_response)
                multi_turn_context.update(extracted)

                # Extract via Turn.extract patterns
                if turn.extract:
                    import re
                    for var_name, pattern in turn.extract.items():
                        match = re.search(pattern, agent_response)
                        if match:
                            multi_turn_context[var_name] = match.group(1) if match.lastindex else match.group(0)

                # Per-turn constraint validation
                if turn.constraints_after_turn:
                    current_state = agent.state
                    failed = self.validator.validate_turn(
                        previous_state, current_state, turn.constraints_after_turn
                    )
                    for f in failed:
                        per_turn_failures.append(f"turn[{turn_idx}]:{f}")

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
                latency_ms=self.config.timeout_seconds * 1000,
                error_message=f"Timeout after {self.config.timeout_seconds}s",
                started_at=started_at,
                completed_at=datetime.now(),
            )
        except Exception as e:
            err_detail = f"{type(e).__name__}: {e}" if str(e) else type(e).__name__
            logger.error(f"Scenario {scenario.id} failed: {err_detail}")
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
                error_message=err_detail,
                started_at=started_at,
                completed_at=datetime.now(),
            )

        # Get final state
        final_state = agent.state
        final_state_json = json.dumps(final_state.to_dict()) if self.config.output.save_states else None

        # Validate constraints
        validation = self.validator.validate(
            initial_state,
            final_state,
            scenario,
        )

        # Merge per-turn constraint failures
        if per_turn_failures:
            validation.failed_constraints.extend(per_turn_failures)
            validation.tsr = False

        # Behavioral fields — populated for ALL scenarios (needed for BPM + unified SR)
        validation.feasibility = scenario.feasibility
        state_unchanged = check_state_unchanged(
            json.dumps(initial_state.to_dict()),
            json.dumps(final_state.to_dict()),
        )
        validation.state_changed = not state_unchanged
        refused = check_refusal(agent_response)
        asked = check_clarification(agent_response)
        validation.refusal_appropriate = refused
        validation.asked_clarification = asked

        # Classify behavior: execute / refuse / clarify / noop
        # Priority: if the model took tool actions → execute; else refuse > clarify > noop.
        if all_tool_calls:
            validation.behavior = "execute"
        elif refused:
            validation.behavior = "refuse"
        elif asked:
            validation.behavior = "clarify"
        else:
            validation.behavior = "noop"

        # Calculate cost
        cost_usd = self._calculate_cost(total_input_tokens, total_output_tokens)

        completed_at = datetime.now()

        return ExecutionResult(
            scenario_id=scenario.id,
            run_number=run_number,
            success=validation.passed,
            validation=validation,
            initial_state_json=initial_state_json,
            final_state_json=final_state_json,
            latency_ms=total_latency_ms,
            token_usage=total_input_tokens + total_output_tokens,
            input_tokens=total_input_tokens,
            output_tokens=total_output_tokens,
            cost_usd=cost_usd,
            tool_calls=[self._serialize_tool_call(tc) for tc in all_tool_calls],
            agent_response=agent_response,
            started_at=started_at,
            completed_at=completed_at,
        )

    def _calculate_cost(self, input_tokens: int, output_tokens: int) -> float:
        """Calculate cost in USD based on API-reported token usage."""
        input_cost = (input_tokens / 1_000_000) * self.config.cost_per_1m_input_tokens
        output_cost = (output_tokens / 1_000_000) * self.config.cost_per_1m_output_tokens
        return input_cost + output_cost

    def _serialize_tool_call(self, tool_call) -> dict:
        """Serialize tool call for JSON storage."""
        if hasattr(tool_call, "to_dict"):
            return tool_call.to_dict()
        if hasattr(tool_call, "__dict__"):
            return {
                k: v for k, v in tool_call.__dict__.items()
                if not k.startswith("_")
            }
        return {"raw": str(tool_call)}

    def save_results(self, output_dir: Optional[Path] = None) -> Path:
        """
        Save config and summary to output directory.

        results.jsonl is already written by ``run_all()`` via streaming,
        so this method only adds config.yaml and summary.json.

        Args:
            output_dir: Output directory. If None, uses the directory
                        created during run_all().

        Returns:
            Path to the results directory
        """
        if output_dir is None:
            output_dir = self._output_dir or self._prepare_output_dir()

        output_dir.mkdir(parents=True, exist_ok=True)

        # Save config
        self.config.to_yaml(output_dir / "config.yaml")

        # results.jsonl was already streamed during run_all().
        # If run_all() was NOT called (e.g. manual usage), write now.
        results_file = output_dir / "results.jsonl"
        if not results_file.exists():
            with open(results_file, "w", encoding="utf-8") as f:
                for result in self._results:
                    f.write(json.dumps(result.to_dict(), ensure_ascii=False) + "\n")

        # Save summary
        summary = self._generate_summary()
        summary_file = output_dir / "summary.json"
        with open(summary_file, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)

        logger.info(f"Results saved to {output_dir}")
        return output_dir

    def _generate_summary(self) -> dict:
        """Generate summary statistics."""
        if not self._results:
            return {"error": "No results"}

        total = len(self._results)
        successful = sum(1 for r in self._results if r.success)

        # Calculate metrics
        tsr = successful / total if total > 0 else 0.0
        csr = sum(1 for r in self._results if r.validation.csr) / total if total > 0 else 0.0
        avg_ovr = sum(r.validation.ovr for r in self._results) / total if total > 0 else 0.0

        latencies = [r.latency_ms for r in self._results if r.latency_ms > 0]
        p50 = sorted(latencies)[len(latencies) // 2] if latencies else 0.0
        p95 = sorted(latencies)[int(len(latencies) * 0.95)] if latencies else 0.0

        total_cost = sum(r.cost_usd for r in self._results)
        avg_cpr = total_cost / total if total > 0 else 0.0

        # By level breakdown
        tsr_by_level = {}
        for level in Level:
            level_results = [r for r in self._results if r.scenario_id.startswith(level.value)]
            if level_results:
                tsr_by_level[level.value] = sum(1 for r in level_results if r.success) / len(level_results)

        return {
            "model": self.config.llm.model,
            "provider": self.config.llm.provider,
            "total_runs": total,
            "successful_runs": successful,
            "metrics": {
                "tsr": round(tsr, 4),
                "csr": round(csr, 4),
                "ovr": round(avg_ovr, 4),
                "p50_latency_ms": round(p50, 2),
                "p95_latency_ms": round(p95, 2),
                "cpr": round(avg_cpr, 4),
            },
            "tsr_by_level": tsr_by_level,
            "total_cost_usd": round(total_cost, 4),
            "actual_billed_usd": None,
            "timestamp": datetime.now().isoformat(),
        }


async def run_benchmark(
    config: Optional[NLEBenchConfig] = None,
    agent_factory: Optional[AgentFactory] = None,
    scenarios_dir: Optional[Path] = None,
    output_dir: Optional[Path] = None,
) -> tuple[list[ExecutionResult], Path]:
    """
    Convenience function to run the full benchmark.

    Args:
        config: NLEBench configuration
        agent_factory: Factory to create EditAgent instances
        scenarios_dir: Directory containing scenarios
        output_dir: Output directory for results

    Returns:
        Tuple of (results, output_path)
    """
    if config is None:
        config = NLEBenchConfig.default()

    runner = NLEBenchRunner(config, agent_factory=agent_factory)
    runner.load_scenarios(scenarios_dir)
    results = await runner.run_all()
    output_path = runner.save_results(output_dir)

    return results, output_path
