"""Configuration records for the analyzer foundation layer."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
import math
from pathlib import Path
from typing import Any

from verfeinert.core.config import ExecutionConfig
from verfeinert.core.io.paths import validate_separate_roots
from verfeinert.core.io.serialization import to_json_safe
from verfeinert.core.validation import (
    CoreValidationError,
    require_bool,
    require_identifier,
    require_non_empty_text,
    require_non_negative_int_or_none,
)


FOUNDATION_METRICS = ("structural_cost",)
EXPENSIVE_METRICS = ("expressibility", "trainability")
DERIVED_ANALYSES = ("pareto_front", "ranking")
SUPPORTED_METRICS = FOUNDATION_METRICS + EXPENSIVE_METRICS
DEFERRED_METRICS = DERIVED_ANALYSES
STRUCTURAL_COST_COMPONENTS = (
    "parameter_count",
    "depth",
    "two_qubit_operation_count",
)
SUPPORTED_MATERIALIZATION_BACKENDS = ("pennylane",)


class AnalyzerConfigError(CoreValidationError):
    """Raised when analyzer configuration violates the foundation contract."""


@dataclass(frozen=True)
class AnalyzerExecutionPermissions:
    """Explicit permissions for analyzer work that may execute expensive code."""

    allow_qnode_execution: bool = False
    allow_expensive_metrics: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "allow_qnode_execution",
            require_bool(
                self.allow_qnode_execution,
                "permissions.allow_qnode_execution",
            ),
        )
        object.__setattr__(
            self,
            "allow_expensive_metrics",
            require_bool(
                self.allow_expensive_metrics,
                "permissions.allow_expensive_metrics",
            ),
        )

    @classmethod
    def from_mapping(
        cls,
        mapping: Mapping[str, object],
    ) -> "AnalyzerExecutionPermissions":
        """Build permissions from a parsed mapping."""
        data = dict(mapping)
        return cls(
            allow_qnode_execution=data.get("allow_qnode_execution", False),  # type: ignore[arg-type]
            allow_expensive_metrics=data.get("allow_expensive_metrics", False),  # type: ignore[arg-type]
        )

    def to_dict(self) -> dict[str, bool]:
        """Return a JSON-safe permissions record."""
        return {
            "allow_qnode_execution": self.allow_qnode_execution,
            "allow_expensive_metrics": self.allow_expensive_metrics,
        }


@dataclass(frozen=True)
class StructuralCostConfig:
    """Configuration for record-based structural-cost computation."""

    reference_id: str = "selected_candidates"
    reference_bounds: Mapping[str, object] | None = None
    component_weights: Mapping[str, float] | None = None
    allow_operation_count_as_depth_proxy: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "reference_id",
            require_non_empty_text(self.reference_id, "structural_cost.reference_id"),
        )
        object.__setattr__(
            self,
            "allow_operation_count_as_depth_proxy",
            require_bool(
                self.allow_operation_count_as_depth_proxy,
                "structural_cost.allow_operation_count_as_depth_proxy",
            ),
        )
        object.__setattr__(
            self,
            "reference_bounds",
            _clean_reference_bounds(self.reference_bounds),
        )
        object.__setattr__(
            self,
            "component_weights",
            _clean_component_weights(self.component_weights),
        )

    @classmethod
    def from_mapping(cls, mapping: Mapping[str, object]) -> "StructuralCostConfig":
        """Build structural-cost config from a parsed mapping."""
        data = dict(mapping)
        return cls(
            reference_id=data.get("reference_id", "selected_candidates"),  # type: ignore[arg-type]
            reference_bounds=data.get("reference_bounds"),  # type: ignore[arg-type]
            component_weights=data.get("component_weights"),  # type: ignore[arg-type]
            allow_operation_count_as_depth_proxy=data.get(
                "allow_operation_count_as_depth_proxy",
                True,
            ),  # type: ignore[arg-type]
        )

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe structural-cost config snapshot."""
        return {
            "reference_id": self.reference_id,
            "reference_bounds": to_json_safe(self.reference_bounds),
            "component_weights": to_json_safe(self.component_weights),
            "allow_operation_count_as_depth_proxy": (
                self.allow_operation_count_as_depth_proxy
            ),
        }


