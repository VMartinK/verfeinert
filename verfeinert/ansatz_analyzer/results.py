"""Assembly helpers for canonical AnalysisResult documents."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from verfeinert import __version__
from verfeinert.core.metadata import current_git_commit

from .config import AnalyzerConfig
from .models import AnalysisContext, AnalysisResultRecord, CandidateView


def build_analysis_context(
    config: AnalyzerConfig,
    *,
    created_at: str | None = None,
    git_commit: str | None = None,
) -> AnalysisContext:
    """Build a run context for AnalysisResult provenance."""
    timestamp = created_at or datetime.now(timezone.utc).isoformat()
    return AnalysisContext(
        run_id=config.run_id,
        selected_metrics=tuple(config.selected_metrics),
        config_snapshot=config.to_dict(),
        permissions=config.permissions.to_dict(),
        execution=config.execution.to_dict(),
        random_seed=config.random_seed,
        created_at=timestamp,
        git_commit=current_git_commit() if git_commit is None else git_commit,
    )


def build_analysis_result_record(
    *,
    candidate: CandidateView,
    context: AnalysisContext,
    metrics,
    cost,
    classifications=(),
    metadata: dict[str, Any] | None = None,
    execution_flags: dict[str, bool] | None = None,
) -> AnalysisResultRecord:
    """Assemble a canonical AnalysisResult record for one candidate."""
    flags = {
        "qnodes_executed": False,
        "generated_callables_executed": False,
        "notebooks_executed": False,
        "expensive_metrics_executed": False,
        "plots_generated": False,
        "automatic_materialization_used": False,
        "materialized_callables_executed": False,
    }
    flags.update(execution_flags or {})
    provenance = {
        "created_at": context.created_at,
        "analyzer": "verfeinert.ansatz_analyzer",
        "software_version": __version__,
        "git_commit": context.git_commit,
        "execution": {
            "run_id": context.run_id,
            "execution_mode": context.execution.get("mode"),
            "worker_count": context.execution.get("worker_count"),
            "selected_metrics": list(context.selected_metrics),
            "random_seed": context.random_seed,
            "permissions": dict(context.permissions),
            **flags,
            "config": dict(context.config_snapshot),
        },
    }
    return AnalysisResultRecord(
        analysis_result_id=_analysis_result_id(context.run_id, candidate.candidate_id),
        candidate_ref=candidate.to_candidate_ref(),
        metrics=tuple(metrics),
        cost=cost,
        classifications=tuple(classifications),
        provenance=provenance,
        metadata=metadata or {},
    )


def _analysis_result_id(run_id: str, candidate_id: str) -> str:
    return f"analysis-{run_id}-{candidate_id}"


__all__ = [
    "build_analysis_context",
    "build_analysis_result_record",
]
