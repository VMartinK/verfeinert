"""Workflow run manifests and traceability exports."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import csv
from pathlib import Path
from typing import Any

from verfeinert import __version__
from verfeinert.core.hashing import stable_hash
from verfeinert.core.io import write_json
from verfeinert.core.io.serialization import to_json_safe

from .config import WorkflowConfig


WORKFLOW_MANIFEST_SCHEMA_VERSION = "verfeinert.workflow_manifest.v1"
WORKFLOW_TRACEABILITY_SCHEMA_VERSION = "verfeinert.workflow_traceability.v1"
TRACEABILITY_COLUMNS = (
    "run_id",
    "candidate_id",
    "structural_hash",
    "lineage_hash",
    "generation",
    "parent_candidate_id",
    "analysis_result_id",
    "expressibility",
    "trainability",
    "structural_cost",
    "survivor",
    "rejected",
    "archive",
    "final_stopping_reason",
)


def build_workflow_manifest_document(
    *,
    config: WorkflowConfig,
    run_root: Path,
    stage_plan: Mapping[str, Any],
    executed_operations: Sequence[str],
    consumed_artifacts: Sequence[Mapping[str, Any]],
    produced_artifacts: Sequence[Mapping[str, Any]],
    reused_artifacts: Sequence[Mapping[str, Any]],
    artifact_paths: Mapping[str, Any],
    warnings: Sequence[str],
    final_stopping_reason: str | None,
    checkpoint_path: Path | None,
    event_log_path: Path | None,
) -> dict[str, Any]:
    """Build a persisted run manifest document."""
    config_snapshot = config.to_dict()
    return to_json_safe(
        {
            "schema_version": WORKFLOW_MANIFEST_SCHEMA_VERSION,
            "run_id": config.run_id,
            "software": {
                "verfeinert_version": __version__,
                "git_commit": None,
                "producer": "verfeinert.workflow",
            },
            "paths": {
                "run_root": str(run_root),
                "output_root": str(config.output_root),
                "checkpoint": str(checkpoint_path) if checkpoint_path is not None else None,
                "event_log": str(event_log_path) if event_log_path is not None else None,
            },
            "config": {
                "snapshot": config_snapshot,
                "hash": stable_hash(config_snapshot),
            },
            "seed_policy": {
                "workflow_seed": config.random_seed,
                "analyzer_seed": config.analyzer.random_seed,
            },
            "execution": {
                "mode": config.execution.mode,
                "worker_count": config.execution.worker_count,
                "config": config.execution.to_dict(),
            },
            "materialization": config.analyzer.materialization.to_dict(),
            "constraints": (
                config.generation.constraints.to_dict()
                if config.generation.constraints is not None
                else None
            ),
            "stages": {
                "requested": dict(stage_plan),
                "completed": list(dict.fromkeys(executed_operations)),
                "status": "completed",
            },
            "artifacts": {
                "paths": dict(artifact_paths),
                "consumed": [dict(item) for item in consumed_artifacts],
                "produced": [dict(item) for item in produced_artifacts],
                "reused": [dict(item) for item in reused_artifacts],
            },
            "warnings": list(dict.fromkeys(warnings)),
            "final_stopping_reason": final_stopping_reason,
        },
    )


def write_workflow_manifest_json(document: Mapping[str, Any], output_root: Path) -> Path:
    """Write the workflow manifest JSON."""
    return write_json(output_root / "workflow_manifest.json", document)


def build_traceability_document(
    *,
    run_id: str,
    rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Build the machine-readable traceability table document."""
    return to_json_safe(
        {
            "schema_version": WORKFLOW_TRACEABILITY_SCHEMA_VERSION,
            "run_id": run_id,
            "columns": list(TRACEABILITY_COLUMNS),
            "rows": [dict(row) for row in rows],
        },
    )


def write_traceability_json(document: Mapping[str, Any], output_root: Path) -> Path:
    """Write traceability rows as JSON."""
    return write_json(output_root / "workflow_traceability.json", document)


def write_traceability_csv(rows: Sequence[Mapping[str, Any]], output_root: Path) -> Path:
    """Write traceability rows as deterministic CSV."""
    target = output_root / "workflow_traceability.csv"
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=TRACEABILITY_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in TRACEABILITY_COLUMNS})
    return target


__all__ = [
    "TRACEABILITY_COLUMNS",
    "WORKFLOW_MANIFEST_SCHEMA_VERSION",
    "WORKFLOW_TRACEABILITY_SCHEMA_VERSION",
    "build_traceability_document",
    "build_workflow_manifest_document",
    "write_traceability_csv",
    "write_traceability_json",
    "write_workflow_manifest_json",
]
