"""Minimal analyzer foundation pipeline."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .config import AnalyzerConfig
from .io import load_candidate_views, write_analysis_result_json
from .metrics.runtime import skipped_metric
from .metrics.structural_cost import compute_structural_costs
from .models import AnalysisResultRecord, CostRecord, MetricRecord
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
        candidate,
        *,
        metric_callables: Mapping[str, Any],
        metric_runtime_state: dict[str, Any],
    ) -> list[MetricRecord]:
        records: list[MetricRecord] = []
        if "expressibility" in self.config.selected_metrics:
            state_callable = _callable_for_metric(
                "expressibility",
                candidate.candidate_id,
                metric_callables,
            )
            if state_callable is None:
                records.append(
                    skipped_metric(
                        metric_name="expressibility",
                        candidate_id=candidate.candidate_id,
                        reason="no state callable provided",
                    ),
                )
            else:
                from .metrics.expressibility import (
                    ExpressibilityConfig,
                    compute_expressibility_metric,
                    shared_rng as shared_expressibility_rng,
                )

                metric_config = ExpressibilityConfig.from_mapping(
                    _metric_config(self.config, "expressibility"),
                )
                rng = None
                if metric_config.rng_policy == "global_sequential":
                    rng = metric_runtime_state.setdefault(
                        "expressibility_rng",
                        shared_expressibility_rng(metric_config),
                    )
                records.append(
                    compute_expressibility_metric(
                        candidate,
                        state_callable,
                        config=metric_config,
                        permissions=self.config.permissions,
                        rng=rng,
                    ),
                )
        if "trainability" in self.config.selected_metrics:
            state_callable = _callable_for_metric(
                "trainability",
                candidate.candidate_id,
                metric_callables,
            )
            if state_callable is None:
                records.append(
                    skipped_metric(
                        metric_name="trainability",
                        candidate_id=candidate.candidate_id,
                        reason="no state callable provided",
                    ),
                )
            else:
                from .metrics.trainability import (
                    TrainabilityConfig,
                    compute_trainability_metric,
                    shared_rng as shared_trainability_rng,
                )

                metric_config = TrainabilityConfig.from_mapping(
                    _metric_config(self.config, "trainability"),
                )
                rng = None
                if metric_config.rng_policy == "global_sequential":
                    rng = metric_runtime_state.setdefault(
                        "trainability_rng",
                        shared_trainability_rng(metric_config),
                    )
                records.append(
                    compute_trainability_metric(
                        candidate,
                        state_callable,
                        config=metric_config,
                        permissions=self.config.permissions,
                        rng=rng,
                    ),
                )
        return records


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


def _metric_config(config: AnalyzerConfig, metric_name: str) -> dict[str, Any]:
    value = config.metric_configs.get(metric_name, {})
    return dict(value) if isinstance(value, Mapping) else {}


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
    }


__all__ = [
    "AnalysisPipeline",
    "analyze_and_write",
    "analyze_candidates",
]