@dataclass(frozen=True)
class CircuitMaterializationConfig:
    """Configuration for analyzer-owned executable circuit materialization."""

    enabled: bool = False
    backend: str = "pennylane"
    device: str = "default.qubit"
    interface: str = "autograd"
    diff_method: str = "best"

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "enabled",
            require_bool(self.enabled, "materialization.enabled"),
        )
        backend = require_non_empty_text(self.backend, "materialization.backend").lower()
        if backend not in SUPPORTED_MATERIALIZATION_BACKENDS:
            raise AnalyzerConfigError(
                "materialization.backend must be one of "
                f"{SUPPORTED_MATERIALIZATION_BACKENDS}.",
            )
        object.__setattr__(self, "backend", backend)
        object.__setattr__(
            self,
            "device",
            require_non_empty_text(self.device, "materialization.device"),
        )
        object.__setattr__(
            self,
            "interface",
            require_non_empty_text(self.interface, "materialization.interface"),
        )
        object.__setattr__(
            self,
            "diff_method",
            require_non_empty_text(self.diff_method, "materialization.diff_method"),
        )

    @classmethod
    def from_mapping(
        cls,
        mapping: Mapping[str, object],
    ) -> "CircuitMaterializationConfig":
        """Build materialization config from a parsed mapping."""
        data = dict(mapping)
        return cls(
            enabled=data.get("enabled", False),  # type: ignore[arg-type]
            backend=data.get("backend", "pennylane"),  # type: ignore[arg-type]
            device=data.get("device", "default.qubit"),  # type: ignore[arg-type]
            interface=data.get("interface", "autograd"),  # type: ignore[arg-type]
            diff_method=data.get("diff_method", "best"),  # type: ignore[arg-type]
        )

    def to_dict(self) -> dict[str, Any]:
        """Return JSON-safe materialization configuration."""
        return {
            "enabled": self.enabled,
            "backend": self.backend,
            "device": self.device,
            "interface": self.interface,
            "diff_method": self.diff_method,
        }


