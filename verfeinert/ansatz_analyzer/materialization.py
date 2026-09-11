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
SUPPORTED_GATE_SPECS = {
    "rx": (1, 1),
    "ry": (1, 1),
    "rz": (1, 1),
    "x": (1, 0),
    "y": (1, 0),
    "z": (1, 0),
    "h": (1, 0),
    "cx": (2, 0),
    "cnot": (2, 0),
    "cz": (2, 0),
    "swap": (2, 0),
    "crx": (2, 1),
    "cry": (2, 1),
    "crz": (2, 1),
    "isingxx": (2, 1),
    "isingyy": (2, 1),
    "isingzz": (2, 1),
}
SUPPORTED_OPERATION_NAMES = tuple(sorted(SUPPORTED_GATE_SPECS))
SUPPORTED_PARAMETER_KINDS = ("trainable", "fixed", "literal_operation_parameter")


class CircuitMaterializationError(ValueError):
    """Raised when a canonical candidate cannot be materialized."""

    def __init__(self, message: str, *, reason: str = "materialization_failed") -> None:
        super().__init__(message)
        self.reason = reason


@dataclass(frozen=True)
class MaterializationCapability:
    """JSON-safe report of materializer support and configured limits."""

    backend: str
    device: str
    interface: str
    diff_method: str
    supported_operations: tuple[str, ...]
    supported_parameter_kinds: tuple[str, ...]
    limits: dict[str, int | None]
    candidate_id: str | None = None
    n_qubits: int | None = None
    operation_count: int | None = None
    trainable_parameter_count: int | None = None
    unsupported_operations: tuple[dict[str, Any], ...] = ()
    materializer_version: str = MATERIALIZER_VERSION

    @property
    def within_limits(self) -> bool:
        """Return whether candidate counts fit configured limits."""
        if self.n_qubits is not None and _exceeds_limit(self.n_qubits, self.limits.get("max_qubits")):
            return False
        if self.operation_count is not None and _exceeds_limit(self.operation_count, self.limits.get("max_operations")):
            return False
        if (
            self.trainable_parameter_count is not None
            and _exceeds_limit(
                self.trainable_parameter_count,
                self.limits.get("max_trainable_parameters"),
            )
        ):
            return False
        return True

    def to_dict(self) -> dict[str, Any]:
        """Return JSON-safe capability metadata."""
        return to_json_safe(
            {
                "materializer": "verfeinert.ansatz_analyzer.materialization",
                "materializer_version": self.materializer_version,
                "backend": self.backend,
                "device": self.device,
                "interface": self.interface,
                "diff_method": self.diff_method,
                "supported_operations": list(self.supported_operations),
                "supported_parameter_kinds": list(self.supported_parameter_kinds),
                "limits": dict(self.limits),
                "candidate_id": self.candidate_id,
                "n_qubits": self.n_qubits,
                "operation_count": self.operation_count,
                "trainable_parameter_count": self.trainable_parameter_count,
                "unsupported_operations": list(self.unsupported_operations),
                "within_limits": self.within_limits,
            },
        )


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
    limits: dict[str, int | None] = field(default_factory=dict)
    materializer_version: str = MATERIALIZER_VERSION
    circuit_body: Any = field(default=None, repr=False, compare=False)
    qml_device: Any = field(default=None, repr=False, compare=False)
    observable_cache: dict[int, Any] = field(default_factory=dict, repr=False, compare=False)

    @property
    def backend_label(self) -> str:
        """Return a compact backend label suitable for metric metadata."""
        return f"{self.backend}:{self.device}"

    @property
    def supports_parameter_broadcasting(self) -> bool:
        """Return whether ``state_callable`` accepts a ``(batch, n_params)`` array."""
        return self.circuit_body is not None

    def observable_qnode(self, observable: Any):
        """Return a cached QNode computing ``<psi(theta)|observable|psi(theta)>``.

        The QNode shares the materialized circuit body and device, so it
        accepts the same trainable-parameter vector (or a broadcast
        ``(batch, n_params)`` array) as ``state_callable``.
        """
        if self.circuit_body is None or self.qml_device is None:
            raise CircuitMaterializationError(
                "observable QNodes require a circuit materialized by this module.",
                reason="observable_unavailable",
            )
        key = id(observable)
        cached = self.observable_cache.get(key)
        if cached is not None:
            return cached
        qml = _require_pennylane()
        body = self.circuit_body

        def circuit(parameters):
            body(parameters)
            return qml.expval(observable)

        qnode = qml.QNode(
            circuit,
            self.qml_device,
            interface=self.interface,
            diff_method=self.diff_method,
        )
        self.observable_cache[key] = qnode
        return qnode

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
                "limits": dict(self.limits),
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
    rotation_overrides: Mapping[str, str] | None = None,
) -> MaterializedCircuit:
    """Materialize a canonical Candidate into a PennyLane state callable.

    ``rotation_overrides`` optionally maps an ``operation_id`` of a
    single-qubit rotation (``rx``/``ry``/``rz``) to the rotation gate that
    should be applied instead. The mapping is looked up every time the circuit
    is executed, so a mutable mapping can be updated between calls; this is
    what gate-selection optimizers such as Rotoselect rely on.
    """
    resolved = config or CircuitMaterializationConfig(enabled=True)
    if not resolved.enabled:
        raise CircuitMaterializationError(
            "circuit materialization is disabled.",
            reason="materialization_disabled",
        )
    if resolved.backend != "pennylane":
        raise CircuitMaterializationError(
            f"unsupported materialization backend: {resolved.backend!r}",
            reason="unsupported_backend",
        )

    view = _candidate_view(candidate)
    _validate_candidate_limits(view, resolved)
    wire_order = _wire_order(view)
    parameter_bindings, trainable_parameter_ids = _parameter_bindings(view)
    _validate_trainable_parameter_limit(trainable_parameter_ids, resolved)
    _validate_operations(view, parameter_bindings=parameter_bindings, wire_order=wire_order)
    qml = _require_pennylane()
    device = qml.device(resolved.device, wires=list(wire_order))

    def circuit_body(parameters):
        parameter_vector = _parameter_vector(
            parameters,
            expected_count=len(trainable_parameter_ids),
        )
        for operation in view.operations:
            _apply_operation(
                qml,
                operation,
                parameter_vector,
                parameter_bindings,
                rotation_overrides=rotation_overrides,
            )

    def circuit(parameters):
        circuit_body(parameters)
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
        limits=_materialization_limits(resolved),
        circuit_body=circuit_body,
        qml_device=device,
    )


