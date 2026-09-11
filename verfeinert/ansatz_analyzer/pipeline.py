"""Minimal analyzer foundation pipeline."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from verfeinert.core.execution import ExecutionError, build_executor

from .config import AnalyzerConfig, AnalyzerConfigError, EXPENSIVE_METRICS
from .io import load_candidate_views, write_analysis_result_json
from .materialization import CircuitMaterializationError, MaterializedCircuit, StateCallableProvider
from .metrics.runtime import failed_metric, skipped_metric
from .metrics.structural_cost import StructuralCostAnalysis, compute_structural_costs
from .models import AnalysisContext, AnalysisResultRecord, CandidateView, CostRecord, MetricRecord
from .results import build_analysis_context, build_analysis_result_record
from .validation import validate_analysis_result_document


class AnalysisPipelineExecutionError(RuntimeError):
    """Raised when analyzer execution cannot complete truthfully."""

    def __init__(
        self,
        message: str,
        *,
        reason: str,
        execution: Mapping[str, Any],
        failures: tuple[dict[str, Any], ...] = (),
        error: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.reason = reason
        self.execution = dict(execution)
        self.failures = failures
        self.error = dict(error or {})

    def to_dict(self) -> dict[str, Any]:
        """Return JSON-safe failure metadata without traceback internals."""
        return {
            "reason": self.reason,
            "execution": dict(self.execution),
            "failures": list(self.failures),
            "error": dict(self.error),
        }


class AnalysisPipeline:
    """Analyzer pipeline over canonical Candidate JSON with optional scientific metrics."""

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
        _validate_parallel_execution_contract(self.config)
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
        metric_callables = {} if metric_callables is None else metric_callables
        if self.config.execution.mode == "multiprocessing":
            records = self._run_parallel_candidates(
                candidates,
                context=context,
                structural_by_candidate=structural_by_candidate,
                metric_callables=metric_callables,
            )
            for record in records:
                validate_analysis_result_document(record.to_dict())
            return records

        metric_runtime_state: dict[str, Any] = {}
        state_callable_provider = StateCallableProvider(self.config.materialization)
        records = []
        for candidate in candidates:
            records.append(
                _analyze_candidate_record(
                    config=self.config,
                    context=context,
                    candidate=candidate,
                    structural=structural_by_candidate.get(candidate.candidate_id),
                    metric_callables=metric_callables,
                    metric_runtime_state=metric_runtime_state,
                    state_callable_provider=state_callable_provider,
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
                            materialized=resolution.materialized,
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
                            materialized=resolution.materialized,
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
                    "materialization_error_reason": exc.reason,
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

    def _run_parallel_candidates(
        self,
        candidates: tuple[CandidateView, ...] | list[CandidateView],
        *,
        context: AnalysisContext,
        structural_by_candidate: Mapping[str, StructuralCostAnalysis],
        metric_callables: Mapping[str, Any],
    ) -> list[AnalysisResultRecord]:
        executor = build_executor(self.config.execution)
        work_items = [
            _CandidateAnalysisWorkItem(
                config=self.config,
                context=context,
                candidate=candidate,
                structural=structural_by_candidate.get(candidate.candidate_id),
                metric_callables=metric_callables,
            )
            for candidate in candidates
        ]
        try:
            outputs = executor.map(_analyze_candidate_work_item, work_items)
        except ExecutionError as exc:
            raise AnalysisPipelineExecutionError(
                "analyzer multiprocessing failed without sequential fallback: "
                f"{exc.error_type or type(exc).__name__}: {exc.error_message or exc}",
                reason=exc.reason,
                execution=self.config.execution.to_dict(),
                error=exc.to_dict(),
            ) from exc

        failures = tuple(
            output.to_dict()
            for output in outputs
            if isinstance(output, _CandidateAnalysisFailure)
        )
        if failures:
            first = failures[0]
            raise AnalysisPipelineExecutionError(
                "analyzer candidate worker failed without sequential fallback: "
                f"candidate_id={first['candidate_id']!r}, "
                f"{first['error_type']}: {first['error_message']}",
                reason="candidate_worker_failed",
                execution=self.config.execution.to_dict(),
                failures=failures,
            )
        records: list[AnalysisResultRecord] = []
        for output in outputs:
            if not isinstance(output, AnalysisResultRecord):
                raise AnalysisPipelineExecutionError(
                    "analyzer worker returned an unsupported payload without "
                    "sequential fallback.",
                    reason="unsupported_worker_result",
                    execution=self.config.execution.to_dict(),
                    error={"payload_type": type(output).__name__},
                )
            records.append(output)
        return records


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


@dataclass(frozen=True)
class _CandidateAnalysisWorkItem:
    config: AnalyzerConfig
    context: AnalysisContext
    candidate: CandidateView
    structural: StructuralCostAnalysis | None
    metric_callables: Mapping[str, Any]


@dataclass(frozen=True)
class _CandidateAnalysisFailure:
    candidate_id: str
    error_type: str
    error_message: str
    reason: str = "candidate_worker_failed"

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "reason": self.reason,
            "error_type": self.error_type,
            "error_message": self.error_message,
        }


def _analyze_candidate_work_item(
    item: _CandidateAnalysisWorkItem,
) -> AnalysisResultRecord | _CandidateAnalysisFailure:
    try:
        return _analyze_candidate_record(
            config=item.config,
            context=item.context,
            candidate=item.candidate,
            structural=item.structural,
            metric_callables=item.metric_callables,
            metric_runtime_state={},
            state_callable_provider=StateCallableProvider(item.config.materialization),
        )
    except Exception as exc:
        return _CandidateAnalysisFailure(
            candidate_id=item.candidate.candidate_id,
            error_type=type(exc).__name__,
            error_message=str(exc),
        )


def _analyze_candidate_record(
    *,
    config: AnalyzerConfig,
    context: AnalysisContext,
    candidate: CandidateView,
    structural: StructuralCostAnalysis | None,
    metric_callables: Mapping[str, Any],
    metric_runtime_state: dict[str, Any],
    state_callable_provider: StateCallableProvider,
) -> AnalysisResultRecord:
    metrics: list[MetricRecord] = []
    cost = CostRecord()
    if structural is not None:
        metrics.append(structural.metric)
        cost = structural.cost
    metrics.extend(
        AnalysisPipeline(config)._optional_metric_records(
            candidate,
            metric_callables=metric_callables,
            metric_runtime_state=metric_runtime_state,
            state_callable_provider=state_callable_provider,
        ),
    )
    return build_analysis_result_record(
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
    )


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


def _validate_parallel_execution_contract(config: AnalyzerConfig) -> None:
    if config.execution.mode != "multiprocessing":
        return
    for metric_name in config.selected_metrics:
        if metric_name not in EXPENSIVE_METRICS:
            continue
        value = config.metric_configs.get(metric_name, {})
        payload = dict(value) if isinstance(value, Mapping) else {}
        if payload.get("rng_policy", "per_circuit") == "global_sequential":
            raise AnalyzerConfigError(
                "execution.mode='multiprocessing' cannot honor "
                f"{metric_name}.rng_policy='global_sequential'; use "
                "rng_policy='per_circuit' or execution.mode='sequential'.",
            )


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
    "AnalysisPipelineExecutionError",
    "analyze_and_write",
    "analyze_candidates",
]
