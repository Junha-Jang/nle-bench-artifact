"""
NLEBench Contamination Defense

Three-layer contamination defense:
1. Temporal: Scenarios created after model training cutoff
2. Structural: Dynamic fixture perturbation (randomize entity IDs/names)
3. Detection: Canary strings embedded in scenarios

Canary strings are unique identifiers that can be used to detect
if NLE-Bench scenarios have leaked into model training data.
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

import yaml

logger = logging.getLogger(__name__)

# Canary prefix for NLE-Bench
CANARY_PREFIX = "nlebench-canary"
CANARY_VERSION = "v1"


def generate_canary(scenario_id: str, seed: str = "") -> str:
    """
    Generate a unique canary string for a scenario.

    Format: nlebench-canary-v1-{hash}

    The hash is derived from scenario_id + seed + timestamp,
    making each canary unique and traceable.

    Args:
        scenario_id: Scenario identifier
        seed: Optional additional seed (e.g., dataset version)

    Returns:
        Canary string
    """
    raw = f"{scenario_id}:{seed}:{uuid.uuid4().hex[:8]}"
    hash_val = hashlib.sha256(raw.encode()).hexdigest()[:16]
    return f"{CANARY_PREFIX}-{CANARY_VERSION}-{hash_val}"


def inject_canary_into_scenario(
    scenario_data: dict,
    canary: Optional[str] = None,
) -> dict:
    """
    Inject a canary string into a scenario YAML dict.

    Adds the canary as a metadata field that gets embedded in
    the scenario description (invisible to the task but detectable).

    Args:
        scenario_data: Scenario dict (as loaded from YAML)
        canary: Optional pre-generated canary. If None, generates one.

    Returns:
        Modified scenario dict with canary
    """
    sid = scenario_data.get("id", "unknown")

    if canary is None:
        canary = generate_canary(sid)

    scenario_data["canary_string"] = canary
    return scenario_data


def check_contamination(
    model_response: str,
    canary_strings: list[str],
) -> list[str]:
    """
    Check if a model response contains any canary strings.

    If a model reproduces a canary string, it's strong evidence
    that NLE-Bench data was in its training set.

    Args:
        model_response: The model's text response
        canary_strings: List of canary strings to check

    Returns:
        List of detected canary strings (empty = clean)
    """
    detected = []
    response_lower = model_response.lower()

    for canary in canary_strings:
        if canary.lower() in response_lower:
            detected.append(canary)

    return detected


def collect_canaries(scenarios_dir: Path) -> dict[str, str]:
    """
    Collect all canary strings from scenario YAML files.

    Args:
        scenarios_dir: Root directory containing scenario subdirectories

    Returns:
        Dict mapping scenario_id -> canary_string
    """
    canaries: dict[str, str] = {}

    for subdir_name in ["L1", "L2", "L3", "L4", "L4a", "L4b", "infeasible", "ambiguous"]:
        subdir = scenarios_dir / subdir_name
        if not subdir.exists():
            continue

        for yaml_file in sorted(subdir.glob("*.yaml")):
            try:
                with open(yaml_file, encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                sid = data.get("id", yaml_file.stem)
                canary = data.get("canary_string")
                if canary:
                    canaries[sid] = canary
            except Exception as e:
                logger.warning(f"Failed to read canary from {yaml_file}: {e}")

    return canaries


def generate_contamination_report(
    results: list[tuple[str, str, list[str]]],
) -> str:
    """
    Generate a contamination detection report.

    Args:
        results: List of (scenario_id, model_name, detected_canaries)

    Returns:
        Formatted report string
    """
    contaminated = [(sid, model, canaries) for sid, model, canaries in results if canaries]

    lines = [
        "Contamination Detection Report",
        "=" * 50,
        f"Total checks: {len(results)}",
        f"Contamination detected: {len(contaminated)}",
        "",
    ]

    if contaminated:
        lines.append("ALERT: Potential contamination detected!")
        lines.append("")
        for sid, model, canaries in contaminated:
            lines.append(f"  Scenario: {sid}")
            lines.append(f"  Model: {model}")
            lines.append(f"  Canaries: {', '.join(canaries)}")
            lines.append("")
    else:
        lines.append("No contamination detected.")

    return "\n".join(lines)
