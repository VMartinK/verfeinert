"""Generator-specific structural constraint records."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from verfeinert.core import to_json_safe

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

    @classmethod
    def from_mapping(cls, mapping: Mapping[str, Any]) -> "ConstraintSet":
        """Build constraints from JSON/YAML-compatible configuration."""
        if isinstance(mapping, ConstraintSet):
            return mapping
        if not isinstance(mapping, Mapping):
            raise GeneratorValidationError("constraints must be a mapping.")
        data = dict(mapping)
        connectivity = data.get("connectivity")
        if connectivity is not None and not isinstance(connectivity, Connectivity):
            connectivity = Connectivity.from_mapping(connectivity)
        return cls(
            allowed_gates=data.get("allowed_gates"),
            allowed_inserted_gates=data.get("allowed_inserted_gates", ("cx", "cz")),
            connectivity=connectivity,
            preserve_layer_count=data.get("preserve_layer_count", True),
            preserve_parameter_count=data.get("preserve_parameter_count", False),
        )

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe structural-constraint description."""
        return {
            "allowed_gates": list(self.allowed_gates) if self.allowed_gates is not None else None,
            "allowed_inserted_gates": list(self.allowed_inserted_gates),
            "connectivity": self.connectivity.to_dict() if self.connectivity is not None else None,
            "preserve_layer_count": self.preserve_layer_count,
            "preserve_parameter_count": self.preserve_parameter_count,
        }

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


