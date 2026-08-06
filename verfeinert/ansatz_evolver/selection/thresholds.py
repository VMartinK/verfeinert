"""Threshold-based selection over AnalysisResult JSON."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

from ..models import require_identifier
from ..validation import validate_analysis_result_document
from .fitness import SelectionResult, _selection_from_results, metric_value


ThresholdDirection = Literal["at_most", "at_least"]


@dataclass(frozen=True)
class ThresholdRule:
    """One numeric threshold rule."""

    name: str
    threshold: float
    direction: ThresholdDirection = "at_most"
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("name must be a non-empty string.")
        object.__setattr__(self, "name", self.name.strip())
        if type(self.threshold) not in {int, float}:
            raise ValueError("threshold must be numeric.")
        object.__setattr__(self, "threshold", float(self.threshold))
        if self.direction not in {"at_most", "at_least"}:
            raise ValueError("direction must be at_most or at_least.")

    def passes(self, result: Mapping[str, Any]) -> bool:
        """Return whether a result passes this threshold."""
        value = metric_value(result, self.name)
        if value is None:
            return False
        if self.direction == "at_most":
            return value <= self.threshold
        return value >= self.threshold

    def to_dict(self) -> dict[str, Any]:
        """Return JSON-safe rule data."""
        return {
            "name": self.name,
            "threshold": self.threshold,
            "direction": self.direction,
            "metadata": dict(self.metadata),
        }


def select_by_thresholds(
    analysis_results: Iterable[Mapping[str, Any]],
    *,
    rules: tuple[ThresholdRule, ...] | list[ThresholdRule],
    policy_id: str = "thresholds",
    mode: Literal["all", "any"] = "all",
) -> SelectionResult:
    """Select candidates passing all or any threshold rules."""
    require_identifier(policy_id, "policy_id")
    if mode not in {"all", "any"}:
        raise ValueError("mode must be all or any.")
    rule_tuple = tuple(rules)
    if not rule_tuple or any(not isinstance(rule, ThresholdRule) for rule in rule_tuple):
        raise ValueError("rules must contain ThresholdRule objects.")
    results = [validate_analysis_result_document(result) for result in analysis_results]
    selected_ids: set[str] = set()
    for result in results:
        outcomes = [rule.passes(result) for rule in rule_tuple]
        if (all(outcomes) if mode == "all" else any(outcomes)):
            selected_ids.add(result["candidate_ref"]["candidate_id"])
    return _selection_from_results(
        results,
        selected_ids=selected_ids,
        policy_id=policy_id,
        reason_selected="thresholds_passed",
        reason_rejected="thresholds_failed",
        configuration={"mode": mode, "rules": [rule.to_dict() for rule in rule_tuple]},
    )


__all__ = ["ThresholdDirection", "ThresholdRule", "select_by_thresholds"]
