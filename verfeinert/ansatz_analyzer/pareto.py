"""Pareto classification over canonical AnalysisResult collections."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
import math
from typing import Any

from verfeinert.core.io.serialization import to_json_safe

from .collections import AnalysisResultCollection, cost_value, metric_value
from .models import ClassificationRecord


class ParetoError(ValueError):
    """Raised when Pareto inputs or configuration are invalid."""


OBJECTIVE_DIRECTIONS = ("maximize", "minimize")


@dataclass(frozen=True)
class ObjectiveSpec:
    """One Pareto objective resolved from an AnalysisResult metric."""

    metric_name: str
    direction: str = "maximize"
    value_key: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.metric_name, str) or not self.metric_name.strip():
            raise ParetoError("objective metric_name must be a non-empty string.")
        object.__setattr__(self, "metric_name", self.metric_name.strip())
        if self.direction not in OBJECTIVE_DIRECTIONS:
            raise ParetoError(f"objective direction must be one of {OBJECTIVE_DIRECTIONS}.")
        if self.value_key is not None and not str(self.value_key).strip():
            raise ParetoError("objective value_key must be non-empty when provided.")


@dataclass(frozen=True)
class ParetoConfig:
    """Configuration for two-or-more-objective Pareto classification."""

    objectives: tuple[ObjectiveSpec, ...] = (
        ObjectiveSpec("expressibility", "maximize"),
        ObjectiveSpec("trainability", "maximize"),
    )
    eps: float = 1e-12
    cost_field: str = "structural_cost"
    cost_thresholds: tuple[float, ...] = ()
    reference_label: str = "reference"

    def __post_init__(self) -> None:
        objectives = tuple(
            item if isinstance(item, ObjectiveSpec) else ObjectiveSpec(**item)  # type: ignore[arg-type]
            for item in self.objectives
        )
        if len(objectives) < 2:
            raise ParetoError("Pareto classification requires at least two objectives.")
        if len({item.metric_name for item in objectives}) != len(objectives):
            raise ParetoError("Pareto objective metric names must be unique.")
        eps = float(self.eps)
        if not math.isfinite(eps) or eps < 0.0:
            raise ParetoError("eps must be finite and non-negative.")
        thresholds = tuple(float(item) for item in self.cost_thresholds)
        if any(not math.isfinite(item) for item in thresholds):
            raise ParetoError("cost_thresholds must contain finite values.")
        object.__setattr__(self, "objectives", objectives)
        object.__setattr__(self, "eps", eps)
        object.__setattr__(self, "cost_thresholds", thresholds)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe config snapshot."""
        return to_json_safe(
            {
                "objectives": [
                    {
                        "metric_name": item.metric_name,
                        "direction": item.direction,
                        "value_key": item.value_key,
                    }
                    for item in self.objectives
                ],
                "eps": self.eps,
                "cost_field": self.cost_field,
                "cost_thresholds": list(self.cost_thresholds),
                "cost_role": "external_constraint",
                "cost_is_pareto_objective": False,
                "reference_label": self.reference_label,
            },
        )


