"""Operational evolution-progress and threshold-trajectory state.

This module consumes already-computed AnalysisResult documents. It does not
execute metrics and does not redefine scientific formulas. Pareto frontier
construction delegates to the existing strict-feedback frontier machinery.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Iterable, Mapping, Sequence

from .models import CandidateRef
from .selection.fitness import metric_value
from .selection.pareto import ObjectiveSpec
from .selection.strict_feedback import (
    _deduplicate_archive,
    _frontier,
    _objective_values,
)


def _selection_projection(result: Mapping[str, Any]) -> dict[str, Any]:
    """Return a selector-readable projection without changing runtime science."""
    projected = dict(result)
    metrics = projected.get("metrics")
    if isinstance(metrics, Mapping):
        metric_rows = []
        cost = dict(projected.get("cost", {}))
        for name, value in metrics.items():
            if name.startswith("cost_"):
                cost.setdefault(str(name), value)
            else:
                metric_rows.append(
                    {"name": str(name), "status": "computed", "value": value}
                )
        projected["metrics"] = metric_rows
        projected["cost"] = cost
    return projected


def _candidate_ref(result: Mapping[str, Any]) -> CandidateRef:
    ref = dict(result["candidate_ref"])
    return CandidateRef(
        candidate_id=ref["candidate_id"],
        candidate_uri=ref.get("candidate_uri"),
        structural_hash=ref.get("structural_hash"),
        lineage_hash=ref.get("lineage_hash"),
    )


def _metric_value(result: Mapping[str, Any], name: str) -> float | None:
    value = metric_value(_selection_projection(result), name)
    return float(value) if value is not None else None


def _objective_signature(
    results: Iterable[Mapping[str, Any]],
    objectives: Sequence[ObjectiveSpec],
) -> tuple[tuple[float, ...], ...]:
    values: set[tuple[float, ...]] = set()
    objective_tuple = tuple(objectives)
    for raw in results:
        result = _selection_projection(raw)
        objective_values = _objective_values(result, objective_tuple)
        if objective_values is None:
            continue
        values.add(tuple(float(item) for item in objective_values))
    return tuple(sorted(values))


@dataclass(frozen=True)
class AccumulatedProgress:
    improved: bool
    previous_signature: tuple[tuple[float, ...], ...]
    current_signature: tuple[tuple[float, ...], ...]
    archive_refs: tuple[CandidateRef, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "improved": self.improved,
            "previous_signature": [list(item) for item in self.previous_signature],
            "current_signature": [list(item) for item in self.current_signature],
            "archive_refs": [ref.to_ref_dict() for ref in self.archive_refs],
        }


def _pareto_frontier(
    results: Iterable[Mapping[str, Any]],
    objectives: Sequence[ObjectiveSpec],
) -> tuple[dict[str, Any], ...]:
    projected = [_selection_projection(item) for item in results]
    deduplicated = _deduplicate_archive(projected)
    return tuple(_frontier(deduplicated, tuple(objectives)))


def frontier_signature(
    results: Iterable[Mapping[str, Any]],
    *,
    objectives: Sequence[ObjectiveSpec],
) -> tuple[tuple[float, ...], ...]:
    return _objective_signature(_pareto_frontier(results, objectives), objectives)


def accumulated_pareto_progress(
    *,
    previous_frontier: Iterable[Mapping[str, Any]],
    candidate_results: Iterable[Mapping[str, Any]],
    objectives: Sequence[ObjectiveSpec],
) -> AccumulatedProgress:
    previous_items = tuple(previous_frontier)
    candidate_items = tuple(candidate_results)
    previous = _pareto_frontier(previous_items, objectives)
    current = _pareto_frontier((*previous_items, *candidate_items), objectives)
    previous_signature = _objective_signature(previous, objectives)
    current_signature = _objective_signature(current, objectives)
    return AccumulatedProgress(
        improved=current_signature != previous_signature,
        previous_signature=previous_signature,
        current_signature=current_signature,
        archive_refs=tuple(_candidate_ref(result) for result in current),
    )


def accumulated_fitness_progress(
    *,
    previous_results: Iterable[Mapping[str, Any]],
    candidate_results: Iterable[Mapping[str, Any]],
    metric_name: str,
    direction: str,
    keep: int,
) -> AccumulatedProgress:
    if direction not in {"minimize", "maximize"}:
        raise ValueError("direction must be minimize or maximize.")
    if keep <= 0:
        raise ValueError("keep must be positive.")

    def ranked(items: Iterable[Mapping[str, Any]]):
        scored = []
        for raw in items:
            result = _selection_projection(raw)
            value = _metric_value(result, metric_name)
            if value is None or not math.isfinite(value):
                raise ValueError(
                    f"AnalysisResult {result.get('analysis_result_id')!r} "
                    f"does not contain finite {metric_name!r}."
                )
            scored.append((value, result))
        scored.sort(
            key=lambda item: (
                -item[0] if direction == "maximize" else item[0],
                str(item[1]["candidate_ref"]["candidate_id"]),
                str(item[1]["analysis_result_id"]),
            )
        )
        return scored[:keep]

    previous_items = tuple(previous_results)
    candidate_items = tuple(candidate_results)
    previous = ranked(previous_items)
    current = ranked((*previous_items, *candidate_items))
    previous_signature = tuple((value,) for value, _ in previous)
    current_signature = tuple((value,) for value, _ in current)
    return AccumulatedProgress(
        improved=current_signature != previous_signature,
        previous_signature=previous_signature,
        current_signature=current_signature,
        archive_refs=tuple(_candidate_ref(result) for _, result in current),
    )


@dataclass(frozen=True)
class ThresholdTrajectorySpec:
    threshold_id: str
    metric_name: str
    direction: str
    threshold: float

    def __post_init__(self) -> None:
        if not isinstance(self.threshold_id, str) or not self.threshold_id.strip():
            raise ValueError("threshold_id must be a non-empty string.")
        if not isinstance(self.metric_name, str) or not self.metric_name.strip():
            raise ValueError("metric_name must be a non-empty string.")
        if self.direction not in {"at_most", "at_least"}:
            raise ValueError("direction must be at_most or at_least.")
        object.__setattr__(self, "threshold_id", self.threshold_id.strip())
        object.__setattr__(self, "metric_name", self.metric_name.strip())
        object.__setattr__(self, "threshold", float(self.threshold))

    def passes(self, result: Mapping[str, Any]) -> bool:
        value = _metric_value(result, self.metric_name)
        if value is None:
            return False
        if self.direction == "at_most":
            return value <= self.threshold
        return value >= self.threshold


@dataclass(frozen=True)
class ThresholdTrajectoryState:
    threshold_id: str
    metric_name: str
    direction: str
    threshold: float
    generation_index: int
    parent_refs: tuple[CandidateRef, ...] = ()
    eligible_candidate_refs: tuple[CandidateRef, ...] = ()
    survivor_refs: tuple[CandidateRef, ...] = ()
    archive_refs: tuple[CandidateRef, ...] = ()
    improved: bool = False
    exhausted: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "threshold_id": self.threshold_id,
            "metric_name": self.metric_name,
            "direction": self.direction,
            "threshold": self.threshold,
            "generation_index": self.generation_index,
            "parent_refs": [ref.to_ref_dict() for ref in self.parent_refs],
            "eligible_candidate_refs": [
                ref.to_ref_dict() for ref in self.eligible_candidate_refs
            ],
            "survivor_refs": [ref.to_ref_dict() for ref in self.survivor_refs],
            "archive_refs": [ref.to_ref_dict() for ref in self.archive_refs],
            "improved": self.improved,
            "exhausted": self.exhausted,
        }

    @classmethod
    def from_mapping(cls, mapping: Mapping[str, Any]) -> "ThresholdTrajectoryState":
        data = dict(mapping)
        return cls(
            threshold_id=str(data["threshold_id"]),
            metric_name=str(data["metric_name"]),
            direction=str(data["direction"]),
            threshold=float(data["threshold"]),
            generation_index=int(data["generation_index"]),
            parent_refs=tuple(
                CandidateRef.from_ref_document(item)
                for item in data.get("parent_refs", ())
            ),
            eligible_candidate_refs=tuple(
                CandidateRef.from_ref_document(item)
                for item in data.get("eligible_candidate_refs", ())
            ),
            survivor_refs=tuple(
                CandidateRef.from_ref_document(item)
                for item in data.get("survivor_refs", ())
            ),
            archive_refs=tuple(
                CandidateRef.from_ref_document(item)
                for item in data.get("archive_refs", ())
            ),
            improved=bool(data.get("improved", False)),
            exhausted=bool(data.get("exhausted", False)),
        )


def build_threshold_trajectory_specs(
    *,
    metric_name: str,
    direction: str,
    trajectories: Mapping[str, float],
) -> tuple[ThresholdTrajectorySpec, ...]:
    return tuple(
        ThresholdTrajectorySpec(
            threshold_id=str(threshold_id),
            metric_name=metric_name,
            direction=direction,
            threshold=float(threshold),
        )
        for threshold_id, threshold in sorted(trajectories.items())
    )


def initialize_threshold_trajectories(
    *,
    specs: Sequence[ThresholdTrajectorySpec],
    analysis_results: Iterable[Mapping[str, Any]],
    objectives: Sequence[ObjectiveSpec],
) -> dict[str, ThresholdTrajectoryState]:
    results = tuple(analysis_results)
    states: dict[str, ThresholdTrajectoryState] = {}
    for spec in specs:
        eligible = tuple(result for result in results if spec.passes(result))
        if not eligible:
            raise ValueError(
                f"threshold trajectory {spec.threshold_id!r} has no eligible G0 parent."
            )
        progress = accumulated_pareto_progress(
            previous_frontier=(),
            candidate_results=eligible,
            objectives=objectives,
        )
        eligible_refs = tuple(_candidate_ref(result) for result in eligible)
        states[spec.threshold_id] = ThresholdTrajectoryState(
            threshold_id=spec.threshold_id,
            metric_name=spec.metric_name,
            direction=spec.direction,
            threshold=spec.threshold,
            generation_index=0,
            parent_refs=progress.archive_refs,
            eligible_candidate_refs=eligible_refs,
            survivor_refs=progress.archive_refs,
            archive_refs=progress.archive_refs,
            improved=False,
            exhausted=False,
        )
    return states


def threshold_trajectories_to_mapping(
    states: Mapping[str, ThresholdTrajectoryState],
) -> dict[str, dict[str, Any]]:
    return {
        threshold_id: state.to_dict()
        for threshold_id, state in sorted(states.items())
    }


def threshold_trajectories_from_mapping(
    mapping: Mapping[str, Any],
) -> dict[str, ThresholdTrajectoryState]:
    return {
        str(threshold_id): (
            value
            if isinstance(value, ThresholdTrajectoryState)
            else ThresholdTrajectoryState.from_mapping(value)
        )
        for threshold_id, value in sorted(mapping.items())
    }


def active_parent_refs_by_trajectory(
    states: Mapping[str, ThresholdTrajectoryState | Mapping[str, Any]],
) -> dict[str, tuple[CandidateRef, ...]]:
    active: dict[str, tuple[CandidateRef, ...]] = {}
    for threshold_id, raw in sorted(states.items()):
        if isinstance(raw, ThresholdTrajectoryState):
            exhausted = raw.exhausted
            refs = raw.parent_refs
        else:
            data = dict(raw)
            exhausted = bool(data.get("exhausted", False))
            refs = tuple(
                ref if isinstance(ref, CandidateRef) else CandidateRef.from_ref_document(ref)
                for ref in data.get("parent_refs", ())
            )
        if not exhausted and refs:
            active[str(threshold_id)] = tuple(refs)
    return active


def apply_threshold_patience_state(
    states: Mapping[str, ThresholdTrajectoryState],
    patience_states: Mapping[str, Any],
) -> dict[str, ThresholdTrajectoryState]:
    updated: dict[str, ThresholdTrajectoryState] = {}
    for threshold_id, state in sorted(states.items()):
        raw = patience_states.get(threshold_id, {})
        exhausted = (
            bool(raw.exhausted)
            if hasattr(raw, "exhausted")
            else bool(dict(raw).get("exhausted", False))
        )
        updated[threshold_id] = ThresholdTrajectoryState(
            threshold_id=state.threshold_id,
            metric_name=state.metric_name,
            direction=state.direction,
            threshold=state.threshold,
            generation_index=state.generation_index,
            parent_refs=state.parent_refs,
            eligible_candidate_refs=state.eligible_candidate_refs,
            survivor_refs=state.survivor_refs,
            archive_refs=state.archive_refs,
            improved=state.improved,
            exhausted=exhausted,
        )
    return updated


__all__ = [
    "AccumulatedProgress",
    "ThresholdTrajectorySpec",
    "ThresholdTrajectoryState",
    "accumulated_fitness_progress",
    "accumulated_pareto_progress",
    "active_parent_refs_by_trajectory",
    "apply_threshold_patience_state",
    "build_threshold_trajectory_specs",
    "frontier_signature",
    "initialize_threshold_trajectories",
    "threshold_trajectories_from_mapping",
    "threshold_trajectories_to_mapping",
]

