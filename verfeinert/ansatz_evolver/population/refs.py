"""Candidate reference helpers for populations."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..models import CandidateRef
from ..validation import validate_candidate_document


def candidate_ref_from_document(
    document: Mapping[str, Any],
    *,
    candidate_uri: str | None = None,
    role: str | None = None,
    status: str | None = None,
) -> CandidateRef:
    """Validate a Candidate JSON document and return its reference."""
    candidate = validate_candidate_document(document)
    return CandidateRef.from_candidate_document(
        candidate,
        candidate_uri=candidate_uri,
        role=role,
        status=status,
    )


__all__ = ["candidate_ref_from_document"]
