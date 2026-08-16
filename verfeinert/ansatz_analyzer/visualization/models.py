"""Semantic visualization models for already-derived analyzer artifacts."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
import math
from types import MappingProxyType
from typing import Any

from verfeinert.core.io.serialization import to_json_safe


class VisualizationModelError(ValueError):
    """Raised when a semantic visualization model is malformed."""


@dataclass(frozen=True)
class ObjectivePoint:
    """One already-classified point in objective space."""

    candidate_id: str
    x: float
    y: float
    display_label: str | None = None
    role: str = "candidate"
    layer: int | None = None
    lineage_id: str | None = None
    generation: int | None = None
    score: float | None = None
    structural_cost: float | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "candidate_id", _required_text(self.candidate_id, "candidate_id"))
        object.__setattr__(self, "x", _finite_float(self.x, "x"))
        object.__setattr__(self, "y", _finite_float(self.y, "y"))
        object.__setattr__(self, "display_label", _optional_text(self.display_label, "display_label"))
        object.__setattr__(self, "role", _required_text(self.role, "role"))
        object.__setattr__(self, "layer", _optional_int(self.layer, "layer"))
        object.__setattr__(self, "lineage_id", _optional_text(self.lineage_id, "lineage_id"))
        object.__setattr__(self, "generation", _optional_int(self.generation, "generation"))
        object.__setattr__(self, "score", _optional_float(self.score, "score"))
        object.__setattr__(self, "structural_cost", _optional_float(self.structural_cost, "structural_cost"))
        object.__setattr__(self, "metadata", _immutable_mapping(self.metadata, "metadata"))

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe semantic point payload."""
        return to_json_safe(self)


@dataclass(frozen=True)
class ObjectiveSeries:
    """A visual objective-space series with caller-supplied semantics."""

    points: tuple[ObjectivePoint, ...] = ()
    role: str = "series"
    label: str | None = None
    threshold: float | None = None
    generation: int | None = None
    source_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "points", tuple(_objective_point(item) for item in self.points))
        object.__setattr__(self, "role", _required_text(self.role, "role"))
        object.__setattr__(self, "label", _optional_text(self.label, "label"))
        object.__setattr__(self, "threshold", _optional_float(self.threshold, "threshold"))
        object.__setattr__(self, "generation", _optional_int(self.generation, "generation"))
        object.__setattr__(self, "source_id", _optional_text(self.source_id, "source_id"))

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe semantic series payload."""
        return to_json_safe(self)


@dataclass(frozen=True)
class MetricSeries:
    """A generic metric series with aligned x and y values."""

    x: tuple[Any, ...]
    y: tuple[float | None, ...]
    role: str = "metric"
    label: str | None = None
    threshold: float | None = None

    def __post_init__(self) -> None:
        x_values = _immutable_sequence(self.x, "x")
        y_values = tuple(_optional_float(value, "y") for value in self.y)
        if len(x_values) != len(y_values):
            raise VisualizationModelError("x and y must have the same length.")
        object.__setattr__(self, "x", x_values)
        object.__setattr__(self, "y", y_values)
        object.__setattr__(self, "role", _required_text(self.role, "role"))
        object.__setattr__(self, "label", _optional_text(self.label, "label"))
        object.__setattr__(self, "threshold", _optional_float(self.threshold, "threshold"))

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe metric series payload."""
        return to_json_safe(self)


@dataclass(frozen=True)
class BarSeries:
    """A generic categorical bar series."""

    categories: tuple[str, ...]
    values: tuple[float | None, ...]
    role: str = "bar"
    label: str | None = None

    def __post_init__(self) -> None:
        categories = tuple(_required_text(category, "categories") for category in self.categories)
        values = tuple(_optional_float(value, "values") for value in self.values)
        if len(categories) != len(values):
            raise VisualizationModelError("categories and values must have the same length.")
        object.__setattr__(self, "categories", categories)
        object.__setattr__(self, "values", values)
        object.__setattr__(self, "role", _required_text(self.role, "role"))
        object.__setattr__(self, "label", _optional_text(self.label, "label"))

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe bar series payload."""
        return to_json_safe(self)


@dataclass(frozen=True)
class TableSpec:
    """A generic table specification for publication renderers."""

    columns: tuple[str, ...]
    rows: tuple[Mapping[str, Any] | tuple[Any, ...], ...]

    def __post_init__(self) -> None:
        columns = tuple(_required_text(column, "columns") for column in self.columns)
        rows = tuple(_immutable_row(row, "rows") for row in self.rows)
        object.__setattr__(self, "columns", columns)
        object.__setattr__(self, "rows", rows)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe table payload."""
        return to_json_safe(self)


def _objective_point(value: ObjectivePoint | Mapping[str, Any]) -> ObjectivePoint:
    if isinstance(value, ObjectivePoint):
        return value
    if isinstance(value, Mapping):
        return ObjectivePoint(**dict(value))
    raise VisualizationModelError("points must contain ObjectivePoint instances or mappings.")


def _required_text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise VisualizationModelError(f"{field_name} must be a non-empty string.")
    return value.strip()


def _optional_text(value: Any, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise VisualizationModelError(f"{field_name} must be None or a non-empty string.")
    return value.strip()


def _finite_float(value: Any, field_name: str) -> float:
    numeric = float(value)
    if not math.isfinite(numeric):
        raise VisualizationModelError(f"{field_name} must be finite.")
    return numeric


def _optional_float(value: Any, field_name: str) -> float | None:
    if value is None:
        return None
    return _finite_float(value, field_name)


def _optional_int(value: Any, field_name: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise VisualizationModelError(f"{field_name} must be an integer or None.")
    return int(value)


def _immutable_mapping(value: Mapping[str, Any], field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise VisualizationModelError(f"{field_name} must be a mapping.")
    return _freeze_json_safe(dict(value))


def _immutable_sequence(value: Sequence[Any], field_name: str) -> tuple[Any, ...]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise VisualizationModelError(f"{field_name} must be a sequence.")
    return tuple(_freeze_json_safe(item) for item in value)


def _immutable_row(value: Mapping[str, Any] | Sequence[Any], field_name: str) -> Mapping[str, Any] | tuple[Any, ...]:
    if isinstance(value, Mapping):
        return _freeze_json_safe(dict(value))
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise VisualizationModelError(f"{field_name} entries must be mappings or sequences.")
    return tuple(_freeze_json_safe(item) for item in value)


def _freeze_json_safe(value: Any) -> Any:
    safe_value = to_json_safe(value)
    if isinstance(safe_value, Mapping):
        return MappingProxyType(
            {str(key): _freeze_json_safe(item) for key, item in safe_value.items()},
        )
    if isinstance(safe_value, Sequence) and not isinstance(safe_value, (str, bytes, bytearray)):
        return tuple(_freeze_json_safe(item) for item in safe_value)
    return safe_value


__all__ = [
    "BarSeries",
    "MetricSeries",
    "ObjectivePoint",
    "ObjectiveSeries",
    "TableSpec",
    "VisualizationModelError",
]