@dataclass(frozen=True)
class ParetoCandidateResult:
    """Pareto result for one candidate."""

    candidate_id: str
    analysis_result_id: str
    objective_values: dict[str, float]
    cost_value: float | None
    pareto_rank: int | None
    is_frontier: bool
    dominated_by: tuple[str, ...] = ()
    dominates: tuple[str, ...] = ()
    dominated_by_reference: bool = False
    dominates_reference: bool = False
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe result payload."""
        return to_json_safe(
            {
                "candidate_id": self.candidate_id,
                "analysis_result_id": self.analysis_result_id,
                "objective_values": self.objective_values,
                "cost_value": self.cost_value,
                "pareto_rank": self.pareto_rank,
                "is_frontier": self.is_frontier,
                "dominated_by": list(self.dominated_by),
                "dominates": list(self.dominates),
                "dominated_by_reference": self.dominated_by_reference,
                "dominates_reference": self.dominates_reference,
                "warnings": list(self.warnings),
            },
        )


@dataclass(frozen=True)
class ParetoResult:
    """Collection-level Pareto classification output."""

    config: ParetoConfig
    candidates: tuple[ParetoCandidateResult, ...]
    frontier_candidate_ids: tuple[str, ...]
    dominated_candidate_ids: tuple[str, ...]
    frontiers_by_cost_threshold: dict[float, tuple[str, ...]]
    classifications_by_candidate_id: dict[str, tuple[ClassificationRecord, ...]]
    warnings: tuple[str, ...] = ()

    def to_classification_records(self) -> tuple[ClassificationRecord, ...]:
        """Return all classification records in deterministic candidate order."""
        records: list[ClassificationRecord] = []
        for candidate in self.candidates:
            records.extend(self.classifications_by_candidate_id[candidate.candidate_id])
        return tuple(records)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe derived Pareto payload."""
        return to_json_safe(
            {
                "schema_version": "verfeinert.pareto_result.v1",
                "transform": "pareto_classification",
                "transform_version": "1",
                "config": self.config.to_dict(),
                "frontier_candidate_ids": list(self.frontier_candidate_ids),
                "dominated_candidate_ids": list(self.dominated_candidate_ids),
                "frontiers_by_cost_threshold": {
                    str(threshold): list(ids)
                    for threshold, ids in self.frontiers_by_cost_threshold.items()
                },
                "candidates": [item.to_dict() for item in self.candidates],
                "classifications": [
                    item.to_dict()
                    for item in self.to_classification_records()
                ],
                "warnings": list(self.warnings),
            },
        )


def dominates(
    values_a: Mapping[str, float],
    values_b: Mapping[str, float],
    *,
    config: ParetoConfig | None = None,
) -> bool:
    """Return whether objective values A dominate objective values B."""
    resolved = config or ParetoConfig()
    no_worse = True
    strictly_better = False
    for objective in resolved.objectives:
        a = _finite_value(values_a.get(objective.metric_name))
        b = _finite_value(values_b.get(objective.metric_name))
        if a is None or b is None:
            return False
        if objective.direction == "maximize":
            no_worse &= a >= b - resolved.eps
            strictly_better |= a > b + resolved.eps
        else:
            no_worse &= a <= b + resolved.eps
            strictly_better |= a < b - resolved.eps
    return bool(no_worse and strictly_better)


def compute_pareto_classifications(
    collection: AnalysisResultCollection,
    *,
    reference_collection: AnalysisResultCollection | None = None,
    config: ParetoConfig | None = None,
) -> ParetoResult:
    """Compute Pareto ranks and classification records for one collection."""
    if not isinstance(collection, AnalysisResultCollection):
        raise ParetoError("collection must be an AnalysisResultCollection.")
    if reference_collection is not None and not isinstance(reference_collection, AnalysisResultCollection):
        raise ParetoError("reference_collection must be an AnalysisResultCollection.")
    resolved = config or ParetoConfig()
    entries = [_entry_from_document(document, resolved) for document in collection]
    rankable = [entry for entry in entries if not entry["warnings"]]
    ranks = _non_dominated_ranks(rankable, resolved)
    dominance_pairs = _dominance_pairs(rankable, resolved)

    reference_front = []
    if reference_collection is not None:
        reference_entries = [
            entry
            for entry in (_entry_from_document(document, resolved) for document in reference_collection)
            if not entry["warnings"]
        ]
        reference_front = [
            entry
            for entry in reference_entries
            if ranks_for_entries(reference_entries, resolved).get(entry["candidate_id"]) == 1
        ]

    candidate_results: list[ParetoCandidateResult] = []
    warnings: list[str] = []
    for entry in entries:
        candidate_id = entry["candidate_id"]
        entry_warnings = tuple(entry["warnings"])
        warnings.extend(entry_warnings)
        rank = ranks.get(candidate_id)
        candidate_results.append(
            ParetoCandidateResult(
                candidate_id=candidate_id,
                analysis_result_id=entry["analysis_result_id"],
                objective_values=dict(entry["objective_values"]),
                cost_value=entry["cost_value"],
                pareto_rank=rank,
                is_frontier=rank == 1,
                dominated_by=tuple(dominance_pairs["dominated_by"].get(candidate_id, ())),
                dominates=tuple(dominance_pairs["dominates"].get(candidate_id, ())),
                dominated_by_reference=any(
                    dominates(ref["objective_values"], entry["objective_values"], config=resolved)
                    for ref in reference_front
                ),
                dominates_reference=any(
                    dominates(entry["objective_values"], ref["objective_values"], config=resolved)
                    for ref in reference_front
                ),
                warnings=entry_warnings,
            ),
        )

    frontier_ids = tuple(item.candidate_id for item in candidate_results if item.is_frontier)
    dominated_ids = tuple(
        item.candidate_id
        for item in candidate_results
        if item.pareto_rank is not None and not item.is_frontier
    )
    frontiers_by_threshold = _cost_threshold_frontiers(rankable, resolved)
    classifications = {
        item.candidate_id: _classification_records_for_candidate(
            item,
            config=resolved,
            frontiers_by_threshold=frontiers_by_threshold,
        )
        for item in candidate_results
    }
    return ParetoResult(
        config=resolved,
        candidates=tuple(candidate_results),
        frontier_candidate_ids=frontier_ids,
        dominated_candidate_ids=dominated_ids,
        frontiers_by_cost_threshold=frontiers_by_threshold,
        classifications_by_candidate_id=classifications,
        warnings=tuple(dict.fromkeys(warnings)),
    )


