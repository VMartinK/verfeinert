"""Deterministic mutation schedules across generations."""

from __future__ import annotations

from dataclasses import dataclass, field

from ..models import require_identifier, require_mapping, require_non_negative_int
from .policies import MutationPolicy


@dataclass(frozen=True)
class MutationSchedule:
    """A mapping from generation ranges to mutation policies."""

    schedule_id: str
    default_policy: MutationPolicy
    generation_overrides: dict[int, MutationPolicy] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "schedule_id", require_identifier(self.schedule_id, "schedule_id"))
        if not isinstance(self.default_policy, MutationPolicy):
            raise ValueError("default_policy must be a MutationPolicy.")
        overrides = require_mapping(self.generation_overrides, "generation_overrides")
        normalized: dict[int, MutationPolicy] = {}
        for generation, policy in overrides.items():
            generation_index = require_non_negative_int(generation, "generation index")
            if not isinstance(policy, MutationPolicy):
                raise ValueError("generation_overrides must contain MutationPolicy values.")
            normalized[generation_index] = policy
        object.__setattr__(self, "generation_overrides", normalized)

    def policy_for_generation(self, generation_index: int) -> MutationPolicy:
        """Return the policy for one generation."""
        generation = require_non_negative_int(generation_index, "generation_index")
        return self.generation_overrides.get(generation, self.default_policy)

    def to_dict(self) -> dict[str, object]:
        """Return JSON-safe schedule data."""
        return {
            "schedule_id": self.schedule_id,
            "default_policy": self.default_policy.to_dict(),
            "generation_overrides": {
                str(generation): policy.to_dict()
                for generation, policy in sorted(self.generation_overrides.items())
            },
        }


__all__ = ["MutationSchedule"]
