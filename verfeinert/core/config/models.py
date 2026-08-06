"""Typed configuration records for Verfeinert public APIs."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from verfeinert.core.io.paths import validate_separate_roots
from verfeinert.core.schemas import RUN_CONFIG_SCHEMA_VERSION
from verfeinert.core.validation import (
    CoreValidationError,
    require_bool,
    require_identifier,
    require_mapping,
    require_non_empty_text,
    require_non_negative_int_or_none,
    require_positive_int,
    require_supported_value,
)


ExecutionMode = Literal["sequential", "multiprocessing"]
ExecutionScope = Literal["candidate"]

SUPPORTED_EXECUTION_MODES: tuple[ExecutionMode, ...] = ("sequential", "multiprocessing")
SUPPORTED_EXECUTION_SCOPES: tuple[ExecutionScope, ...] = ("candidate",)


@dataclass(frozen=True)
class ExecutionConfig:
    """Executor settings shared by generator, analyzer, and evolver workflows."""

    mode: ExecutionMode = "sequential"
    parallelize_candidates: bool = False
    worker_count: int = 1
    scope: ExecutionScope = "candidate"

    def __post_init__(self) -> None:
        mode = require_non_empty_text(self.mode, "execution.mode").lower()
        mode = require_supported_value(mode, "execution.mode", SUPPORTED_EXECUTION_MODES)
        scope = require_non_empty_text(self.scope, "execution.scope").lower()
        scope = require_supported_value(scope, "execution.scope", SUPPORTED_EXECUTION_SCOPES)
        parallelize_candidates = require_bool(
            self.parallelize_candidates,
            "execution.parallelize_candidates",
        )
        worker_count = require_positive_int(self.worker_count, "execution.worker_count")

        if mode == "sequential":
            if parallelize_candidates:
                raise CoreValidationError(
                    "sequential execution cannot parallelize candidates."
                )
            if worker_count != 1:
                raise CoreValidationError("sequential execution requires worker_count=1.")
        if mode == "multiprocessing" and not parallelize_candidates:
            raise CoreValidationError(
                "multiprocessing execution requires parallelize_candidates=true."
            )

        object.__setattr__(self, "mode", mode)
        object.__setattr__(self, "scope", scope)
        object.__setattr__(self, "parallelize_candidates", parallelize_candidates)
        object.__setattr__(self, "worker_count", worker_count)

    @classmethod
    def from_mapping(cls, mapping: dict[str, object]) -> "ExecutionConfig":
        """Build an execution config from parsed YAML or Python dictionaries."""
        data = require_mapping(mapping, "execution")
        return cls(
            mode=data.get("mode", "sequential"),  # type: ignore[arg-type]
            parallelize_candidates=data.get("parallelize_candidates", False),  # type: ignore[arg-type]
            worker_count=data.get("worker_count", 1),  # type: ignore[arg-type]
            scope=data.get("scope", "candidate"),  # type: ignore[arg-type]
        )

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-safe representation of this execution config."""
        return {
            "mode": self.mode,
            "parallelize_candidates": self.parallelize_candidates,
            "worker_count": self.worker_count,
            "scope": self.scope,
        }


@dataclass(frozen=True)
class PathConfig:
    """Caller-provided experiment input and output roots."""

    input_root: str | Path
    output_root: str | Path

    def __post_init__(self) -> None:
        input_root, output_root = validate_separate_roots(
            input_root=self.input_root,
            output_root=self.output_root,
        )
        object.__setattr__(self, "input_root", input_root)
        object.__setattr__(self, "output_root", output_root)

    @classmethod
    def from_mapping(cls, mapping: dict[str, object]) -> "PathConfig":
        """Build a path config from parsed YAML or Python dictionaries."""
        data = require_mapping(mapping, "paths")
        if "input_root" not in data:
            raise CoreValidationError("paths.input_root is required.")
        if "output_root" not in data:
            raise CoreValidationError("paths.output_root is required.")
        return cls(
            input_root=data["input_root"],  # type: ignore[arg-type]
            output_root=data["output_root"],  # type: ignore[arg-type]
        )

    def to_dict(self) -> dict[str, str]:
        """Return a JSON-safe representation of this path config."""
        return {
            "input_root": str(self.input_root),
            "output_root": str(self.output_root),
        }


@dataclass(frozen=True)
class RunConfig:
    """Top-level validated configuration for one Verfeinert run."""

    run_id: str
    execution: ExecutionConfig
    paths: PathConfig
    random_seed: int | None = None
    schema_version: str = RUN_CONFIG_SCHEMA_VERSION

    def __post_init__(self) -> None:
        run_id = require_identifier(self.run_id, "run_id")
        if not isinstance(self.execution, ExecutionConfig):
            raise CoreValidationError("execution must be an ExecutionConfig.")
        if not isinstance(self.paths, PathConfig):
            raise CoreValidationError("paths must be a PathConfig.")
        random_seed = require_non_negative_int_or_none(self.random_seed, "random_seed")
        schema_version = require_non_empty_text(self.schema_version, "schema_version")
        if schema_version != RUN_CONFIG_SCHEMA_VERSION:
            raise CoreValidationError(
                f"schema_version must be {RUN_CONFIG_SCHEMA_VERSION!r}."
            )

        object.__setattr__(self, "run_id", run_id)
        object.__setattr__(self, "random_seed", random_seed)
        object.__setattr__(self, "schema_version", schema_version)

    @classmethod
    def from_mapping(cls, mapping: dict[str, object]) -> "RunConfig":
        """Build a run config from parsed YAML or Python dictionaries."""
        data = require_mapping(mapping, "run_config")
        if "run_id" not in data:
            raise CoreValidationError("run_id is required.")
        if "execution" not in data:
            raise CoreValidationError("execution is required.")
        if "paths" not in data:
            raise CoreValidationError("paths is required.")

        return cls(
            run_id=data["run_id"],  # type: ignore[arg-type]
            execution=ExecutionConfig.from_mapping(data["execution"]),  # type: ignore[arg-type]
            paths=PathConfig.from_mapping(data["paths"]),  # type: ignore[arg-type]
            random_seed=data.get("random_seed"),  # type: ignore[arg-type]
            schema_version=data.get("schema_version", RUN_CONFIG_SCHEMA_VERSION),  # type: ignore[arg-type]
        )

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation of this complete run config."""
        return {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "random_seed": self.random_seed,
            "execution": self.execution.to_dict(),
            "paths": self.paths.to_dict(),
        }


__all__ = [
    "ExecutionConfig",
    "ExecutionMode",
    "ExecutionScope",
    "PathConfig",
    "RunConfig",
    "SUPPORTED_EXECUTION_MODES",
    "SUPPORTED_EXECUTION_SCOPES",
]
