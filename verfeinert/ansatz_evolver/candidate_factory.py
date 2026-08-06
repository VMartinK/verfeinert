"""Public candidate-factory boundary for the evolver."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any, Protocol

from .mutation.requests import MutationRequest
from .validation import EvolverValidationError, validate_candidate_document


class CandidateFactory(Protocol):
    """Protocol for producing child Candidate JSON from a mutation request."""

    def __call__(
        self,
        request: MutationRequest,
        parent_candidate: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        """Return a canonical child Candidate JSON document."""


def produce_candidate_from_request(
    request: MutationRequest,
    parent_candidate: Mapping[str, Any],
    factory: CandidateFactory | Callable[[MutationRequest, Mapping[str, Any]], Mapping[str, Any]],
) -> dict[str, Any]:
    """Call a public candidate factory and validate lineage preservation."""
    if not isinstance(request, MutationRequest):
        raise TypeError("request must be a MutationRequest.")
    parent = validate_candidate_document(parent_candidate)
    child = validate_candidate_document(factory(request, parent))
    lineage = child["lineage"]
    if lineage.get("parent_candidate_id") != request.parent_candidate_id:
        raise EvolverValidationError("Child candidate lineage does not reference the mutation parent.")
    if lineage.get("generation") != request.generation_index:
        raise EvolverValidationError("Child candidate lineage generation does not match the request.")
    mutation = lineage.get("mutation", {})
    if not isinstance(mutation, Mapping) or mutation.get("type") != request.mutation_type:
        raise EvolverValidationError("Child candidate mutation provenance does not match the request.")
    return child


__all__ = ["CandidateFactory", "produce_candidate_from_request"]
