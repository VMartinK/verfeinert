"""Ansatz analysis foundation APIs for Verfeinert."""

from .config import (
    AnalyzerConfig,
    AnalyzerConfigError,
    AnalyzerExecutionPermissions,
    StructuralCostConfig,
)
from .collections import (
    AnalysisResultCollection,
    AnalysisResultCollectionError,
)
from .io import (
    load_candidate_document,
    load_candidate_views,
    write_analysis_result_json,
)
from .models import (
    AnalysisContext,
    AnalysisResultRecord,
    CandidateView,
    ClassificationRecord,
    CostRecord,
    MetricRecord,
    OperationView,
)
from .pareto import (
    ObjectiveSpec,
    ParetoConfig,
    ParetoError,
    compute_pareto_classifications,
    dominates,
    with_pareto_classifications,
)
from .ranking import (
    RankedCandidate,
    RankingConfig,
    RankingError,
    RankingResult,
    rank_analysis_results,
)
from .pipeline import AnalysisPipeline, analyze_and_write, analyze_candidates
from .results import build_analysis_context, build_analysis_result_record
from .validation import (
    AnalyzerValidationError,
    validate_analysis_result_document,
    validate_analyzer_input_document,
    validate_candidate_document,
    validate_staged_package_document,
)

__all__ = [
    "AnalysisContext",
    "AnalysisPipeline",
    "AnalysisResultCollection",
    "AnalysisResultCollectionError",
    "AnalysisResultRecord",
    "AnalyzerConfig",
    "AnalyzerConfigError",
    "AnalyzerExecutionPermissions",
    "AnalyzerValidationError",
    "CandidateView",
    "ClassificationRecord",
    "CostRecord",
    "MetricRecord",
    "ObjectiveSpec",
    "OperationView",
    "ParetoConfig",
    "ParetoError",
    "RankedCandidate",
    "RankingConfig",
    "RankingError",
    "RankingResult",
    "StructuralCostConfig",
    "analyze_and_write",
    "analyze_candidates",
    "build_analysis_context",
    "build_analysis_result_record",
    "compute_pareto_classifications",
    "dominates",
    "load_candidate_document",
    "load_candidate_views",
    "rank_analysis_results",
    "validate_analysis_result_document",
    "validate_analyzer_input_document",
    "validate_candidate_document",
    "validate_staged_package_document",
    "with_pareto_classifications",
    "write_analysis_result_json",
]
