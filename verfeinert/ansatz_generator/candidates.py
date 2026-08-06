"""Candidate records and lightweight normalization helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from verfeinert.core.io import to_json_safe
from verfeinert.core.validation import CoreValidationError, require_identifier

from .lineage import LineageRecord
from .validation import GeneratorValidationError


@dataclass(frozen=True)
class CandidateRecord:
    """Backend-independent candidate metadata record."""

    circuit_id: str
    operations: tuple[dict[str, Any], ...]
    layer: int
    lineage: LineageRecord | None = None
    parameter_count: int | None = None
    operation_count: int | None = None
    two_qubit_operation_count: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        try:
            circuit_id = require_identifier(self.circuit_id, "candidate.circuit_id")
        except CoreValidationError as exc:
            raise GeneratorValidationError(str(exc)) from exc
        if type(self.layer) is not int or self.layer < 0:
            raise GeneratorValidationError("candidate.layer must be a non-negative integer.")
        operations = tuple(to_json_safe(operation) for operation in self.operations)
        for operation in operations:
            if not isinstance(operation, dict):
                raise GeneratorValidationError("candidate.operations must contain mappings.")
        lineage = self.lineage or LineageRecord(circuit_id=circuit_id)
        operation_count = self.operation_count if self.operation_count is not None else len(operations)
        two_qubit_count = (
            self.two_qubit_operation_count
            if self.two_qubit_operation_count is not None
            else sum(1 for op in operations if len(op.get("wires", ())) == 2)
        )
        if operation_count < 0 or two_qubit_count < 0:
            raise GeneratorValidationError("candidate counts must be non-negative.")
        object.__setattr__(self, "circuit_id", circuit_id)
        object.__setattr__(self, "operations", operations)
        object.__setattr__(self, "lineage", lineage)
        object.__setattr__(self, "operation_count", operation_count)
        object.__setattr__(self, "two_qubit_operation_count", two_qubit_count)
        object.__setattr__(self, "metadata", to_json_safe(self.metadata))

    def to_dict(self) -> dict[str, Any]:
        """Serialize the candidate as a JSON-safe mapping."""
        return {
            "circuit_id": self.circuit_id,
            "operations": list(self.operations),
            "layer": self.layer,
            "lineage": self.lineage.to_dict() if self.lineage else None,
            "parameter_count": self.parameter_count,
            "operation_count": self.operation_count,
            "two_qubit_operation_count": self.two_qubit_operation_count,
            "metadata": to_json_safe(self.metadata),
        }


__all__ = ["CandidateRecord"]
