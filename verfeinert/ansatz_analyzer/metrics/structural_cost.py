"""Record-based structural cost for canonical Candidate JSON."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any

from verfeinert.core.io.serialization import to_json_safe

from ..config import STRUCTURAL_COST_COMPONENTS, StructuralCostConfig
from ..models import CandidateView, CostRecord, MetricRecord


@dataclass(frozen=True)
class StructuralFeatures:
    """Structural feature values used by the foundation cost model."""

    candidate_id: str
    parameter_count: int
    depth: int
    two_qubit_operation_count: int
    operation_count: int
    depth_source: str
    warnings: tuple[str, ...] = ()

    def component_values(self) -> dict[str, float]:
        """Return the numeric component payload used by cost normalization."""
        return {
            "parameter_count": float(self.parameter_count),
            "depth": float(self.depth),
            "two_qubit_operation_count": float(self.two_qubit_operation_count),
        }


@dataclass(frozen=True)
class StructuralCostAnalysis:
    """Structural-cost metric and cost records for one candidate."""

    candidate_id: str
    features: StructuralFeatures
    structural_cost: float
    clipped_structural_cost: float
    reference_status: str
    reference_bounds: dict[str, dict[str, float]]
    component_metadata: dict[str, dict[str, float]]
    warnings: tuple[str, ...]
    metric: MetricRecord
    cost: CostRecord


def compute_structural_cost(
    candidate: CandidateView,
    *,
    reference_candidates: tuple[CandidateView, ...] | list[CandidateView] | None = None,
    config: StructuralCostConfig | None = None,
) -> StructuralCostAnalysis:
    """Compute structural cost for one candidate."""
    candidates = tuple(reference_candidates or (candidate,))
    analyses = compute_structural_costs(candidates, config=config)
    for analysis in analyses:
        if analysis.candidate_id == candidate.candidate_id:
            return analysis
    raise ValueError(f"candidate {candidate.candidate_id!r} was not in reference set.")


def compute_structural_costs(
    candidates: tuple[CandidateView, ...] | list[CandidateView],
    *,
    config: StructuralCostConfig | None = None,
) -> list[StructuralCostAnalysis]:
    """Compute structural costs for a deterministic candidate sequence."""
    if not candidates:
        raise ValueError("candidates must not be empty.")
    if any(not isinstance(candidate, CandidateView) for candidate in candidates):
        raise TypeError("candidates must contain CandidateView records.")
    resolved_config = config or StructuralCostConfig()
    feature_rows = [
        _features_for_candidate(candidate, config=resolved_config)
        for candidate in candidates
    ]
    global_warnings: list[str] = []
    reference_bounds = _reference_bounds(
        feature_rows,
        config=resolved_config,
        warnings=global_warnings,
    )
    analyses: list[StructuralCostAnalysis] = []
    for features in feature_rows:
        analyses.append(
            _analyze_features(
                features,
                config=resolved_config,
                reference_bounds=reference_bounds,
                global_warnings=global_warnings,
            ),
        )
    return analyses


def _features_for_candidate(
    candidate: CandidateView,
    *,
    config: StructuralCostConfig,
) -> StructuralFeatures:
    warnings: list[str] = []
    declared_depth = candidate.declared_depth
    if declared_depth is None:
        if not config.allow_operation_count_as_depth_proxy:
            raise ValueError(
                "Candidate does not declare metadata.structural.depth and "
                "operation-count depth proxy is disabled.",
            )
        depth = candidate.operation_count
        depth_source = "operation_count_proxy"
        warnings.append(
            "Depth was not available; using operation_count as a depth proxy.",
        )
    else:
        depth = declared_depth
        depth_source = "metadata.structural.depth"
    return StructuralFeatures(
        candidate_id=candidate.candidate_id,
        parameter_count=candidate.parameter_count,
        depth=depth,
        two_qubit_operation_count=candidate.two_qubit_operation_count,
        operation_count=candidate.operation_count,
        depth_source=depth_source,
        warnings=tuple(warnings),
    )


def _reference_bounds(
    feature_rows: list[StructuralFeatures],
    *,
    config: StructuralCostConfig,
    warnings: list[str],
) -> dict[str, dict[str, float]]:
    if config.reference_bounds is not None:
        return {
            component: dict(bounds)
            for component, bounds in config.reference_bounds.items()
        }
    warnings.append("Reference bounds were derived from the selected candidates.")
    values_by_component = {
        component: [features.component_values()[component] for features in feature_rows]
        for component in STRUCTURAL_COST_COMPONENTS
    }
    return {
        component: {
            "min": float(min(values)),
            "max": float(max(values)),
        }
        for component, values in values_by_component.items()
    }


def _analyze_features(
    features: StructuralFeatures,
    *,
    config: StructuralCostConfig,
    reference_bounds: dict[str, dict[str, float]],
    global_warnings: list[str],
) -> StructuralCostAnalysis:
    warnings = [*global_warnings, *features.warnings]
    component_values = features.component_values()
    component_metadata: dict[str, dict[str, float]] = {}
    weighted_sum = 0.0
    weight_sum = float(sum(config.component_weights.values()))
    for component in STRUCTURAL_COST_COMPONENTS:
        bounds = reference_bounds[component]
        normalized = _normalize_component(
            component_values[component],
            lower=bounds["min"],
            upper=bounds["max"],
            component=component,
            warnings=warnings,
        )
        weight = float(config.component_weights[component])
        component_metadata[component] = {
            "value": component_values[component],
            "normalized": normalized,
            "weight": weight,
            "min": bounds["min"],
            "max": bounds["max"],
        }
        weighted_sum += normalized * weight
    structural_cost = weighted_sum / weight_sum
    clipped = min(1.0, max(0.0, structural_cost))
    status = _reference_status(component_values, reference_bounds)
    metadata = {
        "cost_model": "reference_normalized_structural_cost",
        "reference_id": config.reference_id,
        "definition": (
            "weighted average of reference-normalized parameter_count, depth, "
            "and two_qubit_operation_count"
        ),
        "depth_source": features.depth_source,
        "component_weights": dict(config.component_weights),
        "components": component_metadata,
        "reference_bounds": reference_bounds,
        "cost_reference_status": status,
        "structural_cost_clipped": clipped,
        "warnings": warnings,
        "qnodes_executed": False,
        "expensive_metrics_executed": False,
    }
    metric = MetricRecord(
        metric_id=f"metric-structural-cost-{features.candidate_id}",
        name="structural_cost",
        status="computed",
        value=structural_cost,
        metadata={
            "source": "cost.structural_cost",
            "warnings": list(warnings),
            "qnodes_executed": False,
            "expensive_metric": False,
        },
    )
    cost = CostRecord(
        structural_cost=structural_cost,
        operation_count=features.operation_count,
        two_qubit_operation_count=features.two_qubit_operation_count,
        parameter_count=features.parameter_count,
        metadata=metadata,
    )
    return StructuralCostAnalysis(
        candidate_id=features.candidate_id,
        features=features,
        structural_cost=structural_cost,
        clipped_structural_cost=clipped,
        reference_status=status,
        reference_bounds=to_json_safe(reference_bounds),
        component_metadata=to_json_safe(component_metadata),
        warnings=tuple(warnings),
        metric=metric,
        cost=cost,
    )


def _normalize_component(
    value: float,
    *,
    lower: float,
    upper: float,
    component: str,
    warnings: list[str],
) -> float:
    if not all(math.isfinite(item) for item in (value, lower, upper)):
        raise ValueError(f"Invalid structural-cost bounds for {component}.")
    if math.isclose(upper - lower, 0.0):
        warnings.append(
            f"Reference bounds for {component} have zero width; "
            "normalized value set to 0.0.",
        )
        return 0.0
    return (value - lower) / (upper - lower)


def _reference_status(
    values: dict[str, float],
    bounds: dict[str, dict[str, float]],
) -> str:
    below = any(values[component] < bounds[component]["min"] for component in values)
    above = any(values[component] > bounds[component]["max"] for component in values)
    if below and above:
        return "mixed_outside_reference_range"
    if below:
        return "below_reference_range"
    if above:
        return "above_reference_range"
    return "within_reference_range"


__all__ = [
    "StructuralCostAnalysis",
    "StructuralFeatures",
    "compute_structural_cost",
    "compute_structural_costs",
]
