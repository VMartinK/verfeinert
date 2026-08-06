"""Reference-only population snapshots."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..models import CandidateRef, GenerationRecord, require_identifier, require_mapping, require_non_negative_int, require_supported


POPULATION_ROLES = ("initial", "offspring", "survivor", "archive", "rejected")


@dataclass(frozen=True)
class PopulationSnapshot:
    """A deterministic, reference-only view of a population."""

    population_id: str
    generation_index: int
    role: str
    candidate_refs: tuple[CandidateRef, ...]
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "population_id", require_identifier(self.population_id, "population_id"))
        object.__setattr__(
            self,
            "generation_index",
            require_non_negative_int(self.generation_index, "generation_index"),
        )
        object.__setattr__(self, "role", require_supported(self.role, "role", POPULATION_ROLES))
        refs = tuple(self.candidate_refs)
        if any(not isinstance(ref, CandidateRef) for ref in refs):
            raise ValueError("candidate_refs must contain CandidateRef objects.")
        object.__setattr__(self, "candidate_refs", refs)
        object.__setattr__(self, "metadata", require_mapping(self.metadata, "metadata"))

    def to_dict(self) -> dict[str, Any]:
        """Return an internal JSON-safe snapshot record."""
        return {
            "population_id": self.population_id,
            "generation_index": self.generation_index,
            "role": self.role,
            "candidate_refs": [ref.to_ref_dict() for ref in self.candidate_refs],
            "metadata": dict(self.metadata),
        }

    def to_generation_record(self) -> GenerationRecord:
        """Represent this snapshot as an EvolutionRun generation fragment."""
        if self.role == "survivor":
            survivor_refs = self.candidate_refs
            archive_refs: tuple[CandidateRef, ...] = ()
        elif self.role == "archive":
            survivor_refs = ()
            archive_refs = self.candidate_refs
        else:
            survivor_refs = ()
            archive_refs = ()
        return GenerationRecord(
            generation_index=self.generation_index,
            candidate_refs=self.candidate_refs,
            survivor_refs=survivor_refs,
            archive_refs=archive_refs,
            configuration={"population_role": self.role, "population_id": self.population_id},
        )


__all__ = ["POPULATION_ROLES", "PopulationSnapshot"]
