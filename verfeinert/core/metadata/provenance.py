"""Run provenance records and collectors."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import subprocess
from typing import Any, Callable, Mapping

from verfeinert import __version__
from verfeinert.core.config import RunConfig
from verfeinert.core.hashing import hash_inputs
from verfeinert.core.io.serialization import to_json_safe
from verfeinert.core.schemas import RUN_METADATA_SCHEMA_VERSION
from verfeinert.core.validation import CoreValidationError, require_bool, require_mapping


Clock = Callable[[], datetime]


@dataclass(frozen=True)
class ExecutionFlags:
    """Truthful booleans describing what was actually executed in a run."""

    notebooks_executed: bool = False
    qnodes_executed: bool = False
    generated_callables_executed: bool = False
    scientific_metrics_computed: bool = False
    experiments_run: bool = False
    plots_generated: bool = False

    def __post_init__(self) -> None:
        for field_name in self.__dataclass_fields__:
            object.__setattr__(
                self,
                field_name,
                require_bool(getattr(self, field_name), f"execution_flags.{field_name}"),
            )

    @classmethod
    def from_mapping(cls, mapping: Mapping[str, object]) -> "ExecutionFlags":
        """Build execution flags from a parsed record."""
        data = require_mapping(dict(mapping), "execution_flags")
        return cls(
            notebooks_executed=data.get("notebooks_executed", False),  # type: ignore[arg-type]
            qnodes_executed=data.get("qnodes_executed", False),  # type: ignore[arg-type]
            generated_callables_executed=data.get(
                "generated_callables_executed",
                False,
            ),  # type: ignore[arg-type]
            scientific_metrics_computed=data.get(
                "scientific_metrics_computed",
                False,
            ),  # type: ignore[arg-type]
            experiments_run=data.get("experiments_run", False),  # type: ignore[arg-type]
            plots_generated=data.get("plots_generated", False),  # type: ignore[arg-type]
        )

    def to_dict(self) -> dict[str, bool]:
        """Return JSON-safe execution flags."""
        return {
            "notebooks_executed": self.notebooks_executed,
            "qnodes_executed": self.qnodes_executed,
            "generated_callables_executed": self.generated_callables_executed,
            "scientific_metrics_computed": self.scientific_metrics_computed,
            "experiments_run": self.experiments_run,
            "plots_generated": self.plots_generated,
        }


@dataclass(frozen=True)
class RunMetadata:
    """Complete reproducibility metadata for one Verfeinert run."""

    schema_version: str
    verfeinert_version: str
    created_at: str
    run_id: str
    effective_config: dict[str, Any]
    random_seed: int | None
    execution_mode: str
    worker_count: int
    input_hashes: dict[str, str]
    git_commit: str | None
    execution_flags: ExecutionFlags

    def __post_init__(self) -> None:
        if self.schema_version != RUN_METADATA_SCHEMA_VERSION:
            raise CoreValidationError(
                f"schema_version must be {RUN_METADATA_SCHEMA_VERSION!r}."
            )
        if not isinstance(self.execution_flags, ExecutionFlags):
            raise CoreValidationError("execution_flags must be an ExecutionFlags.")

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe metadata record."""
        return {
            "schema_version": self.schema_version,
            "verfeinert_version": self.verfeinert_version,
            "created_at": self.created_at,
            "run_id": self.run_id,
            "effective_config": to_json_safe(self.effective_config),
            "random_seed": self.random_seed,
            "execution_mode": self.execution_mode,
            "worker_count": self.worker_count,
            "input_hashes": dict(sorted(self.input_hashes.items())),
            "git_commit": self.git_commit,
            "execution_flags": self.execution_flags.to_dict(),
        }


def current_git_commit(git_root: str | Path | None = None) -> str | None:
    """Return the current Git commit, or ``None`` when unavailable."""
    root = Path.cwd() if git_root is None else Path(git_root).expanduser()
    try:
        completed = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    commit = completed.stdout.strip()
    return commit or None


def collect_run_metadata(
    config: RunConfig,
    *,
    input_paths: Mapping[str, str | Path] | None = None,
    execution_flags: ExecutionFlags | None = None,
    git_root: str | Path | None = None,
    version: str | None = None,
    clock: Clock | None = None,
) -> RunMetadata:
    """Collect reproducibility metadata without executing scientific workloads."""
    if not isinstance(config, RunConfig):
        raise CoreValidationError("config must be a RunConfig.")
    now = clock() if clock is not None else datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    flags = execution_flags or ExecutionFlags()
    return RunMetadata(
        schema_version=RUN_METADATA_SCHEMA_VERSION,
        verfeinert_version=version or __version__,
        created_at=now.astimezone(timezone.utc).isoformat(),
        run_id=config.run_id,
        effective_config=config.to_dict(),
        random_seed=config.random_seed,
        execution_mode=config.execution.mode,
        worker_count=config.execution.worker_count,
        input_hashes=hash_inputs(input_paths or {}),
        git_commit=current_git_commit(git_root),
        execution_flags=flags,
    )


__all__ = [
    "ExecutionFlags",
    "RunMetadata",
    "collect_run_metadata",
    "current_git_commit",
]
