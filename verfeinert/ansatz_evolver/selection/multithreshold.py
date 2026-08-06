"""Multi-threshold selection convenience policy."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any, Literal

from .fitness import SelectionResult
from .thresholds import ThresholdRule, select_by_thresholds


def select_multithreshold(
    analysis_results: Iterable[Mapping[str, Any]],
    *,
    thresholds: Mapping[str, float],
    policy_id: str = "multithreshold",
    direction: Literal["at_most", "at_least"] = "at_most",
    mode: Literal["all", "any"] = "all",
) -> SelectionResult:
    """Select candidates using the same direction for several thresholds."""
    rules = tuple(
        ThresholdRule(name=name, threshold=threshold, direction=direction)
        for name, threshold in sorted(thresholds.items())
    )
    return select_by_thresholds(
        analysis_results,
        rules=rules,
        policy_id=policy_id,
        mode=mode,
    )


__all__ = ["select_multithreshold"]
