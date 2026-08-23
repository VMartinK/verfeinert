"""Durable JSON workflow checkpoints."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
from typing import Any

from verfeinert import __version__
from verfeinert.core.hashing import hash_file, stable_hash
from verfeinert.core.io import read_json
from verfeinert.core.io.serialization import to_json_safe

from .config import WorkflowConfig, WorkflowConfigError


WORKFLOW_CHECKPOINT_SCHEMA_VERSION = "verfeinert.workflow_checkpoint.v1"
WORKFLOW_CHECKPOINT_FINGERPRINT_VERSION = (
    "verfeinert.workflow_checkpoint_fingerprint.v1"
)


class WorkflowCheckpointError(WorkflowConfigError):
    """Raised when a workflow checkpoint cannot be read or resumed."""


def workflow_checkpoint_fingerprint(config: WorkflowConfig) -> str:
    """Return the path/stage-independent compatibility fingerprint."""
    evolver = config.evolver.to_dict()
    evolver.pop("max_generations", None)
    evolver.pop("metadata", None)
    payload: dict[str, Any] = {
        "fingerprint_version": WORKFLOW_CHECKPOINT_FINGERPRINT_VERSION,
        "campaign_type": config.campaign_type,
        "random_seed": config.random_seed,
        "generation": {
            "family": config.generation.family,
            "template_ids": list(config.generation.template_ids),
            "layers": list(config.generation.layers),
            "n_qubits": config.generation.n_qubits,
            "candidate_id_prefix": config.generation.candidate_id_prefix,
            "constraints": (
                config.generation.constraints.to_dict()
                if config.generation.constraints is not None
                else None
            ),
        },
        "analyzer": {
            "selected_metrics": list(config.analyzer.selected_metrics),
            "structural_cost": config.analyzer.structural_cost.to_dict(),
            "permissions": config.analyzer.permissions.to_dict(),
            "metric_configs": config.analyzer.metric_configs,
            "materialization": config.analyzer.materialization.to_dict(),
            "random_seed": config.analyzer.random_seed,
            "ranking": (
                config.analyzer.ranking.to_dict()
                if config.analyzer.ranking is not None
                else None
            ),
            "pareto": (
                config.analyzer.pareto.to_dict()
                if config.analyzer.pareto is not None
                else None
            ),
        },
        "evolver": evolver,
        "analysis_result_reuse": dict(config.analysis_result_reuse),
        "execution": config.execution.to_dict(),
    }
    return stable_hash(payload)


def build_workflow_checkpoint_document(
    *,
    config: WorkflowConfig,
    completed_stages: Sequence[str],
    stage_plan: Mapping[str, Any],
    artifact_refs: Mapping[str, Any],
    consumed_artifacts: Sequence[Mapping[str, Any]],
    produced_artifacts: Sequence[Mapping[str, Any]],
    reused_artifacts: Sequence[Mapping[str, Any]],
    status: str = "completed",
    checkpoint_id: str | None = None,
) -> dict[str, Any]:
    """Build a JSON-safe workflow checkpoint document."""
    fingerprint = workflow_checkpoint_fingerprint(config)
    document = {
        "schema_version": WORKFLOW_CHECKPOINT_SCHEMA_VERSION,
        "checkpoint_id": checkpoint_id or f"{config.run_id}-checkpoint",
        "run_id": config.run_id,
        "created_at": config.created_at or _utc_now(),
        "status": status,
        "software": {
            "verfeinert_version": __version__,
            "git_commit": None,
            "producer": "verfeinert.workflow",
        },
        "compatibility": {
            "workflow_fingerprint": fingerprint,
            "workflow_fingerprint_version": WORKFLOW_CHECKPOINT_FINGERPRINT_VERSION,
        },
        "workflow": {
            "config": config.to_dict(),
            "stage_plan": dict(stage_plan),
            "completed_stages": list(dict.fromkeys(completed_stages)),
            "rng": {
                "workflow_seed": config.random_seed,
                "analyzer_seed": config.analyzer.random_seed,
                "execution": config.execution.to_dict(),
            },
        },
        "artifacts": {
            "refs": to_json_safe(dict(artifact_refs)),
            "consumed": [dict(item) for item in consumed_artifacts],
            "produced": [dict(item) for item in produced_artifacts],
            "reused": [dict(item) for item in reused_artifacts],
        },
    }
    return validate_workflow_checkpoint_document(document)


def read_workflow_checkpoint_json(source: str | Path | Mapping[str, Any]) -> dict[str, Any]:
    """Read and validate a workflow checkpoint document."""
    document = dict(source) if isinstance(source, Mapping) else read_json(source)
    checkpoint = validate_workflow_checkpoint_document(document)
    validate_workflow_checkpoint_artifacts(checkpoint)
    return checkpoint


def write_workflow_checkpoint_json(
    document: Mapping[str, Any],
    path: str | Path,
) -> Path:
    """Atomically write a workflow checkpoint JSON document."""
    checkpoint = validate_workflow_checkpoint_document(document)
    return _write_json_atomic(path, checkpoint)


def validate_workflow_checkpoint_document(document: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the supported checkpoint schema shape."""
    if not isinstance(document, Mapping):
        raise WorkflowCheckpointError("workflow checkpoint must be a JSON object.")
    payload = to_json_safe(dict(document))
    if payload.get("schema_version") != WORKFLOW_CHECKPOINT_SCHEMA_VERSION:
        raise WorkflowCheckpointError(
            "checkpoint source is not a WorkflowCheckpoint artifact.",
        )
    for key in ("checkpoint_id", "run_id", "status", "software", "compatibility", "workflow", "artifacts"):
        if key not in payload:
            raise WorkflowCheckpointError(f"workflow checkpoint is missing {key!r}.")
    compatibility = payload.get("compatibility")
    if not isinstance(compatibility, Mapping):
        raise WorkflowCheckpointError("workflow checkpoint compatibility must be an object.")
    if not compatibility.get("workflow_fingerprint"):
        raise WorkflowCheckpointError("workflow checkpoint is missing workflow_fingerprint.")
    workflow = payload.get("workflow")
    if not isinstance(workflow, Mapping):
        raise WorkflowCheckpointError("workflow checkpoint workflow must be an object.")
    completed = workflow.get("completed_stages")
    if not isinstance(completed, Sequence) or isinstance(completed, (str, bytes, bytearray)):
        raise WorkflowCheckpointError("workflow checkpoint completed_stages must be a list.")
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, Mapping) or not isinstance(artifacts.get("refs"), Mapping):
        raise WorkflowCheckpointError("workflow checkpoint artifacts.refs must be an object.")
    return payload


