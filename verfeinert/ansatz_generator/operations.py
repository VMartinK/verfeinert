"""Backend-independent gate and operation records."""

from __future__ import annotations

from dataclasses import dataclass, field
from numbers import Real
from typing import Any

from verfeinert.core.io import to_json_safe
from verfeinert.core.validation import (
    require_bool,
    require_non_empty_text,
    require_positive_int,
)

from .validation import GeneratorValidationError


ParameterValue = str | int | float


@dataclass(frozen=True)
class GateDef:
    """Abstract gate definition independent of any quantum backend."""

    name: str
    n_wires: int
    n_params: int = 0
    aliases: tuple[str, ...] = ()
    is_parameterized: bool = False
    is_trainable: bool = False
    category: str = "generic"
    symmetric_wires: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        name = require_non_empty_text(self.name, "gate.name").lower()
        n_wires = require_positive_int(self.n_wires, "gate.n_wires")
        if type(self.n_params) is not int or self.n_params < 0:
            raise GeneratorValidationError("gate.n_params must be a non-negative integer.")
        aliases = tuple(
            require_non_empty_text(alias, "gate.alias").lower()
            for alias in self.aliases
        )
        is_parameterized = require_bool(self.is_parameterized, "gate.is_parameterized")
        is_trainable = require_bool(self.is_trainable, "gate.is_trainable")
        if is_parameterized and self.n_params < 1:
            raise GeneratorValidationError("parameterized gates must define parameters.")
        if is_trainable and not is_parameterized:
            raise GeneratorValidationError("trainable gates must be parameterized.")
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "n_wires", n_wires)
        object.__setattr__(self, "aliases", aliases)
        object.__setattr__(self, "is_parameterized", is_parameterized)
        object.__setattr__(self, "is_trainable", is_trainable)
        object.__setattr__(
            self,
            "category",
            require_non_empty_text(self.category, "gate.category"),
        )
        object.__setattr__(
            self,
            "symmetric_wires",
            require_bool(self.symmetric_wires, "gate.symmetric_wires"),
        )
        object.__setattr__(self, "metadata", to_json_safe(self.metadata))

    @property
    def is_parametrized(self) -> bool:
        """Compatibility spelling for older Alpha notes."""
        return self.is_parameterized

    @property
    def is_single_qubit(self) -> bool:
        """Return whether this gate acts on one wire."""
        return self.n_wires == 1

    @property
    def is_two_qubit(self) -> bool:
        """Return whether this gate acts on two wires."""
        return self.n_wires == 2


class GateRegistry:
    """Registry of backend-independent gate definitions."""

    def __init__(self) -> None:
        self._defs: dict[str, GateDef] = {}
        self._aliases: dict[str, str] = {}

    def register(self, definition: GateDef, *, overwrite: bool = False) -> None:
        """Register a gate definition and its aliases."""
        if not isinstance(definition, GateDef):
            raise TypeError("definition must be a GateDef.")
        name = definition.name
        if name in self._defs and not overwrite:
            raise GeneratorValidationError(f"gate {name!r} is already registered.")
        for alias in definition.aliases:
            if alias in self._aliases and not overwrite:
                raise GeneratorValidationError(f"gate alias {alias!r} is already registered.")
        self._defs[name] = definition
        for alias in definition.aliases:
            self._aliases[alias] = name

    def normalize(self, gate: str) -> str:
        """Normalize a gate name or alias to a registered canonical name."""
        key = require_non_empty_text(gate, "gate").lower()
        return self._aliases.get(key, key)

    def get(self, gate: str) -> GateDef:
        """Return the gate definition for a name or alias."""
        name = self.normalize(gate)
        if name not in self._defs:
            raise GeneratorValidationError(f"unknown gate {gate!r}.")
        return self._defs[name]

    def has(self, gate: str) -> bool:
        """Return whether the registry knows ``gate``."""
        try:
            return self.normalize(gate) in self._defs
        except Exception:
            return False

    def names(self) -> tuple[str, ...]:
        """Return registered canonical names in deterministic order."""
        return tuple(sorted(self._defs))

    def definitions(self) -> dict[str, GateDef]:
        """Return a copy of registered gate definitions."""
        return dict(self._defs)


def default_gate_registry() -> GateRegistry:
    """Return the default Beta-compatible gate registry."""
    registry = GateRegistry()
    for name in ("x", "y", "z"):
        registry.register(GateDef(name=name, n_wires=1, category="pauli"))
    registry.register(GateDef(name="h", n_wires=1, aliases=("hadamard",), category="basis_change"))
    for name in ("rx", "ry", "rz"):
        registry.register(
            GateDef(
                name=name,
                n_wires=1,
                n_params=1,
                is_parameterized=True,
                is_trainable=True,
                category="rotation",
            )
        )
    registry.register(GateDef(name="cx", n_wires=2, category="entangler"))
    registry.register(GateDef(name="cnot", n_wires=2, category="entangler"))
    registry.register(GateDef(name="cz", n_wires=2, category="entangler", symmetric_wires=True))
    registry.register(GateDef(name="swap", n_wires=2, category="routing", symmetric_wires=True))
    for name in ("crx", "cry", "crz"):
        registry.register(
            GateDef(
                name=name,
                n_wires=2,
                n_params=1,
                is_parameterized=True,
                is_trainable=True,
                category="controlled_rotation",
            )
        )
    for name in ("isingxx", "isingyy", "isingzz"):
        registry.register(
            GateDef(
                name=name,
                n_wires=2,
                n_params=1,
                is_parameterized=True,
                is_trainable=True,
                category="ising",
                symmetric_wires=True,
            )
        )
    return registry