def validate_candidate_constraints(
    candidate: Mapping[str, Any],
    constraints: ConstraintSet | Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Validate a canonical Candidate JSON document against generator constraints."""
    payload = to_json_safe(dict(candidate))
    constraint_set = _constraint_set_or_none(constraints)
    if constraint_set is None:
        return payload
    circuit = payload.get("circuit")
    if not isinstance(circuit, Mapping):
        raise GeneratorValidationError("candidate circuit is required for constraint validation.")
    try:
        n_qubits = int(circuit["n_qubits"])
    except (KeyError, TypeError, ValueError) as exc:
        raise GeneratorValidationError("candidate circuit.n_qubits is required for constraint validation.") from exc
    if constraint_set.connectivity is not None and constraint_set.connectivity.n_qubits != n_qubits:
        raise GeneratorValidationError(
            "candidate violates structural constraints: "
            "connectivity.n_qubits does not match circuit.n_qubits.",
        )
    operations = circuit.get("operations")
    if not isinstance(operations, Sequence) or isinstance(operations, (str, bytes, bytearray)):
        raise GeneratorValidationError("candidate circuit.operations must be a sequence.")
    for index, operation in enumerate(operations):
        if not isinstance(operation, Mapping):
            raise GeneratorValidationError("candidate operations must be mappings.")
        gate = _operation_gate_name(operation)
        if not constraint_set.is_gate_allowed(gate):
            raise GeneratorValidationError(
                "candidate violates structural constraints: "
                f"gate {gate!r} at operation {index} is not allowed.",
            )
        qubits = _operation_qubits(operation, index)
        if len(qubits) == 2 and not constraint_set.is_edge_allowed(qubits[0], qubits[1]):
            raise GeneratorValidationError(
                "candidate violates structural constraints: "
                f"edge {list(qubits)!r} at operation {index} is not allowed.",
            )
    return payload


def validate_mutation_constraints(
    parent: Mapping[str, Any],
    child: Mapping[str, Any],
    constraints: ConstraintSet | Mapping[str, Any] | None,
) -> dict[str, Any]:
    '''Validate parent-to-child structural invariants for one mutation transition.'''
    constraint_set = _constraint_set_or_none(constraints)
    if constraint_set is None:
        return to_json_safe(dict(child))

    parent_payload = validate_candidate_constraints(parent, constraint_set)
    child_payload = validate_candidate_constraints(child, constraint_set)

    if constraint_set.preserve_parameter_count:
        parent_parameter_count = _candidate_parameter_count(parent_payload)
        child_parameter_count = _candidate_parameter_count(child_payload)
        if parent_parameter_count != child_parameter_count:
            raise GeneratorValidationError(
                "candidate mutation violates structural constraints: "
                "preserve_parameter_count requires parent and child parameter "
                "counts to match "
                f"(parent={parent_parameter_count}, child={child_parameter_count}).",
            )

    if constraint_set.preserve_layer_count:
        parent_layer_count = _candidate_layer_count(parent_payload)
        child_layer_count = _candidate_layer_count(child_payload)
        if parent_layer_count != child_layer_count:
            raise GeneratorValidationError(
                "candidate mutation violates structural constraints: "
                "preserve_layer_count requires parent and child layer counts "
                "to match "
                f"(parent={parent_layer_count}, child={child_layer_count}).",
            )

    return child_payload


def _candidate_parameter_count(candidate: Mapping[str, Any]) -> int:
    circuit = candidate.get("circuit")
    if not isinstance(circuit, Mapping):
        raise GeneratorValidationError(
            "candidate circuit is required for transition constraint validation.",
        )
    parameters = circuit.get("parameters")
    if not isinstance(parameters, Sequence) or isinstance(
        parameters,
        (str, bytes, bytearray),
    ):
        raise GeneratorValidationError(
            "candidate circuit.parameters must be a sequence for transition "
            "constraint validation.",
        )
    return len(parameters)


def _candidate_layer_count(candidate: Mapping[str, Any]) -> int:
    circuit = candidate.get("circuit")
    if not isinstance(circuit, Mapping):
        raise GeneratorValidationError(
            "candidate circuit is required for transition constraint validation.",
        )
    operations = circuit.get("operations")
    if not isinstance(operations, Sequence) or isinstance(
        operations,
        (str, bytes, bytearray),
    ):
        raise GeneratorValidationError(
            "candidate circuit.operations must be a sequence for transition "
            "constraint validation.",
        )

    layers: set[int] = set()
    for index, operation in enumerate(operations):
        if not isinstance(operation, Mapping):
            raise GeneratorValidationError(
                "candidate operations must be mappings for transition "
                "constraint validation.",
            )
        raw_layer = operation.get("layer")
        if raw_layer is None:
            metadata = operation.get("metadata")
            raw_layer = (
                metadata.get("layer_index")
                if isinstance(metadata, Mapping)
                else None
            )
        if raw_layer is None:
            raw_layer = 0
        if type(raw_layer) is not int or raw_layer < 0:
            raise GeneratorValidationError(
                f"candidate operation {index} layer must be a non-negative integer.",
            )
        layers.add(raw_layer)
    return len(layers)


def _normalize_gate_tuple(gates: tuple[str, ...] | list[str] | set[str] | None) -> tuple[str, ...] | None:
    if gates is None:
        return None
    return tuple(sorted({DEFAULT_GATE_REGISTRY.normalize(gate) for gate in gates}))


def _constraint_set_or_none(
    constraints: ConstraintSet | Mapping[str, Any] | None,
) -> ConstraintSet | None:
    if constraints is None:
        return None
    if isinstance(constraints, ConstraintSet):
        return constraints
    return ConstraintSet.from_mapping(constraints)


def _operation_gate_name(operation: Mapping[str, Any]) -> str:
    gate = operation.get("gate")
    if isinstance(gate, Mapping):
        gate = gate.get("name")
    if gate is None:
        gate = operation.get("name")
    if gate is None:
        raise GeneratorValidationError("candidate operation gate is required.")
    return DEFAULT_GATE_REGISTRY.normalize(str(gate))


def _operation_qubits(operation: Mapping[str, Any], index: int) -> tuple[int, ...]:
    raw = operation.get("qubits", operation.get("wires"))
    if raw is None:
        raise GeneratorValidationError(f"candidate operation {index} qubits are required.")
    if isinstance(raw, int):
        values = (raw,)
    elif isinstance(raw, Sequence) and not isinstance(raw, (str, bytes, bytearray)):
        values = tuple(raw)
    else:
        raise GeneratorValidationError(f"candidate operation {index} qubits must be a sequence.")
    try:
        qubits = tuple(int(value) for value in values)
    except (TypeError, ValueError) as exc:
        raise GeneratorValidationError(f"candidate operation {index} qubits must be integers.") from exc
    if not qubits or any(qubit < 0 for qubit in qubits) or len(set(qubits)) != len(qubits):
        raise GeneratorValidationError(f"candidate operation {index} qubits must be unique non-negative integers.")
    return qubits


__all__ = ["ConstraintSet", "validate_candidate_constraints", "validate_mutation_constraints"]
