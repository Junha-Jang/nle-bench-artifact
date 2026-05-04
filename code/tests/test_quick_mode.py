"""Tests for Quick mode stratified sampling."""

import pytest

from nlebench.models import Scenario
from nlebench.runner.executor import NLEBenchRunner


def _make_scenario(id: str, level: str, feasibility: str = "feasible") -> Scenario:
    """Helper to create a minimal Scenario."""
    return Scenario(
        id=id,
        name=id,
        level=level,
        category="test",
        description="test",
        fixture="basic_sequence",
        user_messages=["test"],
        feasibility=feasibility,
    )


class TestStratifiedSample:
    """Test _stratified_sample picks from every group."""

    def _build_scenarios(self) -> list[Scenario]:
        """Build a realistic 120-scenario list."""
        scenarios = []
        # L1: 40 feasible
        for i in range(40):
            scenarios.append(_make_scenario(f"L1_{i:03d}", "L1"))
        # L2: 25 feasible
        for i in range(25):
            scenarios.append(_make_scenario(f"L2_{i:03d}", "L2"))
        # L3: 15 feasible
        for i in range(15):
            scenarios.append(_make_scenario(f"L3_{i:03d}", "L3"))
        # L4: 10 feasible
        for i in range(10):
            scenarios.append(_make_scenario(f"L4_{i:03d}", "L4"))
        # 15 infeasible
        for i in range(15):
            scenarios.append(_make_scenario(f"inf_{i:03d}", "L1", "infeasible"))
        # 15 ambiguous
        for i in range(15):
            scenarios.append(_make_scenario(f"amb_{i:03d}", "L1", "ambiguous"))
        return scenarios

    def test_returns_exact_count(self):
        scenarios = self._build_scenarios()
        sampled = NLEBenchRunner._stratified_sample(scenarios, 10)
        assert len(sampled) == 10

    def test_all_groups_represented(self):
        scenarios = self._build_scenarios()
        sampled = NLEBenchRunner._stratified_sample(scenarios, 10)

        levels = {s.level for s in sampled}
        feasibilities = {s.feasibility for s in sampled}

        # Every feasibility type must appear
        assert "feasible" in feasibilities
        assert "infeasible" in feasibilities
        assert "ambiguous" in feasibilities

    def test_all_levels_represented(self):
        scenarios = self._build_scenarios()
        sampled = NLEBenchRunner._stratified_sample(scenarios, 10)

        groups = {(s.level, s.feasibility) for s in sampled}
        # L1 feasible, L2 feasible, L3 feasible, L4 feasible should all appear
        assert ("L1", "feasible") in groups
        assert ("L2", "feasible") in groups
        assert ("L3", "feasible") in groups
        assert ("L4", "feasible") in groups

    def test_larger_groups_get_more(self):
        scenarios = self._build_scenarios()
        sampled = NLEBenchRunner._stratified_sample(scenarios, 20)

        l1_count = sum(1 for s in sampled if s.level == "L1" and s.feasibility == "feasible")
        l4_count = sum(1 for s in sampled if s.level == "L4" and s.feasibility == "feasible")

        # L1 has 40 scenarios, L4 has 10 — L1 should get more samples
        assert l1_count > l4_count

    def test_count_exceeds_total_returns_all(self):
        scenarios = self._build_scenarios()
        sampled = NLEBenchRunner._stratified_sample(scenarios, 200)
        assert len(sampled) == 120

    def test_no_duplicates(self):
        scenarios = self._build_scenarios()
        sampled = NLEBenchRunner._stratified_sample(scenarios, 10)
        ids = [s.id for s in sampled]
        assert len(ids) == len(set(ids))

    def test_small_count_still_covers_groups(self):
        """Even with count=6 (exactly 6 groups), each group gets 1."""
        scenarios = self._build_scenarios()
        sampled = NLEBenchRunner._stratified_sample(scenarios, 6)

        groups = {(s.level, s.feasibility) for s in sampled}
        assert len(groups) == 6
