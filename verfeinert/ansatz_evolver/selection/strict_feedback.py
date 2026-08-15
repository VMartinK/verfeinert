"""Strict Pareto-feedback selection with an accumulated archive."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
import math
from typing import Any

from ..models import AnalysisResultRef, CandidateRef
from ..validation import validate_analysis_result_document
from .fitness import SelectionDecision, SelectionResult, metric_value
from .pareto import ObjectiveSpec


def select_strict_pareto_feedback(
    analysis_results: Iterable[Mapping[str, Any]],
    *,
    objectives: Iterable[ObjectiveSpec],
    reference_results: Iterable[Mapping[str, Any]] = (),
    thresholds: Mapping[str, float] | None = None,
    threshold_direction: str = "at_most",
    strict_ties: bool = True,
    policy_id: str = "strict_pareto_feedback",
) -> SelectionResult:
    """Select strict new Pareto candidates against an accumulated archive."""
    objective_tuple = tuple(objectives)
    if not objective_tuple or any(not isinstance(objective, ObjectiveSpec) for objective in objective_tuple):
        raise ValueError("objectives must contain ObjectiveSpec records.")
    if threshold_direction not in {"at_most", "at_least"}:
        raise ValueError("threshold_direction must be at_most or at_least.")
    threshold_map = {str(name): float(value) for name, value in dict(thresholds or {}).items()}
    results = [validate_analysis_result_document(result) for result in analysis_results]
    references = [validate_analysis_result_document(result) for result in reference_results]

    decisions_by_candidate: dict[str, SelectionDecision] = {}
    valid_new: list[dict[str, Any]] = []
    reference_values = [_objective_values(result, objective_tuple) for result in references]
    for result in sorted(results, key=_result_sort_key):
        candidate_id = result["candidate_ref"]["candidate_id"]
        objective_values = _objective_values(result, objective_tuple)
        if objective_values is None:
            decisions_by_candidate[candidate_id] = _decision(result, False, "missing_metric")
            continue
        if not _passes_thresholds(result, threshold_map, threshold_direction):
            decisions_by_candidate[candidate_id] = _decision(result, False, "cost_threshold_failed")
            continue
        if strict_ties and any(objective_values == values for values in reference_values if values is not None):
            decisions_by_candidate[candidate_id] = _decision(
                result,
                False,
                "duplicate_or_tie_with_accumulated_frontier",
            )
            continue
        if any(_dominates(reference, result, objective_tuple) for reference in references):
            decisions_by_candidate[candidate_id] = _decision(result, False, "dominated_by_accumulated_frontier")
            continue
        valid_new.append(result)

    selected_ids = {
        result["candidate_ref"]["candidate_id"]
        for result in _frontier(valid_new, objective_tuple)
    }
    for result in valid_new:
        candidate_id = result["candidate_ref"]["candidate_id"]
        decisions_by_candidate[candidate_id] = _decision(
            result,
            candidate_id in selected_ids,
            "selected_strict_new_pareto" if candidate_id in selected_ids else "dominated_within_generation",
        )

    selected_results = [result for result in results if result["candidate_ref"]["candidate_id"] in selected_ids]
    archive_results = _frontier(_deduplicate_archive([*references, *selected_results]), objective_tuple)
    survivors = tuple(_candidate_ref(result) for result in selected_results)
    rejected = tuple(
        _candidate_ref(result)
        for result in results
        if result["candidate_ref"]["candidate_id"] not in selected_ids
    )
    decisions = tuple(decisions_by_candidate[result["candidate_ref"]["candidate_id"]] for result in sorted(results, key=_result_sort_key))
    return SelectionResult(
        policy_id=policy_id,
        survivor_refs=survivors,
        rejected_refs=rejected,
        archive_refs=tuple(_candidate_ref(result) for result in archive_results),
        decisions=decisions,
        analysis_result_refs=tuple(AnalysisResultRef.from_analysis_result_document(result) for result in results),
        configuration={
            "objectives": [objective.to_dict() for objective in objective_tuple],
            "thresholds": dict(threshold_map),
            "threshold_direction": threshold_direction,
            "strict_ties": strict_ties,
            "reference_count": len(references),
            "cost_filter_only": True,
            "combined_score_used": False,
        },
    )


def _passes_thresholds(result: Mapping[str, Any], thresholds: Mapping[str, float], direction: str) -> bool:
    for name, threshold in thresholds.items():
        value = metric_value(result, name)
        if value is None or not math.isfinite(float(value)):
            return False
        if direction == "at_most" and float(value) > threshold:
            return False
        if direction == "at_least" and float(value) < threshold:
            return False
    return True


def _objective_values(
    result: Mapping[str, Any],
    objectives: tuple[ObjectiveSpec, ...],
) -> tuple[float, ...] | None:
    values: list[float] = []
    for objective in objectives:
        value = metric_value(result, objective.name)
        if value is None or not math.isfinite(float(value)):
            return None
        values.append(float(value))
    return tuple(values)


def _dominates(left: Mapping[str, Any], right: Mapping[str, Any], objectives: tuple[ObjectiveSpec, ...]) -> bool:
    left_values = _objective_values(left, objectives)
    right_values = _objective_values(right, objectives)
    if left_values is None or right_values is None:
        return False
    no_worse = []
    strictly_better = []
    for index, objective in enumerate(objectives):
        if objective.direction == "minimize":
            no_worse.append(left_values[index] <= right_values[index])
            strictly_better.append(left_values[index] < right_values[index])
        else:
            no_worse.append(left_values[index] >= right_values[index])
            strictly_better.append(left_values[index] > right_values[index])
    return all(no_worse) and any(strictly_better)


def _frontier(results: list[dict[str, Any]], objectives: tuple[ObjectiveSpec, ...]) -> list[dict[str, Any]]:
    frontier: list[dict[str, Any]] = []
    for candidate in sorted(results, key=_result_sort_key):
        if any(_dominates(other, candidate, objectives) for other in results if other is not candidate):
            continue
        frontier.append(candidate)
    return frontier


def _deduplicate_archive(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for result in results:
        candidate_ref = dict(result["candidate_ref"])
        key = str(candidate_ref.get("structural_hash") or candidate_ref["candidate_id"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(result)
    return deduped


def _candidate_ref(result: Mapping[str, Any]) -> CandidateRef:
    ref = dict(result["candidate_ref"])
    return CandidateRef(
        candidate_id=ref["candidate_id"],
        candidate_uri=ref.get("candidate_uri"),
        structural_hash=ref.get("structural_hash"),
    )


def _decision(result: Mapping[str, Any], selected: bool, reason: str) -> SelectionDecision:
    return SelectionDecision(
        candidate_id=result["candidate_ref"]["candidate_id"],
        analysis_result_id=result["analysis_result_id"],
        selected=selected,
        reason=reason,
    )


def _result_sort_key(result: Mapping[str, Any]) -> tuple[str, str]:
    return (str(result["candidate_ref"]["candidate_id"]), str(result["analysis_result_id"]))


__all__ = ["select_strict_pareto_feedback"]
