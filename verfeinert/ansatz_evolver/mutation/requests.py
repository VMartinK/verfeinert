"""Mutation request records produced by evolver policies."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..models import CandidateRef, require_identifier, require_mapping, require_non_negative_int
from .ids import build_mutation_request_id
from .policies import MutationPolicy


@dataclass(frozen=True)
class MutationRequest:
    """Intent to produce a child Candidate JSON from a parent Candidate JSON."""

    request_id: str
    parent_candidate_id: str
    generation_index: int
    mutation_type: str
    policy_id: str
    recipe_id: str
    variant_index: int
    parent_candidate_uri: str | None = None
    root_candidate_id: str | None = None
    parameters: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "request_id", require_identifier(self.request_id, "request_id"))
        object.__setattr__(
            self,
            "parent_candidate_id",
            require_identifier(self.parent_candidate_id, "parent_candidate_id"),
        )
        object.__setattr__(
            self,
            "generation_index",
            require_non_negative_int(self.generation_index, "generation_index"),
        )
        object.__setattr__(self, "mutation_type", require_identifier(self.mutation_type, "mutation_type"))
        object.__setattr__(self, "policy_id", require_identifier(self.policy_id, "policy_id"))
        object.__setattr__(self, "recipe_id", require_identifier(self.recipe_id, "recipe_id"))
        object.__setattr__(
            self,
            "variant_index",
            require_non_negative_int(self.variant_index, "variant_index"),
        )
        if self.root_candidate_id is not None:
            object.__setattr__(
                self,
                "root_candidate_id",
                require_identifier(self.root_candidate_id, "root_candidate_id"),
            )
        object.__setattr__(self, "parameters", require_mapping(self.parameters, "parameters"))
        object.__setattr__(self, "metadata", require_mapping(self.metadata, "metadata"))

    def to_dict(self) -> dict[str, Any]:
        """Return JSON-safe mutation request data."""
        payload: dict[str, Any] = {
            "request_id": self.request_id,
            "parent_candidate_id": self.parent_candidate_id,
            "generation_index": self.generation_index,
            "mutation_type": self.mutation_type,
            "policy_id": self.policy_id,
            "recipe_id": self.recipe_id,
            "variant_index": self.variant_index,
            "parameters": dict(self.parameters),
            "metadata": dict(self.metadata),
        }
        if self.parent_candidate_uri is not None:
            payload["parent_candidate_uri"] = self.parent_candidate_uri
        if self.root_candidate_id is not None:
            payload["root_candidate_id"] = self.root_candidate_id
        return payload


def build_mutation_requests(
    parent_refs: tuple[CandidateRef, ...] | list[CandidateRef],
    *,
    generation_index: int,
    policy: MutationPolicy,
) -> tuple[MutationRequest, ...]:
    """Build deterministic mutation requests without editing circuits."""
    generation = require_non_negative_int(generation_index, "generation_index")
    if not isinstance(policy, MutationPolicy):
        raise ValueError("policy must be a MutationPolicy.")
    requests: list[MutationRequest] = []
    parents = tuple(parent_refs)
    for parent_index, parent in enumerate(parents):
        if not isinstance(parent, CandidateRef):
            raise ValueError("parent_refs must contain CandidateRef records.")
        for variant_index in range(policy.variants_per_parent):
            recipe = policy.recipe_for_variant(variant_index)
            request_id = build_mutation_request_id(
                parent_candidate_id=parent.candidate_id,
                generation_index=generation,
                mutation_type=recipe.mutation_type,
                variant_index=variant_index,
            )
            requests.append(
                MutationRequest(
                    request_id=request_id,
                    parent_candidate_id=parent.candidate_id,
                    parent_candidate_uri=parent.candidate_uri,
                    root_candidate_id=parent.metadata.get("root_candidate_id"),
                    generation_index=generation,
                    mutation_type=recipe.mutation_type,
                    policy_id=policy.policy_id,
                    recipe_id=recipe.recipe_id,
                    variant_index=variant_index,
                    parameters=dict(recipe.parameters),
                    metadata={
                        "structural_hash": parent.structural_hash,
                        "parent_index": parent_index,
                        "parent_count": len(parents),
                    },
                ),
            )
    return tuple(requests)


__all__ = ["MutationRequest", "build_mutation_requests"]
