"""Evaluation request and result-ingestion boundaries."""

from .requests import AnalysisRequest
from .results import AnalysisIngestionResult, ingest_analysis_results

__all__ = [
    "AnalysisIngestionResult",
    "AnalysisRequest",
    "ingest_analysis_results",
]
