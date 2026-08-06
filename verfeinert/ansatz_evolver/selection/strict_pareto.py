"""Strict-Pareto selection against optional reference results."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from ..validation import validate_analysis_result_document
from .fitness import SelectionResult, _selection_from_results
from .pareto import ObjectiveSpec, dominates, select_pareto_front


def select_strict_pareto(
    analysis_results: Iterable[Mapping[str, Any]],
    *,
    objectives: Iterable[ObjectiveSpec],
    reference_results: Iterable[Mapping[str, Any]] = (),
    policy_id: str = "strict_pareto",
) -> SelectionResult:
    """Select frontier candidates that are not dominated by the reference set."""
    objective_tuple = tuple(objectives)
    results = [validate_analysis_result_document(result) for result in analysis_results]
    references = [validate_analysis_result_document(result) for result in reference_results]
    frontier = select_pareto_front(results, objectives=objective_tuple, policy_id=f"{policy_id}:frontier")
    selected_ids: set[str] = set()
    for candidate_ref in frontier.survivor_refs:
        candidate_result = next(
            result for result in results if result["candidate_ref"]["candidate_id"] == candidate_ref.candidate_id
        )
        if any(dominates(reference, candidate_result, objective_tuple) for reference in references):
            continue
        if references and not any(dominates(candidate_result, reference, objective_tuple) for reference in references):
            continue
        selected_ids.add(candidate_ref.candidate_id)
    if not references:
        selected_ids = {ref.candidate_id for ref in frontier.survivor_refs}
    return _selection_from_results(
        results,
        selected_ids=selected_ids,
        policy_id=policy_id,
        reason_selected="strict_pareto_selected",
        reason_rejected="strict_pareto_rejected",
        configuration={
            "objectives": [objective.to_dict() for objective in objective_tuple],
            "reference_count": len(references),
        },
    )


__all__ = ["select_strict_pareto"]
