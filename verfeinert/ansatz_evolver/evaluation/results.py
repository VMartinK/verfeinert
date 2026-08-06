"""AnalysisResult ingestion for evolver selection."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from verfeinert.core.hashing import stable_hash

from ..models import AnalysisResultRef, CandidateRef
from ..validation import validate_analysis_result_document


@dataclass(frozen=True)
class AnalysisIngestionResult:
    """Result of linking AnalysisResult JSON documents to candidate refs."""

    analysis_result_refs: tuple[AnalysisResultRef, ...]
    linked_candidate_ids: tuple[str, ...]
    missing_candidate_ids: tuple[str, ...]
    unexpected_candidate_ids: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        """Return JSON-safe ingestion audit data."""
        return {
            "analysis_result_refs": [ref.to_ref_dict() for ref in self.analysis_result_refs],
            "linked_candidate_ids": list(self.linked_candidate_ids),
            "missing_candidate_ids": list(self.missing_candidate_ids),
            "unexpected_candidate_ids": list(self.unexpected_candidate_ids),
        }


def ingest_analysis_results(
    candidate_refs: Iterable[CandidateRef],
    analysis_results: Iterable[Mapping[str, Any]],
    *,
    uri_by_analysis_result_id: Mapping[str, str] | None = None,
) -> AnalysisIngestionResult:
    """Validate AnalysisResult JSON and link each result to a known candidate ID."""
    candidates = tuple(candidate_refs)
    if any(not isinstance(ref, CandidateRef) for ref in candidates):
        raise ValueError("candidate_refs must contain CandidateRef records.")
    candidate_ids = tuple(ref.candidate_id for ref in candidates)
    known = set(candidate_ids)
    uris = dict(uri_by_analysis_result_id or {})

    refs: list[AnalysisResultRef] = []
    linked: list[str] = []
    unexpected: list[str] = []
    for document in analysis_results:
        result = validate_analysis_result_document(document)
        result_id = result["analysis_result_id"]
        candidate_id = result["candidate_ref"]["candidate_id"]
        if candidate_id in known:
            linked.append(candidate_id)
        else:
            unexpected.append(candidate_id)
        refs.append(
            AnalysisResultRef.from_analysis_result_document(
                result,
                analysis_result_uri=uris.get(result_id),
                hash=stable_hash(result),
                metadata={"ingested_by": "verfeinert.ansatz_evolver"},
            ),
        )
    missing = tuple(candidate_id for candidate_id in candidate_ids if candidate_id not in linked)
    return AnalysisIngestionResult(
        analysis_result_refs=tuple(refs),
        linked_candidate_ids=tuple(linked),
        missing_candidate_ids=missing,
        unexpected_candidate_ids=tuple(unexpected),
    )


__all__ = ["AnalysisIngestionResult", "ingest_analysis_results"]
