"""
ClearML Experiment Tracking — Tag Vocabulary & Registration

This module enforces a closed tag vocabulary for NLE-Bench experiments on
ClearML. The goal is to keep the ClearML tag filter dropdown permanently
small and meaningful for reproducible benchmark runs.

Design:

- **Every run gets exactly 3 required tags**: dataset version, metrics
  version, intent. These are mirrored from code constants + CLI arg.

- **Optional status tag** (added retroactively on ClearML UI or via a
  separate retag script) marks runs that should not be trusted.

- **Any tag value outside the closed vocabulary is rejected** at registration
  time — prevents vocabulary drift from typos or ad-hoc additions.

- **Rich context** (model, provider, mode, seeds, scenario counts, dataset/
  metrics version again) goes into ClearML hyperparameters via `task.connect`,
  so filtering by numeric/free-text fields works without polluting tags.

- **One-off prose** (why this run matters, what's special) goes into
  `task.comment` via `--clearml-note`.
"""
from __future__ import annotations

from typing import Any, Optional


# =============================================================================
# Version constants — bump here when the dataset or metrics schema changes
# =============================================================================

DATASET_VERSION = "scenario-v3.1"   # matches dataset/scenarios_v3_1/
METRICS_VERSION = "metrics-v2"    # single-SR + BPM (2026-04-05 redesign)


# =============================================================================
# Closed tag vocabulary
# =============================================================================

# Intents — exactly one per run (the user picks via --clearml-intent).
INTENT_VALUES = frozenset({
    "pilot",        # exploratory
    "sanity",       # quick end-to-end pipeline check
    "debug",        # targeted bug reproduction/fix verification
    "regression",   # confirm prior results still hold after a change
    "ablation",     # isolate a single variable
    "paper",        # for publication / primary results table
})

# Datasets — grows when we cut a new scenario format.
DATASET_VALUES = frozenset({
    "dataset-scenario-v1",
    "dataset-scenario-v2",
    "dataset-scenario-v3",
    "dataset-scenario-v3.1",
})

# Metrics — grows when we cut a new validator/metric definition.
METRICS_VALUES = frozenset({
    "metrics-v1",
    "metrics-v2",
})

# Status — sparse, applied retroactively when a run should be distrusted.
# Normal healthy runs carry NO status tag.
STATUS_VALUES = frozenset({
    "status-stale",        # superseded by a better run
    "status-broken",       # known-invalid due to infra/code bug
    "status-superseded",   # replaced by a structurally different run
})

# Full closed vocabulary — nothing else is allowed as a tag.
ALLOWED_TAGS: frozenset[str] = (
    {f"intent-{v}" for v in INTENT_VALUES}
    | DATASET_VALUES
    | METRICS_VALUES
    | STATUS_VALUES
)


class TagVocabularyError(ValueError):
    """Raised when a tag outside the closed vocabulary is used."""


def validate_tags(tags: list[str]) -> None:
    """Reject any tag not in the closed vocabulary."""
    unknown = [t for t in tags if t not in ALLOWED_TAGS]
    if unknown:
        raise TagVocabularyError(
            f"Unknown tag value(s): {unknown}. "
            f"Allowed tags: {sorted(ALLOWED_TAGS)}"
        )


def build_run_tags(intent: str) -> list[str]:
    """
    Build the 3 required tags for a new run.

    Args:
        intent: One of INTENT_VALUES (pilot/sanity/debug/regression/ablation/paper)

    Returns:
        A 3-element list of tags, all guaranteed to be in ALLOWED_TAGS.
    """
    if intent not in INTENT_VALUES:
        raise TagVocabularyError(
            f"Unknown intent: {intent!r}. Allowed: {sorted(INTENT_VALUES)}"
        )
    tags = [
        f"dataset-{DATASET_VERSION}",
        METRICS_VERSION,
        f"intent-{intent}",
    ]
    validate_tags(tags)  # defence in depth
    return tags


def register_task(
    *,
    project_name: str,
    task_name: str,
    intent: str,
    note: Optional[str] = None,
    hyperparameters: Optional[dict[str, Any]] = None,
) -> Any:
    """
    Initialize a ClearML Task with enforced tag vocabulary + rich metadata.

    This is the ONLY way NLE-Bench code should create a ClearML task.
    Do not call `Task.init()` directly from experiment code.

    Args:
        project_name: ClearML project name (e.g., "nle-bench").
        task_name: Human-readable task name.
        intent: One of INTENT_VALUES.
        note: Optional free-text description (goes to `task.comment`).
        hyperparameters: Dict of filterable metadata (model, provider, mode,
                         n_scenarios, seeds, etc.). `dataset_version` and
                         `metrics_version` are auto-added.

    Returns:
        The initialized `clearml.Task` instance. Caller can use it for
        scalar/plot/table reporting. Tags must NOT be mutated from outside.

    Raises:
        TagVocabularyError: If `intent` is not a recognized value.
        ImportError: If `clearml` is not installed.
    """
    from clearml import Task

    tags = build_run_tags(intent)

    task = Task.init(
        project_name=project_name,
        task_name=task_name,
    )
    task.set_tags(tags)

    if note:
        task.comment = note

    # Always connect version info as hyperparameters (mirror of tags, for
    # numeric/filterable access) plus any caller-supplied metadata.
    params: dict[str, Any] = {
        "dataset_version": DATASET_VERSION,
        "metrics_version": METRICS_VERSION,
        "intent": intent,
    }
    if hyperparameters:
        params.update(hyperparameters)
    task.connect(params)

    return task


__all__ = [
    "DATASET_VERSION",
    "METRICS_VERSION",
    "INTENT_VALUES",
    "DATASET_VALUES",
    "METRICS_VALUES",
    "STATUS_VALUES",
    "ALLOWED_TAGS",
    "TagVocabularyError",
    "validate_tags",
    "build_run_tags",
    "register_task",
]
