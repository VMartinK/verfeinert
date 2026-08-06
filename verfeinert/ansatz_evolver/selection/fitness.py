"""Fitness scoring over AnalysisResult JSON documents."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
import math
from typing import Any, Literal

from ..models import AnalysisResultRef, CandidateRef, require_identifier, require_mapping
from ..validation import validate_analysis_result_document


Direction = Literal["minimize", "maximize"]


@dataclass(frozen=True)
class SelectionDecision:
    """One candidate-level selection decision."""

    candidate_id: str
    analysis_result_id: str
    selected: bool
    reason: str
    score: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "candidate_id", require_identifier(self.candidate_id, "candidate_id"))
        object.__setattr__(
            self,
            "analysis_result_id",
            require_identifier(self.analysis_result_id, "analysis_result_id"),
        )
        if type(self.selected) is not bool:
            raise ValueError("selected must be a boolean.")
        if not isinstance(self.reason, str) or not self.reason.strip():
            raise ValueError("reason must be a non-empty string.")
        if self.score is not None and not math.isfinite(float(self.score)):
            raise ValueError("score must be finite when provided.")
        object.__setattr__(self, "metadata", require_mapping(self.metadata, "metadata"))

    def to_dict(self) -> dict[str, Any]:
        """Return JSON-safe decision data."""
        payload: dict[str, Any] = {
            "candidate_id": self.candidate_id,
            "analysis_result_id": self.analysis_result_id,
            "selected": self.selected,
            "reason": self.reason,
        }
        if self.score is not None:
            payload["score"] = self.score
        if self.metadata:
            payload["metadata"] = dict(self.metadata)
        return payload


@dataclass(frozen=True)
class SelectionResult:
    """Selection result containing survivor and rejected candidate references."""

    policy_id: str
    survivor_refs: tuple[CandidateRef, ...]
    rejected_refs: tuple[CandidateRef, ...]
    decisions: tuple[SelectionDecision, ...]
    configuration: dict[str, Any] = field(default_factory=dict)
    analysis_result_refs: tuple[AnalysisResultRef, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "policy_id", require_identifier(self.policy_id, "policy_id"))
        for field_name in ("survivor_refs", "rejected_refs"):
            refs = tuple(getattr(self, field_name))
            if any(not isinstance(ref, CandidateRef) for ref in refs):
                raise ValueError(f"{field_name} must contain CandidateRef objects.")
            object.__setattr__(self, field_name, refs)
        decisions = tuple(self.decisions)
        if any(not isinstance(decision, SelectionDecision) for decision in decisions):
            raise ValueError("decisions must contain SelectionDecision objects.")
        object.__setattr__(self, "decisions", decisions)
        analysis_refs = tuple(self.analysis_result_refs)
        if any(not isinstance(ref, AnalysisResultRef) for ref in analysis_refs):
            raise ValueError("analysis_result_refs must contain AnalysisResultRef objects.")
        object.__setattr__(self, "analysis_result_refs", analysis_refs)
        object.__setattr__(self, "configuration", require_mapping(self.configuration, "configuration"))

    def to_dict(self) -> dict[str, Any]:
        """Return JSON-safe selection audit data."""
        return {
            "policy_id": self.policy_id,
            "survivor_refs": [ref.to_ref_dict() for ref in self.survivor_refs],
            "rejected_refs": [ref.to_ref_dict() for ref in self.rejected_refs],
            "analysis_result_refs": [ref.to_ref_dict() for ref in self.analysis_result_refs],
            "decisions": [decision.to_dict() for decision in self.decisions],
            "configuration": dict(self.configuration),
        }


def select_by_fitness(
    analysis_results: Iterable[Mapping[str, Any]],
    *,
    metric_name: str = "structural_cost",
    keep: int = 1,
    direction: Direction = "minimize",
    policy_id: str = "fitness",
) -> SelectionResult:
    """Select candidates by one metric or cost value."""
    if keep < 0:
        raise ValueError("keep must be non-negative.")
    if direction not in {"minimize", "maximize"}:
        raise ValueError("direction must be minimize or maximize.")
    results = [validate_analysis_result_document(result) for result in analysis_results]
    scored = [
        (metric_value(result, metric_name), result)
        for result in results
    ]
    for value, result in scored:
        if value is None or not math.isfinite(float(value)):
            raise ValueError(f"Result {result['analysis_result_id']} does not contain finite {metric_name!r}.")
    if direction == "maximize":
        scored.sort(
            key=lambda item: (
                -float(item[0]),
                item[1]["candidate_ref"]["candidate_id"],
                item[1]["analysis_result_id"],
            ),
        )
    else:
        scored.sort(
            key=lambda item: (
                float(item[0]),
                item[1]["candidate_ref"]["candidate_id"],
                item[1]["analysis_result_id"],
            ),
        )
    selected_ids = {
        result["candidate_ref"]["candidate_id"]
        for _, result in scored[:keep]
    }
    return _selection_from_results(
        results,
        selected_ids=selected_ids,
        policy_id=policy_id,
        reason_selected="selected_by_fitness",
        reason_rejected="fitness_not_selected",
        scores={
            result["analysis_result_id"]: float(value)
            for value, result in scored
        },
        configuration={
            "metric_name": metric_name,
            "keep": keep,
            "direction": direction,
        },
    )


def metric_value(result: Mapping[str, Any], name: str) -> float | None:
    """Return a metric value, falling back to a cost field of the same name."""
    cost = result.get("cost", {})
    if isinstance(cost, Mapping) and name in cost:
        value = cost[name]
        return float(value) if isinstance(value, (int, float)) else None
    for metric in result.get("metrics", ()):
        if not isinstance(metric, Mapping):
            continue
        if metric.get("name") == name and metric.get("status") == "computed":
            value = metric.get("value")
            return float(value) if isinstance(value, (int, float)) else None
    return None


def _selection_from_results(
    results: list[dict[str, Any]],
    *,
    selected_ids: set[str],
    policy_id: str,
    reason_selected: str,
    reason_rejected: str,
    scores: Mapping[str, float | None] | None = None,
    configuration: Mapping[str, Any] | None = None,
) -> SelectionResult:
    survivors: list[CandidateRef] = []
    rejected: list[CandidateRef] = []
    decisions: list[SelectionDecision] = []
    analysis_refs: list[AnalysisResultRef] = []
    for result in results:
        candidate_ref = _candidate_ref_from_result(result)
        analysis_ref = AnalysisResultRef.from_analysis_result_document(result)
        analysis_refs.append(analysis_ref)
        selected = candidate_ref.candidate_id in selected_ids
        if selected:
            survivors.append(candidate_ref)
        else:
            rejected.append(candidate_ref)
        decisions.append(
            SelectionDecision(
                candidate_id=candidate_ref.candidate_id,
                analysis_result_id=result["analysis_result_id"],
                selected=selected,
                reason=reason_selected if selected else reason_rejected,
                score=(scores or {}).get(result["analysis_result_id"]),
            ),
        )
    return SelectionResult(
        policy_id=policy_id,
        survivor_refs=tuple(survivors),
        rejected_refs=tuple(rejected),
        decisions=tuple(decisions),
        configuration=dict(configuration or {}),
        analysis_result_refs=tuple(analysis_refs),
    )


def _candidate_ref_from_result(result: Mapping[str, Any]) -> CandidateRef:
    ref = result["candidate_ref"]
    return CandidateRef(
        candidate_id=ref["candidate_id"],
        candidate_uri=ref.get("candidate_uri"),
        structural_hash=ref.get("structural_hash"),
    )


__all__ = [
    "Direction",
    "SelectionDecision",
    "SelectionResult",
    "metric_value",
    "select_by_fitness",
]