def ranks_for_entries(
    entries: list[dict[str, Any]],
    config: ParetoConfig,
) -> dict[str, int]:
    """Return non-dominated ranks for already-normalized entries."""
    return _non_dominated_ranks(entries, config)


def with_pareto_classifications(
    collection: AnalysisResultCollection,
    result: ParetoResult,
) -> AnalysisResultCollection:
    """Return a new collection with Pareto classification records appended."""
    documents = []
    for document in collection:
        candidate_id = document["candidate_ref"]["candidate_id"]
        appended = dict(document)
        existing = list(appended.get("classifications", []))
        existing.extend(
            record.to_dict()
            for record in result.classifications_by_candidate_id.get(candidate_id, ())
        )
        appended["classifications"] = existing
        documents.append(appended)
    return AnalysisResultCollection.from_records(
        documents,
        collection_id=f"{collection.collection_id}:pareto",
        metadata={"source_collection_id": collection.collection_id},
    )


def _entry_from_document(
    document: Mapping[str, Any],
    config: ParetoConfig,
) -> dict[str, Any]:
    candidate_id = document["candidate_ref"]["candidate_id"]
    objective_values: dict[str, float] = {}
    warnings: list[str] = []
    for objective in config.objectives:
        value = metric_value(
            document,
            objective.metric_name,
            value_key=objective.value_key,
        )
        if value is None:
            warnings.append(
                f"{candidate_id}: missing computed objective {objective.metric_name!r}",
            )
        else:
            objective_values[objective.metric_name] = value
    return {
        "candidate_id": candidate_id,
        "analysis_result_id": document["analysis_result_id"],
        "objective_values": objective_values,
        "cost_value": cost_value(document, config.cost_field),
        "warnings": warnings,
    }


def _non_dominated_ranks(
    entries: list[dict[str, Any]],
    config: ParetoConfig,
) -> dict[str, int]:
    ranks: dict[str, int] = {}
    remaining = list(entries)
    rank = 1
    while remaining:
        front: list[dict[str, Any]] = []
        for entry in remaining:
            dominated = any(
                other is not entry
                and dominates(other["objective_values"], entry["objective_values"], config=config)
                for other in remaining
            )
            if not dominated:
                front.append(entry)
        if not front:
            raise ParetoError("Unable to compute Pareto ranks for the provided entries.")
        for entry in front:
            ranks[entry["candidate_id"]] = rank
        front_ids = {entry["candidate_id"] for entry in front}
        remaining = [
            entry
            for entry in remaining
            if entry["candidate_id"] not in front_ids
        ]
        rank += 1
    return ranks


