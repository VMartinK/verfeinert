"""Mutation policy records that describe intended transformations."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..models import require_identifier, require_mapping, require_supported


SUPPORTED_MUTATION_TYPES = (
    "insert",
    "replace",
    "remove",
    "swap",
    "reorder",
    "layer_propagation",
)


@dataclass(frozen=True)
class MutationRecipe:
    """One weighted mutation recipe."""

    recipe_id: str
    mutation_type: str
    probability: float = 1.0
    parameters: dict[str, Any] = field(default_factory=dict)
    enabled: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "recipe_id", require_identifier(self.recipe_id, "recipe_id"))
        object.__setattr__(
            self,
            "mutation_type",
            require_supported(self.mutation_type, "mutation_type", SUPPORTED_MUTATION_TYPES),
        )
        if type(self.probability) not in {int, float} or self.probability < 0:
            raise ValueError("probability must be a non-negative number.")
        object.__setattr__(self, "probability", float(self.probability))
        if type(self.enabled) is not bool:
            raise ValueError("enabled must be a boolean.")
        object.__setattr__(self, "parameters", require_mapping(self.parameters, "parameters"))

    def to_dict(self) -> dict[str, Any]:
        """Return JSON-safe recipe data."""
        return {
            "recipe_id": self.recipe_id,
            "mutation_type": self.mutation_type,
            "probability": self.probability,
            "parameters": dict(self.parameters),
            "enabled": self.enabled,
        }


@dataclass(frozen=True)
class MutationPolicy:
    """A deterministic collection of mutation recipes."""

    policy_id: str
    recipes: tuple[MutationRecipe, ...]
    variants_per_parent: int = 1
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "policy_id", require_identifier(self.policy_id, "policy_id"))
        recipes = tuple(self.recipes)
        if not recipes:
            raise ValueError("MutationPolicy requires at least one recipe.")
        if any(not isinstance(recipe, MutationRecipe) for recipe in recipes):
            raise ValueError("recipes must contain MutationRecipe records.")
        object.__setattr__(self, "recipes", recipes)
        if type(self.variants_per_parent) is not int or self.variants_per_parent < 1:
            raise ValueError("variants_per_parent must be a positive integer.")
        object.__setattr__(self, "metadata", require_mapping(self.metadata, "metadata"))

    @property
    def enabled_recipes(self) -> tuple[MutationRecipe, ...]:
        """Return enabled recipes with positive probability."""
        return tuple(recipe for recipe in self.recipes if recipe.enabled and recipe.probability > 0)

    def recipe_for_variant(self, variant_index: int) -> MutationRecipe:
        """Pick a recipe deterministically for a variant index."""
        enabled = self.enabled_recipes
        if not enabled:
            raise ValueError("MutationPolicy has no enabled recipes.")
        return enabled[variant_index % len(enabled)]

    def to_dict(self) -> dict[str, Any]:
        """Return JSON-safe policy data."""
        return {
            "policy_id": self.policy_id,
            "variants_per_parent": self.variants_per_parent,
            "recipes": [recipe.to_dict() for recipe in self.recipes],
            "metadata": dict(self.metadata),
        }


__all__ = ["SUPPORTED_MUTATION_TYPES", "MutationPolicy", "MutationRecipe"]
