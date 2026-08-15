"""Parent-structure-aware mutation request expansion."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from ..models import CandidateRef
from .ids import build_mutation_request_id
from .policies import MutationPolicy, MutationRecipe
from .requests import MutationRequest, build_mutation_requests


def expand_mutation_requests(
    parent_refs: tuple[CandidateRef, ...] | list[CandidateRef],
    *,
    generation_index: int,
    policy: MutationPolicy,
    parent_candidates: Mapping[str, Mapping[str, Any]],
) -> tuple[MutationRequest, ...]:
    """Build mutation requests, expanding explicit all-position recipes.

    Existing fixed-cardinality ``variants_per_parent`` behavior is delegated to
    ``build_mutation_requests`` unless at least one enabled recipe explicitly
    opts into ``parameters.apply_to == "all_valid_positions"``.
    """
    if not _requires_parent_expansion(policy):
        return build_mutation_requests(parent_refs, generation_index=generation_index, policy=policy)
    parents = tuple(parent_refs)
    requests: list[MutationRequest] = []
    for parent_index, parent in enumerate(parents):
        if not isinstance(parent, CandidateRef):
            raise ValueError("parent_refs must contain CandidateRef records.")
        document = parent_candidates.get(parent.candidate_id)
        if document is None:
            raise ValueError(f"missing parent Candidate document for {parent.candidate_id!r}.")
        variant_index = 0
        for recipe in policy.enabled_recipes:
            parameters = dict(recipe.parameters)
            if parameters.get("apply_to") != "all_valid_positions":
                for fixed_variant in range(policy.variants_per_parent):
                    requests.append(
                        _request(
                            parent,
                            parent_index=parent_index,
                            parent_count=len(parents),
                            generation_index=generation_index,
                            policy=policy,
                            recipe=recipe,
                            variant_index=variant_index,
                            parameters=parameters,
                            expansion_mode="fixed_cardinality",
                            raw_variant_index=fixed_variant,
                        ),
                    )
                    variant_index += 1
                continue
            for insertion_index in range(_single_layer_operation_count(document) + 1):
                expanded_parameters = {
                    **parameters,
                    "insertion_index": insertion_index,
                }
                requests.append(
                    _request(
                        parent,
                        parent_index=parent_index,
                        parent_count=len(parents),
                        generation_index=generation_index,
                        policy=policy,
                        recipe=recipe,
                        variant_index=variant_index,
                        parameters=expanded_parameters,
                        expansion_mode="all_valid_positions",
                        raw_variant_index=insertion_index,
                    ),
                )
                variant_index += 1
    return tuple(requests)


def _requires_parent_expansion(policy: MutationPolicy) -> bool:
    return any(
        dict(recipe.parameters).get("apply_to") == "all_valid_positions"
        for recipe in policy.enabled_recipes
    )


def _request(
    parent: CandidateRef,
    *,
    parent_index: int,
    parent_count: int,
    generation_index: int,
    policy: MutationPolicy,
    recipe: MutationRecipe,
    variant_index: int,
    parameters: Mapping[str, Any],
    expansion_mode: str,
    raw_variant_index: int,
) -> MutationRequest:
    return MutationRequest(
        request_id=build_mutation_request_id(
            parent_candidate_id=parent.candidate_id,
            generation_index=generation_index,
            mutation_type=recipe.mutation_type,
            variant_index=variant_index,
        ),
        parent_candidate_id=parent.candidate_id,
        parent_candidate_uri=parent.candidate_uri,
        root_candidate_id=parent.metadata.get("root_candidate_id"),
        generation_index=generation_index,
        mutation_type=recipe.mutation_type,
        policy_id=policy.policy_id,
        recipe_id=recipe.recipe_id,
        variant_index=variant_index,
        parameters=dict(parameters),
        metadata={
            "structural_hash": parent.structural_hash,
            "parent_index": parent_index,
            "parent_count": parent_count,
            "expansion_mode": expansion_mode,
            "raw_variant_index": raw_variant_index,
        },
    )


def _single_layer_operation_count(candidate: Mapping[str, Any]) -> int:
    operations = list(dict(candidate["circuit"])["operations"])
    blocks = _layer_blocks(operations)
    if not blocks:
        return len(operations)
    return len(blocks.get(0, ()))


def _layer_blocks(operations: Sequence[Mapping[str, Any]]) -> dict[int, list[Mapping[str, Any]]]:
    blocks: dict[int, list[Mapping[str, Any]]] = {}
    for operation in operations:
        metadata = dict(operation.get("metadata", {}))
        raw_layer = metadata.get("layer_index", operation.get("layer"))
        if raw_layer is None:
            return {}
        try:
            layer = int(raw_layer)
        except (TypeError, ValueError):
            return {}
        blocks.setdefault(layer, []).append(operation)
    return blocks


__all__ = ["expand_mutation_requests"]
