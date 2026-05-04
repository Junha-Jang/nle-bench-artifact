"""
NLEBench Runner

Scenario execution and validation.

Supports two benchmark tracks:
- Canonical Track: Agent makes tool calls using 25 canonical tools
- Open Track: Agent directly produces final EditProject state
"""

# Lazy imports for performance.


def __getattr__(name):
    if name == "NLEBenchRunner":
        from nlebench.runner.executor import NLEBenchRunner
        return NLEBenchRunner
    if name == "ConstraintValidator":
        from nlebench.runner.validator import ConstraintValidator
        return ConstraintValidator
    if name == "TrackRunner":
        from nlebench.runner.track_runner import TrackRunner
        return TrackRunner
    if name == "run_with_track":
        from nlebench.runner.track_runner import run_with_track
        return run_with_track
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "NLEBenchRunner",
    "ConstraintValidator",
    "TrackRunner",
    "run_with_track",
]
