"""Analyzer-owned materialization of canonical candidates into state callables."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
import importlib
import importlib.util
from typing import Any

from verfeinert.core.io.serialization import to_json_safe

from .config import CircuitMaterializationConfig
from .models import CandidateView, OperationView
from .validation import validate_candidate_document


MATERIALIZER_VERSION = "verfeinert.ansatz_analyzer.materialization.v1"
SUPPORTED_GATE_NAMESPACE = "verfeinert.default_gates"


class CircuitMaterializationError(ValueError):
    """Raised when a canonical candidate cannot be materialized."""


@dataclass(frozen=True)
class MaterializedCircuit:
    """Runtime state callable and JSON-safe metadata for one candidate."""

    candidate_id: str
    state_callable: Any
    qnode: Any
    trainable_parameter_ids: tuple[str, ...]
    backend: str
    device: str
    interface: str
    diff_method: str
    wire_order: tuple[int, ...]
    gate_names: tuple[str, ...]
    operation_ids: tuple[str, ...]
    materializer_version: str = MATERIALIZER_VERSION

    @property
    def backend_label(self) -> str:
        """Return a compact backend label suitable for metric metadata."""
        return f"{self.backend}:{self.device}"

    def to_metadata(self) -> dict[str, Any]:
        """Return JSON-safe materialization metadata without runtime objects."""
        return to_json_safe(
            {
                "materializer": "verfeinert.ansatz_analyzer.materialization",
                "materializer_version": self.materializer_version,
                "backend": self.backend,
                "backend_label": self.backend_label,
                "device": self.device,
                "interface": self.interface,
                "diff_method": self.diff_method,
                "wire_order": list(self.wire_order),
                "trainable_parameter_ids": list(self.trainable_parameter_ids),
                "gate_names": list(self.gate_names),
                "operation_ids": list(self.operation_ids),
                "operation_count": len(self.operation_ids),
                "qnode_return": "state",
            },
        )


@dataclass
class StateCallableProvider:
    """Per-run materialized state-callable cache."""

    config: CircuitMaterializationConfig
    _cache: dict[str, MaterializedCircuit] = field(default_factory=dict)

    def materialize(self, candidate: CandidateView | Mapping[str, Any]) -> MaterializedCircuit:
        """Return a cached materialized circuit for a candidate."""
        view = _candidate_view(candidate)
        cached = self._cache.get(view.candidate_id)
        if cached is not None:
            return cached
        materialized = materialize_candidate(view, config=self.config)
        self._cache[view.candidate_id] = materialized
        return materialized


def materialize_candidate(
    candidate: CandidateView | Mapping[str, Any],
    *,
    config: CircuitMaterializationConfig | None = None,
) -> MaterializedCircuit:
    """Materialize a canonical Candidate into a PennyLane state callable."""
    resolved = config or CircuitMaterializationConfig(enabled=True)
    if not resolved.enabled:
        raise CircuitMaterializationError("circuit materialization is disabled.")
    if resolved.backend != "pennylane":
        raise CircuitMaterializationError(f"unsupported materialization backend: {resolved.backend!r}")

    qml = _require_pennylane()
    view = _candidate_view(candidate)
    wire_order = _wire_order(view)
    parameter_bindings, trainable_parameter_ids = _parameter_bindings(view)
    _validate_operations(view, parameter_bindings=parameter_bindings, wire_order=wire_order)
    device = qml.device(resolved.device, wires=list(wire_order))

    def circuit(parameters):
        parameter_vector = _parameter_vector(
            parameters,
            expected_count=len(trainable_parameter_ids),
        )
        for operation in view.operations:
            _apply_operation(qml, operation, parameter_vector, parameter_bindings)
        return qml.state()

    qnode = qml.QNode(
        circuit,
        device,
        interface=resolved.interface,
        diff_method=resolved.diff_method,
    )

    def state_callable(parameters):
        return qnode(parameters)

    return MaterializedCircuit(
        candidate_id=view.candidate_id,
        state_callable=state_callable,
        qnode=qnode,
        trainable_parameter_ids=trainable_parameter_ids,
        backend=resolved.backend,
        device=resolved.device,
        interface=resolved.interface,
        diff_method=resolved.diff_method,
        wire_order=wire_order,
        gate_names=tuple(operation.gate_name for operation in view.operations),
        operation_ids=tuple(operation.operation_id for operation in view.operations),
    )


def make_state_callable(
    candidate: CandidateView | Mapping[str, Any],
    *,
    config: CircuitMaterializationConfig | None = None,
):
    """Return a differentiable state callable for a canonical candidate."""
    return materialize_candidate(candidate, config=config).state_callable


def _candidate_view(candidate: CandidateView | Mapping[str, Any]) -> CandidateView:
    if isinstance(candidate, CandidateView):
        return candidate
    if isinstance(candidate, Mapping):
        return CandidateView.from_document(validate_candidate_document(candidate))
    raise TypeError("candidate must be a CandidateView or canonical Candidate mapping.")


def _require_pennylane():
    if importlib.util.find_spec("pennylane") is None:
        raise CircuitMaterializationError(
            "PennyLane is required for analyzer circuit materialization.",
        )
    return importlib.import_module("pennylane")


def _wire_order(candidate: CandidateView) -> tuple[int, ...]:
    wire_order = candidate.wire_order or tuple(range(candidate.n_qubits))
    if len(wire_order) != candidate.n_qubits:
        raise CircuitMaterializationError(
            "candidate.circuit.wire_order length must match candidate.circuit.n_qubits.",
        )
    if len(set(wire_order)) != len(wire_order):
        raise CircuitMaterializationError("candidate.circuit.wire_order must not contain duplicates.")
    return tuple(wire_order)


def _parameter_bindings(candidate: CandidateView) -> tuple[dict[str, dict[str, Any]], tuple[str, ...]]:
    bindings: dict[str, dict[str, Any]] = {}
    trainable_parameter_ids: list[str] = []
    for index, parameter in enumerate(candidate.parameters):
        parameter_id = _parameter_id(parameter, field_name=f"circuit.parameters[{index}].parameter_id")
        if parameter_id in bindings:
            raise CircuitMaterializationError(f"duplicate circuit parameter_id: {parameter_id!r}")
        kind = str(parameter.get("kind", "")).strip().lower()
        if kind == "trainable":
            bindings[parameter_id] = {
                "kind": "trainable",
                "index": len(trainable_parameter_ids),
            }
            trainable_parameter_ids.append(parameter_id)
            continue
        if kind == "fixed":
            if "value" not in parameter:
                raise CircuitMaterializationError(f"fixed parameter {parameter_id!r} is missing a value.")
            bindings[parameter_id] = {
                "kind": "fixed",
                "value": _literal_value(parameter["value"], field_name=parameter_id),
            }
            continue
        if kind == "derived":
            raise CircuitMaterializationError(
                f"derived parameter {parameter_id!r} is representable in Candidate JSON "
                "but is not materializable by the v0.3.1 PennyLane materializer.",
            )
        raise CircuitMaterializationError(f"unsupported parameter kind for {parameter_id!r}: {kind!r}")
    return bindings, tuple(trainable_parameter_ids)


def _validate_operations(
    candidate: CandidateView,
    *,
    parameter_bindings: Mapping[str, Mapping[str, Any]],
    wire_order: tuple[int, ...],
) -> None:
    known_wires = set(wire_order)
    for operation in candidate.operations:
        if any(wire not in known_wires for wire in operation.qubits):
            raise CircuitMaterializationError(
                f"operation {operation.operation_id!r} references qubits outside wire_order.",
            )
        spec = _gate_spec(operation)
        if spec is None:
            raise CircuitMaterializationError(
                f"unsupported candidate operation {operation.gate_name!r} "
                f"at {operation.operation_id!r}.",
            )
        expected_wires, expected_parameters = spec
        if len(operation.qubits) != expected_wires:
            raise CircuitMaterializationError(
                f"operation {operation.operation_id!r} gate {operation.gate_name!r} "
                f"requires {expected_wires} wire(s), got {len(operation.qubits)}.",
            )
        if len(operation.parameters) != expected_parameters:
            raise CircuitMaterializationError(
                f"operation {operation.operation_id!r} gate {operation.gate_name!r} "
                f"requires {expected_parameters} parameter(s), got {len(operation.parameters)}.",
            )
        for parameter in operation.parameters:
            if parameter.get("kind") == "reference":
                parameter_id = _parameter_id(parameter, field_name=f"{operation.operation_id}.parameter_id")
                if parameter_id not in parameter_bindings:
                    raise CircuitMaterializationError(
                        f"operation {operation.operation_id!r} references unknown parameter {parameter_id!r}.",
                    )
            elif parameter.get("kind") == "literal":
                _literal_value(parameter.get("value"), field_name=f"{operation.operation_id}.literal")
            else:
                raise CircuitMaterializationError(
                    f"operation {operation.operation_id!r} has unsupported parameter record.",
                )


def _parameter_vector(parameters, *, expected_count: int):
    if parameters is None:
        if expected_count == 0:
            return ()
        raise CircuitMaterializationError(
            f"state callable expected {expected_count} trainable parameter(s), got None.",
        )
    try:
        count = len(parameters)
    except TypeError as exc:
        if expected_count == 1:
            return (parameters,)
        raise CircuitMaterializationError(
            f"state callable expected {expected_count} trainable parameter(s).",
        ) from exc
    if count != expected_count:
        raise CircuitMaterializationError(
            f"state callable expected {expected_count} trainable parameter(s), got {count}.",
        )
    return parameters


def _apply_operation(
    qml,
    operation: OperationView,
    parameter_vector,
    parameter_bindings: Mapping[str, Mapping[str, Any]],
) -> None:
    gate = operation.gate_name
    wires = list(operation.qubits)
    if gate == "rx":
        qml.RX(_operation_parameter(operation, 0, parameter_vector, parameter_bindings), wires=wires[0])
    elif gate == "ry":
        qml.RY(_operation_parameter(operation, 0, parameter_vector, parameter_bindings), wires=wires[0])
    elif gate == "rz":
        qml.RZ(_operation_parameter(operation, 0, parameter_vector, parameter_bindings), wires=wires[0])
    elif gate == "x":
        qml.PauliX(wires=wires[0])
    elif gate == "y":
        qml.PauliY(wires=wires[0])
    elif gate == "z":
        qml.PauliZ(wires=wires[0])
    elif gate == "h":
        qml.Hadamard(wires=wires[0])
    elif gate in {"cx", "cnot"}:
        qml.CNOT(wires=wires)
    elif gate == "cz":
        qml.CZ(wires=wires)
    elif gate == "swap":
        qml.SWAP(wires=wires)
    elif gate == "crx":
        qml.CRX(_operation_parameter(operation, 0, parameter_vector, parameter_bindings), wires=wires)
    elif gate == "cry":
        qml.CRY(_operation_parameter(operation, 0, parameter_vector, parameter_bindings), wires=wires)
    elif gate == "crz":
        qml.CRZ(_operation_parameter(operation, 0, parameter_vector, parameter_bindings), wires=wires)
    elif gate == "isingxx":
        qml.IsingXX(_operation_parameter(operation, 0, parameter_vector, parameter_bindings), wires=wires)
    elif gate == "isingyy":
        qml.IsingYY(_operation_parameter(operation, 0, parameter_vector, parameter_bindings), wires=wires)
    elif gate == "isingzz":
        qml.IsingZZ(_operation_parameter(operation, 0, parameter_vector, parameter_bindings), wires=wires)
    else:
        raise CircuitMaterializationError(
            f"unsupported candidate operation {gate!r} at {operation.operation_id!r}.",
        )


def _operation_parameter(
    operation: OperationView,
    parameter_index: int,
    parameter_vector,
    parameter_bindings: Mapping[str, Mapping[str, Any]],
):
    try:
        parameter = operation.parameters[parameter_index]
    except IndexError as exc:
        raise CircuitMaterializationError(
            f"operation {operation.operation_id!r} is missing parameter {parameter_index}.",
        ) from exc
    kind = parameter.get("kind")
    if kind == "literal":
        return _literal_value(parameter.get("value"), field_name=f"{operation.operation_id}.literal")
    if kind != "reference":
        raise CircuitMaterializationError(
            f"operation {operation.operation_id!r} has unsupported parameter kind {kind!r}.",
        )
    parameter_id = _parameter_id(parameter, field_name=f"{operation.operation_id}.parameter_id")
    binding = parameter_bindings.get(parameter_id)
    if binding is None:
        raise CircuitMaterializationError(
            f"operation {operation.operation_id!r} references unknown parameter {parameter_id!r}.",
        )
    if binding["kind"] == "fixed":
        return binding["value"]
    if binding["kind"] != "trainable":
        raise CircuitMaterializationError(
            f"operation {operation.operation_id!r} references unsupported parameter {parameter_id!r}.",
        )
    return parameter_vector[int(binding["index"])]


def _parameter_id(parameter: Mapping[str, Any], *, field_name: str) -> str:
    value = parameter.get("parameter_id")
    if not isinstance(value, str) or not value.strip():
        raise CircuitMaterializationError(f"{field_name} must be a non-empty string.")
    return value.strip()


def _literal_value(value: Any, *, field_name: str) -> float:
    if type(value) not in {int, float}:
        raise CircuitMaterializationError(f"{field_name} literal value must be numeric.")
    return float(value)


def _gate_spec(operation: OperationView) -> tuple[int, int] | None:
    gate = operation.gate_name
    if operation.gate_namespace not in {None, SUPPORTED_GATE_NAMESPACE}:
        raise CircuitMaterializationError(
            "unsupported semantic gate identity for operation "
            f"{operation.operation_id!r}: gate={gate!r}, "
            f"namespace={operation.gate_namespace!r}, version={operation.gate_version!r}. "
            f"The v0.3.1 PennyLane materializer supports only legacy omitted "
            f"namespaces or {SUPPORTED_GATE_NAMESPACE!r} without a gate version.",
        )
    if operation.gate_version is not None:
        raise CircuitMaterializationError(
            "unsupported semantic gate identity for operation "
            f"{operation.operation_id!r}: gate={gate!r}, "
            f"namespace={operation.gate_namespace!r}, version={operation.gate_version!r}. "
            f"The v0.3.1 PennyLane materializer supports only legacy omitted "
            f"versions for {SUPPORTED_GATE_NAMESPACE!r}.",
        )
    if gate in {"rx", "ry", "rz"}:
        return 1, 1
    if gate in {"x", "y", "z", "h"}:
        return 1, 0
    if gate in {"cx", "cnot", "cz", "swap"}:
        return 2, 0
    if gate in {"crx", "cry", "crz", "isingxx", "isingyy", "isingzz"}:
        return 2, 1
    return None


__all__ = [
    "CircuitMaterializationError",
    "MATERIALIZER_VERSION",
    "MaterializedCircuit",
    "SUPPORTED_GATE_NAMESPACE",
    "StateCallableProvider",
    "make_state_callable",
    "materialize_candidate",
]