DEFAULT_GATE_REGISTRY = default_gate_registry()
KNOWN_BETA_GATES = DEFAULT_GATE_REGISTRY.names()
TWO_QUBIT_GATES = tuple(
    name
    for name, definition in DEFAULT_GATE_REGISTRY.definitions().items()
    if definition.is_two_qubit
)
PARAMETERIZED_GATES = tuple(
    name
    for name, definition in DEFAULT_GATE_REGISTRY.definitions().items()
    if definition.is_parameterized
)


@dataclass(frozen=True)
class Operation:
    """Immutable backend-independent circuit operation record."""

    gate: str
    wires: tuple[int, ...]
    parameters: tuple[ParameterValue, ...] = ()
    layer: int = 0
    order: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        definition = DEFAULT_GATE_REGISTRY.get(self.gate)
        wires = _normalize_wires(self.wires)
        if len(wires) != definition.n_wires:
            raise GeneratorValidationError(
                f"gate {definition.name!r} expects {definition.n_wires} wire(s)."
            )
        params = _normalize_parameters(self.parameters)
        if params and len(params) != definition.n_params:
            raise GeneratorValidationError(
                f"gate {definition.name!r} expects {definition.n_params} parameter(s)."
            )
        if not definition.is_parameterized and params:
            raise GeneratorValidationError(f"gate {definition.name!r} is not parameterized.")
        if type(self.layer) is not int or self.layer < 0:
            raise GeneratorValidationError("operation.layer must be a non-negative integer.")
        if type(self.order) is not int or self.order < 0:
            raise GeneratorValidationError("operation.order must be a non-negative integer.")
        object.__setattr__(self, "gate", definition.name)
        object.__setattr__(self, "wires", wires)
        object.__setattr__(self, "parameters", params)
        object.__setattr__(self, "metadata", to_json_safe(self.metadata))

    @property
    def params(self) -> tuple[ParameterValue, ...]:
        """Alias used by candidate-compilation records."""
        return self.parameters

    @property
    def is_parameterized(self) -> bool:
        """Return whether this operation's gate is parameterized."""
        return DEFAULT_GATE_REGISTRY.get(self.gate).is_parameterized

    @property
    def is_two_qubit(self) -> bool:
        """Return whether this operation acts on two wires."""
        return len(self.wires) == 2

    @property
    def trainable_parameter_names(self) -> tuple[str, ...]:
        """Return symbolic trainable parameter names."""
        if not DEFAULT_GATE_REGISTRY.get(self.gate).is_trainable:
            return ()
        return tuple(param for param in self.parameters if isinstance(param, str))

    def canonical_wires(self) -> tuple[int, ...]:
        """Return sorted wires for symmetric gates and original wires otherwise."""
        if DEFAULT_GATE_REGISTRY.get(self.gate).symmetric_wires:
            return tuple(sorted(self.wires))
        return self.wires

    def to_dict(self) -> dict[str, Any]:
        """Serialize the operation as a JSON-safe mapping."""
        return {
            "gate": self.gate,
            "wires": list(self.wires),
            "parameterized": self.is_parameterized,
            "params": list(self.parameters) if self.parameters else None,
            "layer": self.layer,
            "order": self.order,
            "metadata": to_json_safe(self.metadata),
        }

    @classmethod
    def from_mapping(cls, mapping: dict[str, Any]) -> "Operation":
        """Build an operation from a Beta-style mapping."""
        if not isinstance(mapping, dict):
            raise TypeError("mapping must be a dictionary.")
        return cls(
            gate=str(mapping.get("gate") or mapping.get("name")),
            wires=tuple(_normalize_wires(mapping.get("wires", mapping.get("qubits")))),
            parameters=tuple(mapping.get("params") or mapping.get("parameters") or ()),
            layer=int(mapping.get("layer", mapping.get("metadata", {}).get("layer_index", 0))),
            order=int(mapping.get("order", mapping.get("metadata", {}).get("order", 0))),
            metadata=dict(mapping.get("metadata") or {}),
        )


def _normalize_wires(value: Any) -> tuple[int, ...]:
    if value is None:
        raise GeneratorValidationError("operation wires are required.")
    if isinstance(value, int):
        values = (value,)
    elif isinstance(value, (list, tuple)):
        values = tuple(value)
    else:
        raise GeneratorValidationError("operation wires must be an int, list, or tuple.")
    if not values:
        raise GeneratorValidationError("operation wires cannot be empty.")
    try:
        wires = tuple(int(item) for item in values)
    except Exception as exc:
        raise GeneratorValidationError("operation wires must be integer-like.") from exc
    if any(wire < 0 for wire in wires):
        raise GeneratorValidationError("operation wires must be non-negative.")
    if len(set(wires)) != len(wires):
        raise GeneratorValidationError("operation wires must not repeat.")
    return wires


def _normalize_parameters(value: Any) -> tuple[ParameterValue, ...]:
    if value is None:
        return ()
    if isinstance(value, (str, Real)):
        values = (value,)
    elif isinstance(value, (list, tuple)):
        values = tuple(value)
    else:
        raise GeneratorValidationError("operation parameters must be scalar or sequence.")
    normalized: list[ParameterValue] = []
    for item in values:
        if isinstance(item, str):
            normalized.append(require_non_empty_text(item, "parameter"))
        elif isinstance(item, Real) and type(item) is not bool:
            normalized.append(item)
        else:
            raise GeneratorValidationError("operation parameters must be strings or real numbers.")
    return tuple(normalized)


__all__ = [
    "DEFAULT_GATE_REGISTRY",
    "GateDef",
    "GateRegistry",
    "KNOWN_BETA_GATES",
    "Operation",
    "PARAMETERIZED_GATES",
    "ParameterValue",
    "TWO_QUBIT_GATES",
    "default_gate_registry",
]