def make_state_callable(
    candidate: CandidateView | Mapping[str, Any],
    *,
    config: CircuitMaterializationConfig | None = None,
):
    """Return a differentiable state callable for a canonical candidate."""
    return materialize_candidate(candidate, config=config).state_callable


def inspect_materialization_capability(
    candidate: CandidateView | Mapping[str, Any] | None = None,
    *,
    config: CircuitMaterializationConfig | None = None,
) -> MaterializationCapability:
    """Return materializer capabilities and optional candidate support details."""
    resolved = config or CircuitMaterializationConfig(enabled=True)
    view = _candidate_view(candidate) if candidate is not None else None
    unsupported: list[dict[str, Any]] = []
    if view is not None:
        for operation in view.operations:
            support = _operation_support_record(operation)
            if support is not None:
                unsupported.append(support)
    return MaterializationCapability(
        backend=resolved.backend,
        device=resolved.device,
        interface=resolved.interface,
        diff_method=resolved.diff_method,
        supported_operations=SUPPORTED_OPERATION_NAMES,
        supported_parameter_kinds=SUPPORTED_PARAMETER_KINDS,
        limits=_materialization_limits(resolved),
        candidate_id=view.candidate_id if view is not None else None,
        n_qubits=view.n_qubits if view is not None else None,
        operation_count=len(view.operations) if view is not None else None,
        trainable_parameter_count=_trainable_parameter_count(view) if view is not None else None,
        unsupported_operations=tuple(unsupported),
    )


def _candidate_view(candidate: CandidateView | Mapping[str, Any]) -> CandidateView:
    if isinstance(candidate, CandidateView):
        return candidate
    if isinstance(candidate, Mapping):
        return CandidateView.from_document(validate_candidate_document(candidate))
    raise TypeError("candidate must be a CandidateView or canonical Candidate mapping.")


def _validate_candidate_limits(candidate: CandidateView, config: CircuitMaterializationConfig) -> None:
    if _exceeds_limit(candidate.n_qubits, config.max_qubits):
        raise CircuitMaterializationError(
            "materialization resource limit exceeded: "
            f"n_qubits={candidate.n_qubits}, max_qubits={config.max_qubits}.",
            reason="resource_limit_exceeded",
        )
    operation_count = len(candidate.operations)
    if _exceeds_limit(operation_count, config.max_operations):
        raise CircuitMaterializationError(
            "materialization resource limit exceeded: "
            f"operation_count={operation_count}, max_operations={config.max_operations}.",
            reason="resource_limit_exceeded",
        )


def _validate_trainable_parameter_limit(
    trainable_parameter_ids: tuple[str, ...],
    config: CircuitMaterializationConfig,
) -> None:
    parameter_count = len(trainable_parameter_ids)
    if _exceeds_limit(parameter_count, config.max_trainable_parameters):
        raise CircuitMaterializationError(
            "materialization resource limit exceeded: "
            f"trainable_parameter_count={parameter_count}, "
            f"max_trainable_parameters={config.max_trainable_parameters}.",
            reason="resource_limit_exceeded",
        )


def _materialization_limits(config: CircuitMaterializationConfig) -> dict[str, int | None]:
    return {
        "max_qubits": config.max_qubits,
        "max_operations": config.max_operations,
        "max_trainable_parameters": config.max_trainable_parameters,
    }


def _exceeds_limit(value: int, limit: int | None) -> bool:
    return limit is not None and value > limit


def _trainable_parameter_count(candidate: CandidateView | None) -> int | None:
    if candidate is None:
        return None
    return sum(1 for parameter in candidate.parameters if str(parameter.get("kind", "")).lower() == "trainable")