@dataclass(frozen=True)
class AnalyzerConfig:
    """Validated configuration for analyzer foundation runs."""

    run_id: str
    input_roots: Iterable[str | Path]
    output_root: str | Path
    selected_metrics: Iterable[str] = FOUNDATION_METRICS
    execution: ExecutionConfig = field(default_factory=ExecutionConfig)
    permissions: AnalyzerExecutionPermissions = field(
        default_factory=AnalyzerExecutionPermissions,
    )
    random_seed: int | None = None
    structural_cost: StructuralCostConfig = field(default_factory=StructuralCostConfig)
    metric_configs: Mapping[str, object] = field(default_factory=dict)
    materialization: CircuitMaterializationConfig = field(
        default_factory=CircuitMaterializationConfig,
    )

    def __post_init__(self) -> None:
        run_id = require_identifier(self.run_id, "run_id")
        input_roots = _normalize_input_roots(self.input_roots)
        output_root = _normalize_path(self.output_root, "output_root")
        for input_root in input_roots:
            validate_separate_roots(input_root=input_root, output_root=output_root)

        if not isinstance(self.execution, ExecutionConfig):
            raise AnalyzerConfigError("execution must be an ExecutionConfig.")
        if not isinstance(self.permissions, AnalyzerExecutionPermissions):
            raise AnalyzerConfigError(
                "permissions must be an AnalyzerExecutionPermissions.",
            )
        if not isinstance(self.structural_cost, StructuralCostConfig):
            raise AnalyzerConfigError("structural_cost must be a StructuralCostConfig.")
        if not isinstance(self.materialization, CircuitMaterializationConfig):
            raise AnalyzerConfigError(
                "materialization must be a CircuitMaterializationConfig.",
            )
        selected_metrics = _normalize_selected_metrics(self.selected_metrics)
        expensive = [metric for metric in selected_metrics if metric in EXPENSIVE_METRICS]
        if expensive and not self.permissions.allow_expensive_metrics:
            raise AnalyzerConfigError(
                "Expensive analyzer metrics require "
                "permissions.allow_expensive_metrics=True; "
                f"requested: {expensive}."
            )
        random_seed = require_non_negative_int_or_none(self.random_seed, "random_seed")
        metric_configs = _clean_metric_configs(self.metric_configs)

        object.__setattr__(self, "run_id", run_id)
        object.__setattr__(self, "input_roots", input_roots)
        object.__setattr__(self, "output_root", output_root)
        object.__setattr__(self, "selected_metrics", selected_metrics)
        object.__setattr__(self, "random_seed", random_seed)
        object.__setattr__(self, "metric_configs", metric_configs)

    @classmethod
    def from_mapping(cls, mapping: Mapping[str, object]) -> "AnalyzerConfig":
        """Build analyzer configuration from a parsed mapping."""
        data = dict(mapping)
        if "run_id" not in data:
            raise AnalyzerConfigError("run_id is required.")
        if "input_roots" not in data:
            raise AnalyzerConfigError("input_roots is required.")
        if "output_root" not in data:
            raise AnalyzerConfigError("output_root is required.")
        execution = data.get("execution", ExecutionConfig())
        permissions = data.get("permissions", AnalyzerExecutionPermissions())
        structural_cost = data.get("structural_cost", StructuralCostConfig())
        materialization = data.get("materialization", CircuitMaterializationConfig())
        return cls(
            run_id=data["run_id"],  # type: ignore[arg-type]
            input_roots=data["input_roots"],  # type: ignore[arg-type]
            output_root=data["output_root"],  # type: ignore[arg-type]
            selected_metrics=data.get("selected_metrics", FOUNDATION_METRICS),  # type: ignore[arg-type]
            execution=(
                execution
                if isinstance(execution, ExecutionConfig)
                else ExecutionConfig.from_mapping(execution)  # type: ignore[arg-type]
            ),
            permissions=(
                permissions
                if isinstance(permissions, AnalyzerExecutionPermissions)
                else AnalyzerExecutionPermissions.from_mapping(permissions)  # type: ignore[arg-type]
            ),
            random_seed=data.get("random_seed"),  # type: ignore[arg-type]
            structural_cost=(
                structural_cost
                if isinstance(structural_cost, StructuralCostConfig)
                else StructuralCostConfig.from_mapping(structural_cost)  # type: ignore[arg-type]
            ),
            metric_configs=data.get("metric_configs", {}),  # type: ignore[arg-type]
            materialization=(
                materialization
                if isinstance(materialization, CircuitMaterializationConfig)
                else CircuitMaterializationConfig.from_mapping(materialization)  # type: ignore[arg-type]
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe effective analyzer configuration."""
        return {
            "run_id": self.run_id,
            "input_roots": [str(path) for path in self.input_roots],
            "output_root": str(self.output_root),
            "selected_metrics": list(self.selected_metrics),
            "execution": self.execution.to_dict(),
            "permissions": self.permissions.to_dict(),
            "random_seed": self.random_seed,
            "structural_cost": self.structural_cost.to_dict(),
            "metric_configs": to_json_safe(self.metric_configs),
            "materialization": self.materialization.to_dict(),
        }


def _normalize_input_roots(value: Iterable[str | Path] | str | Path) -> tuple[Path, ...]:
    if isinstance(value, (str, Path)):
        items = (value,)
    else:
        items = tuple(value)
    if not items:
        raise AnalyzerConfigError("input_roots must contain at least one path.")
    return tuple(_normalize_path(item, "input_roots") for item in items)


def _normalize_path(value: str | Path, field_name: str) -> Path:
    if isinstance(value, Path):
        path = value
    elif isinstance(value, str) and value.strip():
        path = Path(value)
    else:
        raise AnalyzerConfigError(f"{field_name} must be a non-empty path.")
    return path.expanduser().resolve(strict=False)


def _normalize_selected_metrics(value: Iterable[str] | str) -> tuple[str, ...]:
    metrics = (value,) if isinstance(value, str) else tuple(value)
    if not metrics:
        raise AnalyzerConfigError("selected_metrics must not be empty.")
    normalized = tuple(
        require_non_empty_text(metric, "selected_metrics").lower()
        for metric in metrics
    )
    duplicates = sorted({metric for metric in normalized if normalized.count(metric) > 1})
    if duplicates:
        raise AnalyzerConfigError(f"selected_metrics contains duplicates: {duplicates}")
    deferred = [metric for metric in normalized if metric in DERIVED_ANALYSES]
    if deferred:
        raise AnalyzerConfigError(
            "Pareto and ranking are derived analyses, not selected metrics; "
            f"requested: {deferred}."
        )
    unsupported = sorted(set(normalized) - set(SUPPORTED_METRICS))
    if unsupported:
        raise AnalyzerConfigError(f"Unsupported analyzer metrics: {unsupported}")
    return normalized


def _clean_metric_configs(configs: Mapping[str, object]) -> dict[str, object]:
    if not isinstance(configs, Mapping):
        raise AnalyzerConfigError("metric_configs must be a mapping.")
    unknown = sorted(set(str(key) for key in configs) - set(SUPPORTED_METRICS))
    if unknown:
        raise AnalyzerConfigError(f"metric_configs contains unknown metrics: {unknown}")
    cleaned: dict[str, object] = {}
    for key, value in configs.items():
        if value is None:
            cleaned[str(key)] = {}
        elif isinstance(value, Mapping):
            cleaned[str(key)] = to_json_safe(dict(value))
        else:
            raise AnalyzerConfigError(f"metric_configs[{key!r}] must be a mapping.")
    return cleaned


def _clean_component_weights(
    weights: Mapping[str, float] | None,
) -> dict[str, float]:
    cleaned = {component: 1.0 for component in STRUCTURAL_COST_COMPONENTS}
    if weights is None:
        return cleaned
    if not isinstance(weights, Mapping):
        raise AnalyzerConfigError("component_weights must be a mapping.")
    unknown = sorted(set(str(key) for key in weights) - set(STRUCTURAL_COST_COMPONENTS))
    if unknown:
        raise AnalyzerConfigError(f"Unknown structural-cost components: {unknown}")
    for key, value in weights.items():
        if type(value) not in {int, float}:
            raise AnalyzerConfigError(f"component weight {key!r} must be numeric.")
        numeric = float(value)
        if not math.isfinite(numeric) or numeric < 0.0:
            raise AnalyzerConfigError(
                f"component weight {key!r} must be finite and non-negative.",
            )
        cleaned[str(key)] = numeric
    if sum(cleaned.values()) <= 0.0:
        raise AnalyzerConfigError("component_weights must sum to a positive value.")
    return cleaned


def _clean_reference_bounds(
    bounds: Mapping[str, object] | None,
) -> dict[str, dict[str, float]] | None:
    if bounds is None:
        return None
    if not isinstance(bounds, Mapping):
        raise AnalyzerConfigError("reference_bounds must be a mapping.")
    payload = bounds.get("components", bounds)
    if not isinstance(payload, Mapping):
        raise AnalyzerConfigError("reference_bounds.components must be a mapping.")
    missing = sorted(set(STRUCTURAL_COST_COMPONENTS) - set(str(key) for key in payload))
    if missing:
        raise AnalyzerConfigError(f"reference_bounds missing components: {missing}")
    cleaned: dict[str, dict[str, float]] = {}
    for component in STRUCTURAL_COST_COMPONENTS:
        item = payload[component]
        if not isinstance(item, Mapping) or "min" not in item or "max" not in item:
            raise AnalyzerConfigError(
                f"reference_bounds[{component!r}] must contain min and max.",
            )
        lower = _finite_float(item["min"], f"reference_bounds.{component}.min")
        upper = _finite_float(item["max"], f"reference_bounds.{component}.max")
        cleaned[component] = {"min": lower, "max": upper}
    return cleaned


def _finite_float(value: object, field_name: str) -> float:
    if type(value) not in {int, float}:
        raise AnalyzerConfigError(f"{field_name} must be numeric.")
    numeric = float(value)
    if not math.isfinite(numeric):
        raise AnalyzerConfigError(f"{field_name} must be finite.")
    return numeric


__all__ = [
    "AnalyzerConfig",
    "AnalyzerConfigError",
    "AnalyzerExecutionPermissions",
    "CircuitMaterializationConfig",
    "DEFERRED_METRICS",
    "DERIVED_ANALYSES",
    "EXPENSIVE_METRICS",
    "FOUNDATION_METRICS",
    "STRUCTURAL_COST_COMPONENTS",
    "StructuralCostConfig",
    "SUPPORTED_METRICS",
    "SUPPORTED_MATERIALIZATION_BACKENDS",
]
