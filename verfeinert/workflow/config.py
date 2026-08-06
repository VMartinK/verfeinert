"""Configuration records for public Verfeinert workflow orchestration."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from verfeinert.ansatz_analyzer import (
    AnalyzerExecutionPermissions,
    RankingConfig,
    StructuralCostConfig,
)
from verfeinert.core.config import ExecutionConfig
from verfeinert.core.io import ensure_output_root
from verfeinert.core.io.serialization import to_json_safe
from verfeinert.core.validation import (
    CoreValidationError,
    require_bool,
    require_identifier,
    require_non_negative_int_or_none,
    require_positive_int,
)


class WorkflowConfigError(CoreValidationError):
    """Raised when a workflow configuration cannot be normalized."""


SUPPORTED_GENERATION_FAMILIES = ("sanz19", "provided")
SUPPORTED_EVOLUTION_SELECTION_MODES = ("fitness", "pareto", "strict_pareto", "thresholds")
SUPPORTED_WORKFLOW_STAGES = ("generate", "analyze", "evolve", "rank")


@dataclass(frozen=True)
class GenerationStageConfig:
    """Configuration for candidate generation and staged-package export."""

    family: str = "sanz19"
    template_ids: tuple[str, ...] = ("A02",)
    layers: tuple[int, ...] = (1,)
    n_qubits: int = 4
    candidate_id_prefix: str = "workflow"
    package_id: str | None = None
    source_label: str = "verfeinert.workflow"
    created_at: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        family = _non_empty_text(self.family, "generation.family").lower()
        if family not in SUPPORTED_GENERATION_FAMILIES:
            raise WorkflowConfigError(
                f"generation.family must be one of {SUPPORTED_GENERATION_FAMILIES}.",
            )
        object.__setattr__(self, "family", family)
        template_ids = tuple(_non_empty_text(item, "generation.template_ids") for item in self.template_ids)
        if family == "sanz19" and not template_ids:
            raise WorkflowConfigError("sanz19 generation requires at least one template_id.")
        layers = tuple(int(layer) for layer in self.layers)
        if family == "sanz19" and (not layers or any(layer < 1 for layer in layers)):
            raise WorkflowConfigError("generation.layers must contain positive integers.")
        object.__setattr__(self, "template_ids", template_ids)
        object.__setattr__(self, "layers", layers)
        object.__setattr__(self, "n_qubits", require_positive_int(self.n_qubits, "generation.n_qubits"))
        object.__setattr__(
            self,
            "candidate_id_prefix",
            require_identifier(self.candidate_id_prefix, "generation.candidate_id_prefix"),
        )
        if self.package_id is not None:
            object.__setattr__(self, "package_id", require_identifier(self.package_id, "generation.package_id"))
        object.__setattr__(self, "source_label", _non_empty_text(self.source_label, "generation.source_label"))
        object.__setattr__(self, "metadata", to_json_safe(dict(self.metadata)))

    @classmethod
    def from_mapping(cls, mapping: Mapping[str, Any]) -> "GenerationStageConfig":
        """Build generation config from parsed YAML/Python data."""
        data = dict(mapping)
        return cls(
            family=data.get("family", "sanz19"),
            template_ids=tuple(data.get("template_ids", ("A02",))),
            layers=tuple(data.get("layers", (1,))),
            n_qubits=data.get("n_qubits", 4),
            candidate_id_prefix=data.get("candidate_id_prefix", "workflow"),
            package_id=data.get("package_id"),
            source_label=data.get("source_label", "verfeinert.workflow"),
            created_at=data.get("created_at"),
            metadata=dict(data.get("metadata", {})),
        )

    def to_dict(self) -> dict[str, Any]:
        """Return JSON-safe generation configuration."""
        return {
            "family": self.family,
            "template_ids": list(self.template_ids),
            "layers": list(self.layers),
            "n_qubits": self.n_qubits,
            "candidate_id_prefix": self.candidate_id_prefix,
            "package_id": self.package_id,
            "source_label": self.source_label,
            "created_at": self.created_at,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class AnalyzerStageConfig:
    """Configuration for analyzer execution and derived ranking."""

    selected_metrics: tuple[str, ...] = ("structural_cost",)
    structural_cost: StructuralCostConfig = field(default_factory=StructuralCostConfig)
    permissions: AnalyzerExecutionPermissions = field(default_factory=AnalyzerExecutionPermissions)
    metric_configs: dict[str, Any] = field(default_factory=dict)
    random_seed: int | None = None
    ranking: RankingConfig | None = None
    write_ranking: bool = True

    def __post_init__(self) -> None:
        metrics = tuple(_non_empty_text(metric, "analyzer.selected_metrics") for metric in self.selected_metrics)
        if not metrics:
            raise WorkflowConfigError("analyzer.selected_metrics must not be empty.")
        object.__setattr__(self, "selected_metrics", metrics)
        if not isinstance(self.structural_cost, StructuralCostConfig):
            raise WorkflowConfigError("analyzer.structural_cost must be StructuralCostConfig.")
        if not isinstance(self.permissions, AnalyzerExecutionPermissions):
            raise WorkflowConfigError("analyzer.permissions must be AnalyzerExecutionPermissions.")
        object.__setattr__(
            self,
            "random_seed",
            require_non_negative_int_or_none(self.random_seed, "analyzer.random_seed"),
        )
        object.__setattr__(self, "metric_configs", to_json_safe(dict(self.metric_configs)))
        object.__setattr__(self, "write_ranking", require_bool(self.write_ranking, "analyzer.write_ranking"))

    @classmethod
    def from_mapping(cls, mapping: Mapping[str, Any]) -> "AnalyzerStageConfig":
        """Build analyzer stage config from parsed YAML/Python data."""
        data = dict(mapping)
        structural = data.get("structural_cost", {})
        permissions = data.get("permissions", {})
        ranking = data.get("ranking")
        return cls(
            selected_metrics=tuple(data.get("selected_metrics", ("structural_cost",))),
            structural_cost=(
                structural
                if isinstance(structural, StructuralCostConfig)
                else StructuralCostConfig.from_mapping(structural)
            ),
            permissions=(
                permissions
                if isinstance(permissions, AnalyzerExecutionPermissions)
                else AnalyzerExecutionPermissions.from_mapping(permissions)
            ),
            metric_configs=dict(data.get("metric_configs", {})),
            random_seed=data.get("random_seed"),
            ranking=(
                ranking
                if isinstance(ranking, RankingConfig) or ranking is None
                else RankingConfig(**dict(ranking))
            ),
            write_ranking=data.get("write_ranking", True),
        )

    def to_dict(self) -> dict[str, Any]:
        """Return JSON-safe analyzer configuration."""
        return {
            "selected_metrics": list(self.selected_metrics),
            "structural_cost": self.structural_cost.to_dict(),
            "permissions": self.permissions.to_dict(),
            "metric_configs": to_json_safe(self.metric_configs),
            "random_seed": self.random_seed,
            "ranking": self.ranking.to_dict() if self.ranking is not None else None,
            "write_ranking": self.write_ranking,
        }


@dataclass(frozen=True)
class EvolutionStageConfig:
    """Configuration for evolver selection and EvolutionRun export."""

    selection_mode: str = "fitness"
    policy_id: str = "workflow-selection"
    metric_name: str = "structural_cost"
    keep: int = 1
    direction: str = "minimize"
    objectives: tuple[dict[str, str], ...] = (
        {"name": "structural_cost", "direction": "minimize"},
    )
    thresholds: dict[str, float] = field(default_factory=dict)
    threshold_direction: str = "at_most"
    max_generations: int = 1
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        mode = _non_empty_text(self.selection_mode, "evolver.selection_mode").lower()
        if mode not in SUPPORTED_EVOLUTION_SELECTION_MODES:
            raise WorkflowConfigError(
                f"evolver.selection_mode must be one of {SUPPORTED_EVOLUTION_SELECTION_MODES}.",
            )
        object.__setattr__(self, "selection_mode", mode)
        object.__setattr__(self, "policy_id", require_identifier(self.policy_id, "evolver.policy_id"))
        object.__setattr__(self, "metric_name", _non_empty_text(self.metric_name, "evolver.metric_name"))
        object.__setattr__(self, "keep", require_positive_int(self.keep, "evolver.keep"))
        if self.direction not in {"minimize", "maximize"}:
            raise WorkflowConfigError("evolver.direction must be minimize or maximize.")
        objectives = tuple(_objective_mapping(item) for item in self.objectives)
        if mode in {"pareto", "strict_pareto"} and not objectives:
            raise WorkflowConfigError("Pareto selection requires objectives.")
        object.__setattr__(self, "objectives", objectives)
        thresholds = {str(name): float(value) for name, value in self.thresholds.items()}
        object.__setattr__(self, "thresholds", thresholds)
        if self.threshold_direction not in {"at_most", "at_least"}:
            raise WorkflowConfigError("evolver.threshold_direction must be at_most or at_least.")
        object.__setattr__(
            self,
            "max_generations",
            require_positive_int(self.max_generations, "evolver.max_generations"),
        )
        object.__setattr__(self, "metadata", to_json_safe(dict(self.metadata)))

    @classmethod
    def from_mapping(cls, mapping: Mapping[str, Any]) -> "EvolutionStageConfig":
        """Build evolution stage config from parsed YAML/Python data."""
        data = dict(mapping)
        return cls(
            selection_mode=data.get("selection_mode", "fitness"),
            policy_id=data.get("policy_id", "workflow-selection"),
            metric_name=data.get("metric_name", "structural_cost"),
            keep=data.get("keep", 1),
            direction=data.get("direction", "minimize"),
            objectives=tuple(data.get("objectives", ({"name": "structural_cost", "direction": "minimize"},))),
            thresholds=dict(data.get("thresholds", {})),
            threshold_direction=data.get("threshold_direction", "at_most"),
            max_generations=data.get("max_generations", 1),
            metadata=dict(data.get("metadata", {})),
        )

    def to_dict(self) -> dict[str, Any]:
        """Return JSON-safe evolution configuration."""
        return {
            "selection_mode": self.selection_mode,
            "policy_id": self.policy_id,
            "metric_name": self.metric_name,
            "keep": self.keep,
            "direction": self.direction,
            "objectives": [dict(item) for item in self.objectives],
            "thresholds": dict(self.thresholds),
            "threshold_direction": self.threshold_direction,
            "max_generations": self.max_generations,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class WorkflowConfig:
    """Top-level configuration for one public workflow run."""

    run_id: str
    output_root: str | Path
    input_roots: tuple[str | Path, ...] = ()
    stages: tuple[str, ...] = ("generate", "analyze", "evolve", "rank")
    generation: GenerationStageConfig = field(default_factory=GenerationStageConfig)
    analyzer: AnalyzerStageConfig = field(default_factory=AnalyzerStageConfig)
    evolver: EvolutionStageConfig = field(default_factory=EvolutionStageConfig)
    execution: ExecutionConfig = field(default_factory=ExecutionConfig)
    random_seed: int | None = None
    created_at: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "run_id", require_identifier(self.run_id, "workflow.run_id"))
        output_root = ensure_output_root(self.output_root, input_roots=self.input_roots)
        object.__setattr__(self, "output_root", output_root)
        object.__setattr__(self, "input_roots", tuple(Path(root).expanduser() for root in self.input_roots))
        stages = tuple(_non_empty_text(stage, "workflow.stages").lower() for stage in self.stages)
        if any(stage not in SUPPORTED_WORKFLOW_STAGES for stage in stages):
            raise WorkflowConfigError(f"workflow.stages must be drawn from {SUPPORTED_WORKFLOW_STAGES}.")
        object.__setattr__(self, "stages", stages)
        if not isinstance(self.generation, GenerationStageConfig):
            raise WorkflowConfigError("generation must be GenerationStageConfig.")
        if not isinstance(self.analyzer, AnalyzerStageConfig):
            raise WorkflowConfigError("analyzer must be AnalyzerStageConfig.")
        if not isinstance(self.evolver, EvolutionStageConfig):
            raise WorkflowConfigError("evolver must be EvolutionStageConfig.")
        if not isinstance(self.execution, ExecutionConfig):
            raise WorkflowConfigError("execution must be ExecutionConfig.")
        object.__setattr__(
            self,
            "random_seed",
            require_non_negative_int_or_none(self.random_seed, "workflow.random_seed"),
        )
        object.__setattr__(self, "metadata", to_json_safe(dict(self.metadata)))

    @classmethod
    def from_mapping(cls, mapping: Mapping[str, Any]) -> "WorkflowConfig":
        """Build workflow config from a parsed mapping."""
        data = dict(mapping)
        run = dict(data.get("run", {}))
        paths = dict(data.get("paths", {}))
        execution = data.get("execution", {})
        return cls(
            run_id=run.get("run_id", data.get("run_id")),
            output_root=paths.get("output_root", data.get("output_root")),
            input_roots=tuple(paths.get("input_roots", data.get("input_roots", ()))),
            stages=tuple(data.get("stages", ("generate", "analyze", "evolve", "rank"))),
            generation=GenerationStageConfig.from_mapping(data.get("generation", data.get("candidate_generation", {}))),
            analyzer=AnalyzerStageConfig.from_mapping(data.get("analyzer", {})),
            evolver=EvolutionStageConfig.from_mapping(data.get("evolver", {})),
            execution=(
                execution
                if isinstance(execution, ExecutionConfig)
                else ExecutionConfig.from_mapping(dict(execution))
            ),
            random_seed=run.get("random_seed", data.get("random_seed")),
            created_at=run.get("created_at", data.get("created_at")),
            metadata=dict(data.get("metadata", {})),
        )

    def to_dict(self) -> dict[str, Any]:
        """Return JSON-safe workflow configuration."""
        return {
            "run": {
                "run_id": self.run_id,
                "random_seed": self.random_seed,
                "created_at": self.created_at,
            },
            "paths": {
                "output_root": str(self.output_root),
                "input_roots": [str(path) for path in self.input_roots],
            },
            "stages": list(self.stages),
            "generation": self.generation.to_dict(),
            "analyzer": self.analyzer.to_dict(),
            "evolver": self.evolver.to_dict(),
            "execution": self.execution.to_dict(),
            "metadata": dict(self.metadata),
        }


def _non_empty_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WorkflowConfigError(f"{field_name} must be a non-empty string.")
    return value.strip()


def _objective_mapping(value: Mapping[str, Any]) -> dict[str, str]:
    data = dict(value)
    name = _non_empty_text(data.get("name"), "objective.name")
    direction = _non_empty_text(data.get("direction", "minimize"), "objective.direction")
    if direction not in {"minimize", "maximize"}:
        raise WorkflowConfigError("objective.direction must be minimize or maximize.")
    return {"name": name, "direction": direction}


__all__ = [
    "AnalyzerStageConfig",
    "EvolutionStageConfig",
    "GenerationStageConfig",
    "SUPPORTED_EVOLUTION_SELECTION_MODES",
    "SUPPORTED_GENERATION_FAMILIES",
    "SUPPORTED_WORKFLOW_STAGES",
    "WorkflowConfig",
    "WorkflowConfigError",
]
