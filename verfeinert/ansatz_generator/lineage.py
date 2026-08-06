"""Candidate lineage records."""

from __future__ import annotations

from dataclasses import dataclass

from verfeinert.core.validation import CoreValidationError, require_identifier

from .validation import GeneratorValidationError


@dataclass(frozen=True)
class LineageRecord:
    """Parent-child provenance for generated candidates."""

    circuit_id: str
    parent_circuit_id: str | None = None
    root_circuit_id: str | None = None
    generation_index: int = 0
    variant_index: int = 0

    def __post_init__(self) -> None:
        try:
            circuit_id = require_identifier(self.circuit_id, "lineage.circuit_id")
            parent = (
                None
                if self.parent_circuit_id is None
                else require_identifier(self.parent_circuit_id, "lineage.parent_circuit_id")
            )
            root = (
                None
                if self.root_circuit_id is None
                else require_identifier(self.root_circuit_id, "lineage.root_circuit_id")
            )
        except CoreValidationError as exc:
            raise GeneratorValidationError(str(exc)) from exc
        if type(self.generation_index) is not int or self.generation_index < 0:
            raise GeneratorValidationError("generation_index must be a non-negative integer.")
        if type(self.variant_index) is not int or self.variant_index < 0:
            raise GeneratorValidationError("variant_index must be a non-negative integer.")
        object.__setattr__(self, "circuit_id", circuit_id)
        object.__setattr__(self, "parent_circuit_id", parent)
        object.__setattr__(self, "root_circuit_id", root or parent or circuit_id)

    def to_dict(self) -> dict[str, object]:
        """Serialize lineage as a JSON-safe mapping."""
        return {
            "circuit_id": self.circuit_id,
            "parent_circuit_id": self.parent_circuit_id,
            "root_circuit_id": self.root_circuit_id,
            "generation_index": self.generation_index,
            "variant_index": self.variant_index,
        }


__all__ = ["LineageRecord"]
