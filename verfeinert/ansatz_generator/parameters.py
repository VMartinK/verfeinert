"""Parameter records and stable trainable-parameter mappings."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from verfeinert.core.validation import require_non_empty_text

from .validation import GeneratorValidationError


@dataclass(frozen=True)
class Parameter:
    """Named trainable parameter placeholder."""

    name: str
    index: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", require_non_empty_text(self.name, "parameter.name"))
        if type(self.index) is not int or self.index < 0:
            raise GeneratorValidationError("parameter.index must be a non-negative integer.")


@dataclass
class ParameterMap:
    """Stable first-appearance mapping from symbolic names to vector indices."""

    parameter_names: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        seen: set[str] = set()
        normalized: list[str] = []
        for name in self.parameter_names:
            text = require_non_empty_text(name, "parameter name")
            if text in seen:
                raise GeneratorValidationError("duplicated parameter names in explicit map.")
            seen.add(text)
            normalized.append(text)
        self.parameter_names = normalized
        self._rebuild()

    def _rebuild(self) -> None:
        self.name_to_index = {name: index for index, name in enumerate(self.parameter_names)}
        self.index_to_name = {index: name for index, name in enumerate(self.parameter_names)}

    def add(self, name: str) -> int:
        """Add a symbolic parameter if missing and return its vector index."""
        text = require_non_empty_text(name, "parameter name")
        if text in self.name_to_index:
            return self.name_to_index[text]
        self.parameter_names.append(text)
        self._rebuild()
        return self.name_to_index[text]

    def extend(self, names: Iterable[str]) -> None:
        """Add several names while preserving first-appearance order."""
        for name in names:
            self.add(name)

    def get_index(self, name: str) -> int:
        """Return the vector index for ``name``."""
        text = require_non_empty_text(name, "parameter name")
        if text not in self.name_to_index:
            raise KeyError(text)
        return self.name_to_index[text]

    def get_name(self, index: int) -> str:
        """Return the parameter name for ``index``."""
        if type(index) is not int:
            raise TypeError("index must be an integer.")
        if index not in self.index_to_name:
            raise KeyError(index)
        return self.index_to_name[index]

    @classmethod
    def from_names(cls, names: Iterable[str]) -> "ParameterMap":
        """Build a map where repeated names represent shared parameters."""
        parameter_map = cls()
        parameter_map.extend(names)
        return parameter_map

    @classmethod
    def from_operations(cls, operations: Iterable[Any]) -> "ParameterMap":
        """Build a map from operation-like objects exposing trainable names."""
        parameter_map = cls()
        for operation in operations:
            names = getattr(operation, "trainable_parameter_names", None)
            if names is None:
                params = getattr(operation, "parameters", getattr(operation, "params", ()))
                names = tuple(item for item in params if isinstance(item, str))
            parameter_map.extend(names)
        return parameter_map

    def to_dict(self) -> dict[str, Any]:
        """Serialize as a JSON-safe mapping."""
        return {
            "parameter_names": list(self.parameter_names),
            "name_to_index": dict(self.name_to_index),
            "index_to_name": {str(key): value for key, value in self.index_to_name.items()},
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ParameterMap":
        """Reconstruct from ``to_dict`` output."""
        if "parameter_names" not in data:
            raise KeyError("parameter_names")
        return cls(parameter_names=list(data["parameter_names"]))

    def as_tuple(self) -> tuple[str, ...]:
        """Return names in vector-index order."""
        return tuple(self.parameter_names)

    def __len__(self) -> int:
        return len(self.parameter_names)

    def __contains__(self, name: str) -> bool:
        return name in self.name_to_index

    def __iter__(self):
        return iter(self.parameter_names)


__all__ = ["Parameter", "ParameterMap"]
