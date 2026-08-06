"""Deterministic identifiers for mutation requests."""

from __future__ import annotations

from ..models import require_identifier


def build_mutation_request_id(
    *,
    parent_candidate_id: str,
    generation_index: int,
    mutation_type: str,
    variant_index: int,
) -> str:
    """Build a stable mutation request identifier."""
    parent = require_identifier(parent_candidate_id, "parent_candidate_id")
    mutation = require_identifier(mutation_type.lower(), "mutation_type")
    if generation_index < 0:
        raise ValueError("generation_index must be non-negative.")
    if variant_index < 0:
        raise ValueError("variant_index must be non-negative.")
    return f"{parent}:g{generation_index:04d}:{mutation}:v{variant_index:04d}"


__all__ = ["build_mutation_request_id"]
