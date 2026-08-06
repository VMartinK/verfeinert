"""Generator-specific structural constraint records."""

from __future__ import annotations

from dataclasses import dataclass

from .connectivity import Connectivity
from .operations import DEFAULT_GATE_REGISTRY
from .validation import GeneratorValidationError


@dataclass(frozen=True)
class ConstraintSet:
    """Bundle of gate and connectivity rules for ansatz generation."""

    allowed_gates: tuple[str, ...] | None = None
    allowed_inserted_gates: tuple[str, ...] = ("cx", "cz")
    connectivity: Connectivity | None = None
    preserve_layer_count: bool = True
    preserve_parameter_count: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "allowed_gates", _normalize_gate_tuple(self.allowed_gates))
        object.__setattr__(
            self,
            "allowed_inserted_gates",
            _normalize_gate_tuple(self.allowed_inserted_gates) or (),
        )
        if self.connectivity is not None and not isinstance(self.connectivity, Connectivity):
            raise TypeError("connectivity must be a Connectivity or None.")
        for field_name in ("preserve_layer_count", "preserve_parameter_count"):
            if type(getattr(self, field_name)) is not bool:
                raise GeneratorValidationError(f"{field_name} must be a boolean.")

    def is_gate_allowed(self, gate: str) -> bool:
        """Return whether ``gate`` may appear in a candidate."""
        normalized = DEFAULT_GATE_REGISTRY.normalize(gate)
        return self.allowed_gates is None or normalized in self.allowed_gates

    def is_inserted_gate_allowed(self, gate: str) -> bool:
        """Return whether mutation primitives may insert ``gate``."""
        return DEFAULT_GATE_REGISTRY.normalize(gate) in self.allowed_inserted_gates

    def is_edge_allowed(self, a: int, b: int) -> bool:
        """Return whether a two-qubit edge is structurally allowed."""
        if self.connectivity is None:
            return True
        return self.connectivity.allows(a, b)


def _normalize_gate_tuple(gates: tuple[str, ...] | list[str] | set[str] | None) -> tuple[str, ...] | None:
    if gates is None:
        return None
    return tuple(sorted({DEFAULT_GATE_REGISTRY.normalize(gate) for gate in gates}))


__all__ = ["ConstraintSet"]
