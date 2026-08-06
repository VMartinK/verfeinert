"""Configuration records for JSON-first ansatz evolution."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from verfeinert.core.config import ExecutionConfig
from verfeinert.core.io import ensure_output_root
from verfeinert.core.validation import (
    CoreValidationError,
    require_bool,
    require_non_negative_int_or_none,
    require_positive_int,
)

from .models import require_identifier, require_mapping


@dataclass(frozen=True)
class EvolverExecutionPermissions:
    """Execution permissions for the evolver boundary."""

    allow_metric_execution: bool = False
    allow_qnode_execution: bool = False
    allow_visualization: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "allow_metric_execution",
            require_bool(self.allow_metric_execution, "allow_metric_execution"),
        )
        object.__setattr__(
            self,
            "allow_qnode_execution",
            require_bool(self.allow_qnode_execution, "allow_qnode_execution"),
        )
        object.__setattr__(
            self,
            "allow_visualization",
            require_bool(self.allow_visualization, "allow_visualization"),
        )
        if self.allow_metric_execution or self.allow_qnode_execution:
            raise CoreValidationError("The evolver never executes metrics or QNodes.")
        if self.allow_visualization:
            raise CoreValidationError("The evolver foundation does not generate plots.")

    def to_dict(self) -> dict[str, bool]:
        """Return JSON-safe execution permissions."""
        return {
            "allow_metric_execution": self.allow_metric_execution,
            "allow_qnode_execution": self.allow_qnode_execution,
            "allow_visualization": self.allow_visualization,
        }


@dataclass(frozen=True)
class EvolverConfig:
    """Top-level configuration snapshot for an evolution run."""

    run_id: str
    output_root: str | Path
    input_roots: tuple[str | Path, ...] = ()
    random_seed: int | None = None
    max_generations: int = 1
    requested_metrics: tuple[str, ...] = ("structural_cost",)
    execution: ExecutionConfig = field(default_factory=ExecutionConfig)
    permissions: EvolverExecutionPermissions = field(default_factory=EvolverExecutionPermissions)
    mutation_policy: dict[str, Any] = field(default_factory=dict)
    selection_policy: dict[str, Any] = field(default_factory=dict)
    stopping_policy: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "run_id", require_identifier(self.run_id, "run_id"))
        object.__setattr__(
            self,
            "random_seed",
            require_non_negative_int_or_none(self.random_seed, "random_seed"),
        )
        object.__setattr__(
            self,
            "max_generations",
            require_positive_int(self.max_generations, "max_generations"),
        )
        if not isinstance(self.execution, ExecutionConfig):
            raise CoreValidationError("execution must be an ExecutionConfig.")
        if not isinstance(self.permissions, EvolverExecutionPermissions):
            raise CoreValidationError("permissions must be EvolverExecutionPermissions.")
        metrics = tuple(str(metric).strip() for metric in self.requested_metrics)
        if any(not metric for metric in metrics):
            raise CoreValidationError("requested_metrics must not contain empty names.")
        object.__setattr__(self, "requested_metrics", metrics)
        output_root = ensure_output_root(self.output_root, input_roots=self.input_roots)
        object.__setattr__(self, "output_root", output_root)
        object.__setattr__(self, "input_roots", tuple(Path(root).expanduser() for root in self.input_roots))
        object.__setattr__(self, "mutation_policy", require_mapping(self.mutation_policy, "mutation_policy"))
        object.__setattr__(self, "selection_policy", require_mapping(self.selection_policy, "selection_policy"))
        object.__setattr__(self, "stopping_policy", require_mapping(self.stopping_policy, "stopping_policy"))
        object.__setattr__(self, "metadata", require_mapping(self.metadata, "metadata"))

    @classmethod
    def from_mapping(cls, mapping: Mapping[str, Any]) -> "EvolverConfig":
        """Build an evolver config from a parsed mapping."""
        data = require_mapping(mapping, "evolver_config")
        execution_payload = data.get("execution", {})
        permissions_payload = data.get("permissions", {})
        return cls(
            run_id=data.get("run_id"),  # type: ignore[arg-type]
            output_root=data.get("output_root"),  # type: ignore[arg-type]
            input_roots=tuple(data.get("input_roots", ())),  # type: ignore[arg-type]
            random_seed=data.get("random_seed"),  # type: ignore[arg-type]
            max_generations=data.get("max_generations", 1),  # type: ignore[arg-type]
            requested_metrics=tuple(data.get("requested_metrics", ("structural_cost",))),  # type: ignore[arg-type]
            execution=ExecutionConfig.from_mapping(dict(execution_payload)),  # type: ignore[arg-type]
            permissions=EvolverExecutionPermissions(**dict(permissions_payload)),  # type: ignore[arg-type]
            mutation_policy=dict(data.get("mutation_policy", {})),  # type: ignore[arg-type]
            selection_policy=dict(data.get("selection_policy", {})),  # type: ignore[arg-type]
            stopping_policy=dict(data.get("stopping_policy", {})),  # type: ignore[arg-type]
            metadata=dict(data.get("metadata", {})),  # type: ignore[arg-type]
        )

    def to_evolution_configuration(self) -> dict[str, Any]:
        """Return the configuration object stored in EvolutionRun JSON."""
        return {
            "random_seed": self.random_seed,
            "execution": self.execution.to_dict(),
            "mutation_policy": {
                **self.mutation_policy,
                "requested_metrics": list(self.requested_metrics),
            },
            "selection_policy": dict(self.selection_policy),
            "stopping_policy": {
                **self.stopping_policy,
                "max_generations": self.max_generations,
            },
        }

    def to_dict(self) -> dict[str, Any]:
        """Return a complete JSON-safe config snapshot."""
        return {
            "run_id": self.run_id,
            "output_root": str(self.output_root),
            "input_roots": [str(root) for root in self.input_roots],
            "random_seed": self.random_seed,
            "max_generations": self.max_generations,
            "requested_metrics": list(self.requested_metrics),
            "execution": self.execution.to_dict(),
            "permissions": self.permissions.to_dict(),
            "mutation_policy": dict(self.mutation_policy),
            "selection_policy": dict(self.selection_policy),
            "stopping_policy": dict(self.stopping_policy),
            "metadata": dict(self.metadata),
        }


__all__ = [
    "EvolverConfig",
    "EvolverExecutionPermissions",
]
