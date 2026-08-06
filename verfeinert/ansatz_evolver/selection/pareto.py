"""Pareto selection over canonical AnalysisResult JSON."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Literal

from ..validation import validate_analysis_result_document
from .fitness import SelectionResult, _selection_from_results, metric_value


ObjectiveDirection = Literal["minimize", "maximize"]


@dataclass(frozen=True)
class ObjectiveSpec:
    """One Pareto objective over metric or cost values."""

    name: str
    direction: ObjectiveDirection = "minimize"

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("objective name must be a non-empty string.")
        object.__setattr__(self, "name", self.name.strip())
        if self.direction not in {"minimize", "maximize"}:
            raise ValueError("direction must be minimize or maximize.")

    def value(self, result: Mapping[str, Any]) -> float:
        """Return the numeric objective value for a result."""
        value = metric_value(result, self.name)
        if value is None:
            raise ValueError(f"AnalysisResult {result['analysis_result_id']} lacks objective {self.name!r}.")
        return float(value)

    def better_or_equal(self, left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
        """Return whether left is no worse than right for this objective."""
        left_value = self.value(left)
        right_value = self.value(right)
        if self.direction == "minimize":
            return left_value <= right_value
        return left_value >= right_value

    def strictly_better(self, left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
        """Return whether left is strictly better than right."""
        left_value = self.value(left)
        right_value = self.value(right)
        if self.direction == "minimize":
            return left_value < right_value
        return left_value > right_value

    def to_dict(self) -> dict[str, str]:
        """Return JSON-safe objective data."""
        return {"name": self.name, "direction": self.direction}


def dominates(
    left: Mapping[str, Any],
    right: Mapping[str, Any],
    objectives: Iterable[ObjectiveSpec],
) -> bool:
    """Return true when left Pareto-dominates right."""
    objective_tuple = _objective_tuple(objectives)
    left_doc = validate_analysis_result_document(left)
    right_doc = validate_analysis_result_document(right)
    return all(objective.better_or_equal(left_doc, right_doc) for objective in objective_tuple) and any(
        objective.strictly_better(left_doc, right_doc)
        for objective in objective_tuple
    )


def non_dominated_ranks(
    analysis_results: Iterable[Mapping[str, Any]],
    objectives: Iterable[ObjectiveSpec],
) -> dict[str, int]:
    """Return deterministic non-dominated ranks keyed by candidate ID."""
    objective_tuple = _objective_tuple(objectives)
    remaining = [validate_analysis_result_document(result) for result in analysis_results]
    ranks: dict[str, int] = {}
    rank = 0
    while remaining:
        frontier = _frontier(remaining, objective_tuple)
        frontier_ids = {result["candidate_ref"]["candidate_id"] for result in frontier}
        for candidate_id in sorted(frontier_ids):
            ranks[candidate_id] = rank
        remaining = [
            result
            for result in remaining
            if result["candidate_ref"]["candidate_id"] not in frontier_ids
        ]
        rank += 1
    return ranks


def select_pareto_front(
    analysis_results: Iterable[Mapping[str, Any]],
    *,
    objectives: Iterable[ObjectiveSpec],
    policy_id: str = "pareto",
) -> SelectionResult:
    """Select the non-dominated frontier."""
    objective_tuple = _objective_tuple(objectives)
    results = [validate_analysis_result_document(result) for result in analysis_results]
    frontier_ids = {
        result["candidate_ref"]["candidate_id"]
        for result in _frontier(results, objective_tuple)
    }
    return _selection_from_results(
        results,
        selected_ids=frontier_ids,
        policy_id=policy_id,
        reason_selected="pareto_frontier",
        reason_rejected="pareto_dominated",
        configuration={"objectives": [objective.to_dict() for objective in objective_tuple]},
    )


def _frontier(results: list[dict[str, Any]], objectives: tuple[ObjectiveSpec, ...]) -> list[dict[str, Any]]:
    frontier: list[dict[str, Any]] = []
    for candidate in sorted(results, key=lambda item: (item["candidate_ref"]["candidate_id"], item["analysis_result_id"])):
        if any(dominates(other, candidate, objectives) for other in results if other is not candidate):
            continue
        frontier.append(candidate)
    return frontier


def _objective_tuple(objectives: Iterable[ObjectiveSpec]) -> tuple[ObjectiveSpec, ...]:
    objective_tuple = tuple(objectives)
    if not objective_tuple or any(not isinstance(objective, ObjectiveSpec) for objective in objective_tuple):
        raise ValueError("objectives must contain ObjectiveSpec records.")
    return objective_tuple


__all__ = [
    "ObjectiveDirection",
    "ObjectiveSpec",
    "dominates",
    "non_dominated_ranks",
    "select_pareto_front",
]
