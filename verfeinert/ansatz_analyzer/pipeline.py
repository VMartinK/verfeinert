"""Minimal analyzer foundation pipeline."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .config import AnalyzerConfig
from .io import load_candidate_views, write_analysis_result_json
from .materialization import CircuitMaterializationError, MaterializedCircuit, StateCallableProvider
from .metrics.runtime import failed_metric, skipped_metric
from .metrics.structural_cost import compute_structural_costs
from .models import AnalysisResultRecord, CandidateView, CostRecord, MetricRecord
from .results import build_analysis_context, build_analysis_result_record
from .validation import validate_analysis_result_document


class AnalysisPipeline:
    """Structural-cost-only pipeline over canonical Candidate JSON."""

    def __init__(self, config: AnalyzerConfig):
        if not isinstance(config, AnalyzerConfig):
            raise TypeError("config must be an AnalyzerConfig.")
        self.config = config

    def run(
        self,
        source,
        *,
        metric_callables: Mapping[str, Any] | None = None,
    ) -> list[AnalysisResultRecord]:
        """Analyze Candidate or StagedPackage JSON and return result records."""
        candidates = load_candidate_views(source)
        context = build_analysis_context(self.config)
        structural_by_candidate = {}
        if "structural_cost" in self.config.selected_metrics:
            structural_by_candidate = {
                result.candidate_id: result
                for result in compute_structural_costs(
                    candidates,
                    config=self.config.structural_cost,
                )
            }
        metric_runtime_state: dict[str, Any] = {}
        state_callable_provider = StateCallableProvider(self.config.materialization)
        records = []
        for candidate in candidates:
            metrics: list[MetricRecord] = []
            cost = CostRecord()
            structural = structural_by_candidate.get(candidate.candidate_id)
            if structural is not None:
                metrics.append(structural.metric)
                cost = structural.cost
            metrics.extend(
                self._optional_metric_records(
                    candidate,
                    metric_callables=metric_callables or {},
                    metric_runtime_state=metric_runtime_state,
                    state_callable_provider=state_callable_provider,
                ),
            )
            records.append(
                build_analysis_result_record(
                    candidate=candidate,
                    context=context,
                    metrics=tuple(metrics),
                    cost=cost,
                    metadata={
                        "foundation_slice": True,
                        "derived_analyses": [
                            "pareto_front",
                            "ranking",
                        ],
                        "candidate_semantics": _candidate_semantics(candidate),
                    },
                    execution_flags=_execution_flags(metrics),
                ),
            )
        for record in records:
            validate_analysis_result_document(record.to_dict())
        return records

    def run_and_write(
        self,
        source,
        *,
        metric_callables: Mapping[str, Any] | None = None,
    ) -> list[Path]:
        """Analyze a source and write one AnalysisResult JSON per candidate."""
        return [
            write_analysis_result_json(record, self.config)
            for record in self.run(source, metric_callables=metric_callables)
        ]

    def _optional_metric_records(
        self,
        candidate: CandidateView,
        *,
        metric_callables: Mapping[str, Any],
        metric_runtime_state: dict[str, Any],
        state_callable_provider: StateCallableProvider,
    ) -> list[MetricRecord]:
        records: list[MetricRecord] = []
        if "expressibility" in self.config.selected_metrics:
            resolution = self._state_callable_resolution(
                "expressibility",
                candidate,
                metric_callables,
                state_callable_provider,
            )
            if resolution.skip_reason is not None:
                records.append(_skipped_optional_metric("expressibility", candidate, resolution))
            elif resolution.error is not None:
                records.append(_failed_optional_metric("expressibility", candidate, resolution))
            else:
                from .metrics.expressibility import (
                    ExpressibilityConfig,
                    compute_expressibility_metric,
                    shared_rng as shared_expressibility_rng,
                )

                metric_config = ExpressibilityConfig.from_mapping(
                    _metric_config(self.config, "expressibility", resolution=resolution),
                )
                rng = None
                if metric_config.rng_policy == "global_sequential":
                    rng = metric_runtime_state.setdefault(
                        "expressibility_rng",
                        shared_expressibility_rng(metric_config),
                    )
                records.append(
                    _with_resolution_metadata(
                        compute_expressibility_metric(
                            candidate,
                            resolution.state_callable,
                            config=metric_config,
                            permissions=self.config.permissions,
                            rng=rng,
                        ),
                        resolution,
                    ),
                )
        if "trainability" in self.config.selected_metrics:
            resolution = self._state_callable_resolution(
                "trainability",
                candidate,
                metric_callables,
                state_callable_provider,
            )
            if resolution.skip_reason is not None:
                records.append(_skipped_optional_metric("trainability", candidate, resolution))
            elif resolution.error is not None:
                records.append(_failed_optional_metric("trainability", candidate, resolution))
            else:
                from .metrics.trainability import (
                    TrainabilityConfig,
                    compute_trainability_metric,
                    shared_rng as shared_trainability_rng,
                )

                metric_config = TrainabilityConfig.from_mapping(
                    _metric_config(self.config, "trainability", resolution=resolution),
                )
                rng = None
                if metric_config.rng_policy == "global_sequential":
                    rng = metric_runtime_state.setdefault(
                        "trainability_rng",
                        shared_trainability_rng(metric_config),
                    )
                records.append(
                    _with_resolution_metadata(
                        compute_trainability_metric(
                            candidate,
                            resolution.state_callable,
                            config=metric_config,
                            permissions=self.config.permissions,
                            rng=rng,
                        ),
                        resolution,
                    ),
                )
        return records

    def _state_callable_resolution(
        self,
        metric_name: str,
        candidate: CandidateView,
        metric_callables: Mapping[str, Any],
        state_callable_provider: StateCallableProvider,
    ) -> "_StateCallableResolution":
        explicit = _callable_for_metric(
            metric_name,
            candidate.candidate_id,
            metric_callables,
        )
        if explicit is not None:
            return _StateCallableResolution(
                state_callable=explicit,
                source="explicit",
                metadata={
                    "state_callable_source": "explicit",
                    "automatic_materialization_used": False,
                    "materialization_enabled": self.config.materialization.enabled,
                },
            )
        if not self.config.materialization.enabled:
            return _StateCallableResolution(
                source="unavailable",
                skip_reason="no state callable provided",
                metadata={
                    "state_callable_source": "unavailable",
                    "materialization_enabled": False,
                    "automatic_materialization_used": False,
                },
            )
        if not self.config.permissions.allow_qnode_execution:
            return _StateCallableResolution(
                source="automatic_materialization",
                skip_reason="permissions.allow_qnode_execution is false",
                metadata={
                    "state_callable_source": "automatic_materialization",
                    "execution_boundary": "permission_denied",
                    "materialization_enabled": True,
                    "automatic_materialization_used": False,
                    "qnodes_executed": False,
                },
            )
        try:
            materialized = state_callable_provider.materialize(candidate)
        except CircuitMaterializationError as exc:
            return _StateCallableResolution(
                source="automatic_materialization",
                error=str(exc),
                metadata={
                    "state_callable_source": "automatic_materialization",
                    "materialization_enabled": True,
                    "automatic_materialization_used": False,
                    "materialization_error": str(exc),
                    "qnodes_executed": False,
                },
            )
        return _StateCallableResolution(
            state_callable=materialized.state_callable,
            source="automatic_materialization",
            materialized=materialized,
            metadata={
                "state_callable_source": "automatic_materialization",
                "materialization_enabled": True,
                "automatic_materialization_used": True,
                "materialization": materialized.to_metadata(),
            },
        )


@dataclass(frozen=True)
class _StateCallableResolution:
    state_callable: Any | None = None
    source: str = "unavailable"
    materialized: MaterializedCircuit | None = None
    skip_reason: str | None = None
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def uses_automatic_materialization(self) -> bool:
        return self.materialized is not None


def _skipped_optional_metric(
    metric_name: str,
    candidate: CandidateView,
    resolution: _StateCallableResolution,
) -> MetricRecord:
    return skipped_metric(
        metric_name=metric_name,
        candidate_id=candidate.candidate_id,
        reason=resolution.skip_reason or "state callable unavailable",
        metadata=resolution.metadata,
    )


def _failed_optional_metric(
    metric_name: str,
    candidate: CandidateView,
    resolution: _StateCallableResolution,
) -> MetricRecord:
    return failed_metric(
        metric_name=metric_name,
        candidate_id=candidate.candidate_id,
        error=resolution.error or "state callable materialization failed",
        metadata={
            "execution_boundary": "materialization",
            **resolution.metadata,
        },
    )


def _with_resolution_metadata(
    metric: MetricRecord,
    resolution: _StateCallableResolution,
) -> MetricRecord:
    metadata = {
        **metric.metadata,
        **resolution.metadata,
    }
    if resolution.uses_automatic_materialization:
        metadata["materialized_callable_executed"] = metric.status == "computed"
    return MetricRecord(
        metric_id=metric.metric_id,
        name=metric.name,
        status=metric.status,
        value=metric.value,
        units=metric.units,
        error=metric.error,
        metadata=metadata,
    )


def _candidate_semantics(candidate: CandidateView) -> dict[str, Any]:
    """Propagate structured semantics without duplicating candidate identity."""
    lineage = dict(candidate.lineage)
    metadata = dict(candidate.metadata)
    mutation = lineage.get("mutation")
    payload: dict[str, Any] = {
        "lineage": {
            "generation": lineage.get("generation"),
            "root_candidate_id": lineage.get("root_candidate_id"),
            "parent_candidate_id": lineage.get("parent_candidate_id"),
        },
    }
    if isinstance(mutation, Mapping):
        payload["mutation"] = {
            key: mutation.get(key)
            for key in ("mutation_id", "type", "source_candidate_id", "operation")
            if mutation.get(key) is not None
        }
        if isinstance(mutation.get("parameters"), Mapping):
            payload["mutation"]["parameters"] = dict(mutation["parameters"])
        if isinstance(mutation.get("metadata"), Mapping):
            payload["mutation"]["metadata"] = dict(mutation["metadata"])
    source_context = {
        key: metadata.get(key)
        for key in (
            "template_id",
            "ansatz_id",
            "layer",
            "recipe_id",
            "source_backend_name",
            "workflow_run_id",
        )
        if metadata.get(key) is not None
    }
    if source_context:
        payload["source_context"] = source_context
    return payload


def analyze_candidates(
    source,
    config: AnalyzerConfig,
    *,
    metric_callables: Mapping[str, Any] | None = None,
) -> list[AnalysisResultRecord]:
    """Convenience wrapper for the minimal analyzer foundation pipeline."""
    return AnalysisPipeline(config).run(source, metric_callables=metric_callables)


def analyze_and_write(
    source,
    config: AnalyzerConfig,
    *,
    metric_callables: Mapping[str, Any] | None = None,
) -> list[Path]:
    """Analyze and write canonical AnalysisResult JSON documents."""
    return AnalysisPipeline(config).run_and_write(source, metric_callables=metric_callables)


def _metric_config(
    config: AnalyzerConfig,
    metric_name: str,
    *,
    resolution: _StateCallableResolution,
) -> dict[str, Any]:
    value = config.metric_configs.get(metric_name, {})
    payload = dict(value) if isinstance(value, Mapping) else {}
    if resolution.materialized is not None:
        payload["backend_label"] = resolution.materialized.backend_label
        payload["requires_qnode_execution"] = True
    return payload


def _callable_for_metric(
    metric_name: str,
    candidate_id: str,
    metric_callables: Mapping[str, Any],
):
    nested = metric_callables.get(metric_name)
    if isinstance(nested, Mapping):
        return nested.get(candidate_id)
    return metric_callables.get(candidate_id)


def _execution_flags(metrics: list[MetricRecord]) -> dict[str, bool]:
    return {
        "qnodes_executed": any(
            bool(metric.metadata.get("qnodes_executed"))
            for metric in metrics
        ),
        "expensive_metrics_executed": any(
            metric.status == "computed"
            and bool(metric.metadata.get("expensive_metric"))
            for metric in metrics
        ),
        "automatic_materialization_used": any(
            bool(metric.metadata.get("automatic_materialization_used"))
            for metric in metrics
        ),
        "materialized_callables_executed": any(
            bool(metric.metadata.get("materialized_callable_executed"))
            for metric in metrics
        ),
    }


__all__ = [
    "AnalysisPipeline",
    "analyze_and_write",
    "analyze_candidates",
]