def validate_workflow_checkpoint_artifacts(document: Mapping[str, Any]) -> None:
    """Fail closed if a checkpointed artifact path is missing or has changed."""
    refs = dict(dict(document.get("artifacts", {})).get("refs", {}))
    for record in _iter_artifact_ref_records(refs):
        uri = record.get("uri")
        if not isinstance(uri, str) or not uri:
            continue
        expected_hash = record.get("sha256")
        if expected_hash is None:
            continue
        path = Path(uri).expanduser()
        if not path.is_file():
            raise WorkflowCheckpointError(
                f"checkpoint artifact is missing: {uri}",
            )
        actual_hash = hash_file(path)
        if actual_hash != expected_hash:
            raise WorkflowCheckpointError(
                "checkpoint artifact hash mismatch for "
                f"{uri}: expected {expected_hash}, got {actual_hash}",
            )


def _iter_artifact_ref_records(refs: Mapping[str, Any]):
    for value in refs.values():
        if isinstance(value, Mapping):
            if "uri" in value:
                yield dict(value)
            else:
                yield from _iter_artifact_ref_records(value)
        elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            for item in value:
                if isinstance(item, Mapping):
                    yield dict(item)


def _write_json_atomic(path: str | Path, payload: Mapping[str, Any]) -> Path:
    target = Path(path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp_path: Path | None = None
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=target.parent,
        prefix=f".{target.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        tmp_path = Path(handle.name)
        json.dump(to_json_safe(dict(payload)), handle, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    try:
        os.replace(tmp_path, target)
        _fsync_directory(target.parent)
    finally:
        if tmp_path is not None and tmp_path.exists():
            tmp_path.unlink()
    return target


def _fsync_directory(path: Path) -> None:
    try:
        fd = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


__all__ = [
    "WORKFLOW_CHECKPOINT_FINGERPRINT_VERSION",
    "WORKFLOW_CHECKPOINT_SCHEMA_VERSION",
    "WorkflowCheckpointError",
    "build_workflow_checkpoint_document",
    "read_workflow_checkpoint_json",
    "validate_workflow_checkpoint_artifacts",
    "validate_workflow_checkpoint_document",
    "workflow_checkpoint_fingerprint",
    "write_workflow_checkpoint_json",
]