def _dominance_pairs(
    entries: list[dict[str, Any]],
    config: ParetoConfig,
) -> dict[str, dict[str, list[str]]]:
    dominated_by: dict[str, list[str]] = {entry["candidate_id"]: [] for entry in entries}
    dominates_map: dict[str, list[str]] = {entry["candidate_id"]: [] for entry in entries}
    for entry_a in entries:
        for entry_b in entries:
            if entry_a is entry_b:
                continue
            if dominates(entry_a["objective_values"], entry_b["objective_values"], config=config):
                dominates_map[entry_a["candidate_id"]].append(entry_b["candidate_id"])
                dominated_by[entry_b["candidate_id"]].append(entry_a["candidate_id"])
    return {
        "dominated_by": dominated_by,
        "dominates": dominates_map,
    }


def _cost_threshold_frontiers(
    entries: list[dict[str, Any]],
    config: ParetoConfig,
) -> dict[float, tuple[str, ...]]:
    frontiers: dict[float, tuple[str, ...]] = {}
    for threshold in config.cost_thresholds:
        eligible = [
            entry
            for entry in entries
            if entry["cost_value"] is not None and entry["cost_value"] <= threshold
        ]
        ranks = _non_dominated_ranks(eligible, config) if eligible else {}
        frontiers[threshold] = tuple(
            entry["candidate_id"]
            for entry in eligible
            if ranks.get(entry["candidate_id"]) == 1
        )
    return frontiers


def _classification_records_for_candidate(
    candidate: ParetoCandidateResult,
    *,
    config: ParetoConfig,
    frontiers_by_threshold: Mapping[float, tuple[str, ...]],
) -> tuple[ClassificationRecord, ...]:
    if candidate.pareto_rank is None:
        label = "unrankable"
    elif candidate.is_frontier:
        label = "frontier"
    else:
        label = "dominated"
    metadata = {
        "classification_policy": "pareto",
        "objective_values": candidate.objective_values,
        "objective_directions": {
            item.metric_name: item.direction for item in config.objectives
        },
        "pareto_rank": candidate.pareto_rank,
        "dominated_by": list(candidate.dominated_by),
        "dominates": list(candidate.dominates),
        "dominated_by_reference": candidate.dominated_by_reference,
        "dominates_reference": candidate.dominates_reference,
        "cost_role": "external_constraint",
        "warnings": list(candidate.warnings),
    }
    records = [
        ClassificationRecord(
            classification_id=f"pareto-front-{candidate.candidate_id}",
            name="pareto_front",
            label=label,
            confidence=1.0,
            metadata=metadata,
        ),
    ]
    for threshold, frontier_ids in frontiers_by_threshold.items():
        cost_label = _cost_threshold_label(candidate, threshold, frontier_ids)
        records.append(
            ClassificationRecord(
                classification_id=(
                    f"pareto-cost-{_threshold_token(threshold)}-{candidate.candidate_id}"
                ),
                name="pareto_cost_threshold",
                label=cost_label,
                threshold=threshold,
                confidence=1.0,
                metadata={
                    "classification_policy": "pareto_cost_threshold",
                    "cost_field": config.cost_field,
                    "cost_value": candidate.cost_value,
                    "cost_role": "external_constraint",
                    "is_cost_threshold_frontier": candidate.candidate_id in frontier_ids,
                },
            ),
        )
    return tuple(records)


def _cost_threshold_label(
    candidate: ParetoCandidateResult,
    threshold: float,
    frontier_ids: tuple[str, ...],
) -> str:
    if candidate.cost_value is None:
        return "cost_unavailable"
    if candidate.cost_value > threshold:
        return "ineligible"
    if candidate.candidate_id in frontier_ids:
        return "frontier"
    return "eligible_dominated"


def _finite_value(value: Any) -> float | None:
    if type(value) not in {int, float}:
        return None
    numeric = float(value)
    return numeric if math.isfinite(numeric) else None


def _threshold_token(value: float) -> str:
    return str(float(value)).replace("-", "m").replace(".", "p")


__all__ = [
    "ObjectiveSpec",
    "ParetoCandidateResult",
    "ParetoConfig",
    "ParetoError",
    "ParetoResult",
    "compute_pareto_classifications",
    "dominates",
    "ranks_for_entries",
    "with_pareto_classifications",
]