def _require_pennylane():
    if importlib.util.find_spec("pennylane") is None:
        raise CircuitMaterializationError(
            "PennyLane is required for analyzer circuit materialization.",
            reason="backend_dependency_missing",
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
                reason="unsupported_operation",
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
    """Validate a parameter vector or a ``(batch, expected_count)`` broadcast array."""
    if parameters is None:
        if expected_count == 0:
            return ()
        raise CircuitMaterializationError(
            f"state callable expected {expected_count} trainable parameter(s), got None.",
        )
    shape = _parameter_shape(parameters)
    if shape is None:
        if expected_count == 1:
            return (parameters,)
        raise CircuitMaterializationError(
            f"state callable expected {expected_count} trainable parameter(s).",
        )
    if len(shape) == 2:
        if shape[1] != expected_count:
            raise CircuitMaterializationError(
                f"state callable expected {expected_count} trainable parameter(s) per batch row, "
                f"got {shape[1]}.",
            )
        return _BroadcastParameters(parameters)
    if len(shape) != 1:
        raise CircuitMaterializationError(
            "state callable parameters must be a vector or a (batch, n_params) array.",
        )
    if shape[0] != expected_count:
        raise CircuitMaterializationError(
            f"state callable expected {expected_count} trainable parameter(s), got {shape[0]}.",
        )
    return parameters


class _BroadcastParameters:
    """Column view over a ``(batch, n_params)`` array for PennyLane broadcasting."""

    __slots__ = ("array",)

    def __init__(self, array) -> None:
        self.array = array

    def __getitem__(self, index):
        return self.array[:, int(index)]


def _parameter_shape(parameters) -> tuple[int, ...] | None:
    shape = getattr(parameters, "shape", None)
    if shape is not None:
        return tuple(int(item) for item in shape)
    try:
        count = len(parameters)
    except TypeError:
        return None
    if count and all(getattr(item, "shape", None) is not None and len(item.shape) == 1 for item in parameters):
        return (count, int(parameters[0].shape[0]))
    return (count,)


ROTATION_GATES = ("rx", "ry", "rz")


def _apply_operation(
    qml,
    operation: OperationView,
    parameter_vector,
    parameter_bindings: Mapping[str, Mapping[str, Any]],
    rotation_overrides: Mapping[str, str] | None = None,
) -> None:
    gate = operation.gate_name
    wires = list(operation.qubits)
    if rotation_overrides and gate in ROTATION_GATES:
        override = rotation_overrides.get(operation.operation_id)
        if override is not None:
            override = str(override).lower()
            if override not in ROTATION_GATES:
                raise CircuitMaterializationError(
                    f"rotation override for {operation.operation_id!r} must be one of {ROTATION_GATES}, got {override!r}.",
                )
            gate = override
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
            reason="unsupported_semantic_gate_identity",
        )
    if operation.gate_version is not None:
        raise CircuitMaterializationError(
            "unsupported semantic gate identity for operation "
            f"{operation.operation_id!r}: gate={gate!r}, "
            f"namespace={operation.gate_namespace!r}, version={operation.gate_version!r}. "
            f"The v0.3.1 PennyLane materializer supports only legacy omitted "
            f"versions for {SUPPORTED_GATE_NAMESPACE!r}.",
            reason="unsupported_semantic_gate_identity",
        )
    return SUPPORTED_GATE_SPECS.get(gate)


def _operation_support_record(operation: OperationView) -> dict[str, Any] | None:
    try:
        spec = _gate_spec(operation)
    except CircuitMaterializationError as exc:
        return {
            "operation_id": operation.operation_id,
            "gate": operation.gate_name,
            "reason": exc.reason,
            "message": str(exc),
        }
    if spec is None:
        return {
            "operation_id": operation.operation_id,
            "gate": operation.gate_name,
            "reason": "unsupported_operation",
            "message": f"unsupported candidate operation {operation.gate_name!r}.",
        }
    expected_wires, expected_parameters = spec
    if len(operation.qubits) != expected_wires:
        return {
            "operation_id": operation.operation_id,
            "gate": operation.gate_name,
            "reason": "unsupported_wire_arity",
            "message": (
                f"gate {operation.gate_name!r} requires {expected_wires} wire(s), "
                f"got {len(operation.qubits)}."
            ),
        }
    if len(operation.parameters) != expected_parameters:
        return {
            "operation_id": operation.operation_id,
            "gate": operation.gate_name,
            "reason": "unsupported_parameter_arity",
            "message": (
                f"gate {operation.gate_name!r} requires {expected_parameters} parameter(s), "
                f"got {len(operation.parameters)}."
            ),
        }
    return None


__all__ = [
    "CircuitMaterializationError",
    "MATERIALIZER_VERSION",
    "MaterializationCapability",
    "MaterializedCircuit",
    "ROTATION_GATES",
    "SUPPORTED_GATE_NAMESPACE",
    "StateCallableProvider",
    "inspect_materialization_capability",
    "make_state_callable",
    "materialize_candidate",
]
