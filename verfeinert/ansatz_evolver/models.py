"""Reference-first models for ansatz evolution runs."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
import re
from typing import Any, Literal

from verfeinert import __version__
from verfeinert.core.io.serialization import to_json_safe
from verfeinert.core.metadata import current_git_commit


EVOLUTION_RUN_SCHEMA_VERSION = "verfeinert.evolution_run.v1"
ANALYSIS_RESULT_SCHEMA_VERSION = "verfeinert.analysis_result.v1"
CANDIDATE_SCHEMA_VERSION = "verfeinert.candidate.v1"
RUN_STATUSES = ("planned", "running", "completed", "failed", "cancelled")
GENERATION_ROLES = ("initial", "offspring", "survivor", "archive", "rejected")
REF_ROLES = ("parent", "child", "survivor", "archive", "rejected", "candidate")

_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$")
_SHA256_RE = re.compile(r"^[a-fA-F0-9]{64}$")


class EvolverModelError(ValueError):
    """Raised when an evolver model cannot be constructed."""


def utc_now_iso() -> str:
    """Return a second-resolution UTC timestamp for reproducible records."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def require_identifier(value: object, field_name: str) -> str:
    """Validate an identifier using the canonical schema pattern."""
    if not isinstance(value, str) or not value.strip():
        raise EvolverModelError(f"{field_name} must be a non-empty string.")
    normalized = value.strip()
    if not _IDENTIFIER_RE.fullmatch(normalized):
        raise EvolverModelError(f"{field_name} is not a portable identifier.")
    return normalized


def require_sha256_or_none(value: object, field_name: str) -> str | None:
    """Validate an optional SHA-256 hex digest."""
    if value is None:
        return None
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise EvolverModelError(f"{field_name} must be a SHA-256 hex digest.")
    return value


def require_mapping(value: object, field_name: str) -> dict[str, Any]:
    """Validate a mapping and return a shallow copy."""
    if not isinstance(value, Mapping):
        raise EvolverModelError(f"{field_name} must be a mapping.")
    return dict(value)


def require_sequence(value: object, field_name: str) -> tuple[Any, ...]:
    """Validate a non-string sequence."""
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise EvolverModelError(f"{field_name} must be a sequence.")
    return tuple(value)


def require_non_negative_int(value: object, field_name: str) -> int:
    """Validate a non-negative integer."""
    if type(value) is not int or value < 0:
        raise EvolverModelError(f"{field_name} must be a non-negative integer.")
    return value


def require_supported(value: object, field_name: str, allowed: Sequence[str]) -> str:
    """Validate a value against a small enum."""
    if not isinstance(value, str):
        raise EvolverModelError(f"{field_name} must be a string.")
    normalized = value.strip().lower()
    if normalized not in allowed:
        raise EvolverModelError(f"{field_name} must be one of {', '.join(allowed)}.")
    return normalized


@dataclass(frozen=True)
class CandidateRef:
    """Reference to a canonical Candidate JSON document."""

    candidate_id: str
    candidate_uri: str | None = None
    structural_hash: str | None = None
    lineage_hash: str | None = None
    role: str | None = None
    status: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "candidate_id", require_identifier(self.candidate_id, "candidate_id"))
        if self.candidate_uri is not None and not str(self.candidate_uri).strip():
            raise EvolverModelError("candidate_uri must not be empty when provided.")
        object.__setattr__(
            self,
            "structural_hash",
            require_sha256_or_none(self.structural_hash, "structural_hash"),
        )
        object.__setattr__(
            self,
            "lineage_hash",
            require_sha256_or_none(self.lineage_hash, "lineage_hash"),
        )
        if self.role is not None:
            object.__setattr__(self, "role", require_supported(self.role, "role", REF_ROLES))
        if self.status is not None and not str(self.status).strip():
            raise EvolverModelError("status must not be empty when provided.")
        object.__setattr__(self, "metadata", require_mapping(self.metadata, "metadata"))

    @classmethod
    def from_candidate_document(
        cls,
        document: Mapping[str, Any],
        *,
        candidate_uri: str | None = None,
        role: str | None = None,
        status: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> "CandidateRef":
        """Build a candidate reference from canonical Candidate JSON."""
        identity = require_mapping(document.get("identity"), "candidate.identity")
        return cls(
            candidate_id=document.get("candidate_id"),  # type: ignore[arg-type]
            candidate_uri=candidate_uri,
            structural_hash=identity.get("structural_hash"),  # type: ignore[arg-type]
            lineage_hash=identity.get("lineage_hash"),  # type: ignore[arg-type]
            role=role,
            status=status,
            metadata=dict(metadata or {}),
        )

    @classmethod
    def from_ref_document(cls, document: Mapping[str, Any]) -> "CandidateRef":
        """Build a candidate reference from an EvolutionRun candidate_ref object."""
        return cls(
            candidate_id=document.get("candidate_id"),  # type: ignore[arg-type]
            candidate_uri=document.get("candidate_uri"),  # type: ignore[arg-type]
            structural_hash=document.get("structural_hash"),  # type: ignore[arg-type]
            lineage_hash=document.get("lineage_hash"),  # type: ignore[arg-type]
        )

    def to_ref_dict(self) -> dict[str, Any]:
        """Return the schema-compatible candidate reference."""
        payload: dict[str, Any] = {"candidate_id": self.candidate_id}
        if self.candidate_uri is not None:
            payload["candidate_uri"] = self.candidate_uri
        if self.structural_hash is not None:
            payload["structural_hash"] = self.structural_hash
        if self.lineage_hash is not None:
            payload["lineage_hash"] = self.lineage_hash
        return payload

    def to_internal_dict(self) -> dict[str, Any]:
        """Return an internal audit view including non-schema annotations."""
        payload = self.to_ref_dict()
        if self.role is not None:
            payload["role"] = self.role
        if self.status is not None:
            payload["status"] = self.status
        if self.metadata:
            payload["metadata"] = dict(self.metadata)
        return to_json_safe(payload)


@dataclass(frozen=True)
class AnalysisResultRef:
    """Reference to a canonical AnalysisResult JSON document."""

    analysis_result_id: str
    candidate_id: str
    analysis_result_uri: str | None = None
    schema_version: str = ANALYSIS_RESULT_SCHEMA_VERSION
    hash: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "analysis_result_id",
            require_identifier(self.analysis_result_id, "analysis_result_id"),
        )
        object.__setattr__(self, "candidate_id", require_identifier(self.candidate_id, "candidate_id"))
        if self.analysis_result_uri is not None and not str(self.analysis_result_uri).strip():
            raise EvolverModelError("analysis_result_uri must not be empty when provided.")
        if not isinstance(self.schema_version, str) or not self.schema_version.strip():
            raise EvolverModelError("schema_version must be a non-empty string.")
        object.__setattr__(self, "hash", require_sha256_or_none(self.hash, "hash"))
        object.__setattr__(self, "metadata", require_mapping(self.metadata, "metadata"))

    @classmethod
    def from_analysis_result_document(
        cls,
        document: Mapping[str, Any],
        *,
        analysis_result_uri: str | None = None,
        hash: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> "AnalysisResultRef":
        """Build an AnalysisResult reference from canonical result JSON."""
        candidate_ref = require_mapping(document.get("candidate_ref"), "candidate_ref")
        return cls(
            analysis_result_id=document.get("analysis_result_id"),  # type: ignore[arg-type]
            candidate_id=candidate_ref.get("candidate_id"),  # type: ignore[arg-type]
            analysis_result_uri=analysis_result_uri,
            schema_version=str(document.get("schema_version", ANALYSIS_RESULT_SCHEMA_VERSION)),
            hash=hash,
            metadata=dict(metadata or {}),
        )

    def to_ref_dict(self) -> dict[str, Any]:
        """Return the schema-compatible analysis-result reference."""
        payload: dict[str, Any] = {
            "analysis_result_id": self.analysis_result_id,
            "candidate_id": self.candidate_id,
            "schema_version": self.schema_version,
        }
        if self.analysis_result_uri is not None:
            payload["analysis_result_uri"] = self.analysis_result_uri
        if self.hash is not None:
            payload["hash"] = self.hash
        if self.metadata:
            payload["metadata"] = dict(self.metadata)
        return to_json_safe(payload)


@dataclass(frozen=True)
class EvolutionEvent:
    """Typed audit event for a generation."""

    event_type: str
    created_at: str | None = None
    candidate_id: str | None = None
    analysis_result_id: str | None = None
    policy_id: str | None = None
    status: str | None = None
    reason: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.event_type, str) or not self.event_type.strip():
            raise EvolverModelError("event_type must be a non-empty string.")
        object.__setattr__(self, "event_type", self.event_type.strip())
        if self.candidate_id is not None:
            object.__setattr__(
                self,
                "candidate_id",
                require_identifier(self.candidate_id, "candidate_id"),
            )
        if self.analysis_result_id is not None:
            object.__setattr__(
                self,
                "analysis_result_id",
                require_identifier(self.analysis_result_id, "analysis_result_id"),
            )
        if self.policy_id is not None:
            object.__setattr__(self, "policy_id", require_identifier(self.policy_id, "policy_id"))
        if self.status is not None and not str(self.status).strip():
            raise EvolverModelError("status must not be empty when provided.")
        if self.reason is not None and not str(self.reason).strip():
            raise EvolverModelError("reason must not be empty when provided.")
        object.__setattr__(self, "metadata", require_mapping(self.metadata, "metadata"))

    def to_dict(self) -> dict[str, Any]:
        """Return a schema-compatible event."""
        payload: dict[str, Any] = {"event_type": self.event_type}
        if self.created_at is not None:
            payload["created_at"] = self.created_at
        if self.candidate_id is not None:
            payload["candidate_id"] = self.candidate_id
        if self.analysis_result_id is not None:
            payload["analysis_result_id"] = self.analysis_result_id
        if self.policy_id is not None:
            payload["policy_id"] = self.policy_id
        if self.status is not None:
            payload["status"] = self.status
        if self.reason is not None:
            payload["reason"] = self.reason
        if self.metadata:
            payload["metadata"] = dict(self.metadata)
        return to_json_safe(payload)


@dataclass(frozen=True)
class GenerationRecord:
    """Reference-based record for one evolution generation."""

    generation_index: int
    candidate_refs: tuple[CandidateRef, ...]
    survivor_refs: tuple[CandidateRef, ...] = ()
    archive_refs: tuple[CandidateRef, ...] = ()
    parent_refs: tuple[CandidateRef, ...] = ()
    rejected_refs: tuple[CandidateRef, ...] = ()
    analysis_result_refs: tuple[AnalysisResultRef, ...] = ()
    configuration: dict[str, Any] = field(default_factory=dict)
    events: tuple[EvolutionEvent, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "generation_index",
            require_non_negative_int(self.generation_index, "generation_index"),
        )
        for field_name in (
            "candidate_refs",
            "survivor_refs",
            "archive_refs",
            "parent_refs",
            "rejected_refs",
        ):
            refs = tuple(getattr(self, field_name))
            if any(not isinstance(ref, CandidateRef) for ref in refs):
                raise EvolverModelError(f"{field_name} must contain CandidateRef objects.")
            object.__setattr__(self, field_name, refs)
        analysis_refs = tuple(self.analysis_result_refs)
        if any(not isinstance(ref, AnalysisResultRef) for ref in analysis_refs):
            raise EvolverModelError("analysis_result_refs must contain AnalysisResultRef objects.")
        object.__setattr__(self, "analysis_result_refs", analysis_refs)
        events = tuple(self.events)
        if any(not isinstance(event, EvolutionEvent) for event in events):
            raise EvolverModelError("events must contain EvolutionEvent objects.")
        object.__setattr__(self, "events", events)
        object.__setattr__(self, "configuration", require_mapping(self.configuration, "configuration"))

    def to_dict(self) -> dict[str, Any]:
        """Return a schema-compatible generation record."""
        payload: dict[str, Any] = {
            "generation_index": self.generation_index,
            "candidate_refs": [ref.to_ref_dict() for ref in self.candidate_refs],
            "survivor_refs": [ref.to_ref_dict() for ref in self.survivor_refs],
            "archive_refs": [ref.to_ref_dict() for ref in self.archive_refs],
        }
        if self.parent_refs:
            payload["parent_refs"] = [ref.to_ref_dict() for ref in self.parent_refs]
        if self.rejected_refs:
            payload["rejected_refs"] = [ref.to_ref_dict() for ref in self.rejected_refs]
        if self.analysis_result_refs:
            payload["analysis_result_refs"] = [
                ref.to_ref_dict() for ref in self.analysis_result_refs
            ]
        if self.configuration:
            payload["configuration"] = self.configuration
        if self.events:
            payload["events"] = [event.to_dict() for event in self.events]
        return to_json_safe(payload)


@dataclass(frozen=True)
class EvolutionRunState:
    """Complete in-memory state for one JSON-first evolution run."""

    evolution_run_id: str
    status: Literal["planned", "running", "completed", "failed", "cancelled"]
    configuration: dict[str, Any]
    generations: tuple[GenerationRecord, ...] = ()
    provenance: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now_iso)
    software_version: str = __version__
    git_commit: str | None = field(default_factory=current_git_commit)
    execution_metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "evolution_run_id",
            require_identifier(self.evolution_run_id, "evolution_run_id"),
        )
        object.__setattr__(self, "status", require_supported(self.status, "status", RUN_STATUSES))
        configuration = require_mapping(self.configuration, "configuration")
        if "random_seed" not in configuration:
            raise EvolverModelError("configuration.random_seed is required.")
        if "execution" not in configuration:
            raise EvolverModelError("configuration.execution is required.")
        object.__setattr__(self, "configuration", configuration)
        generations = tuple(self.generations)
        if any(not isinstance(generation, GenerationRecord) for generation in generations):
            raise EvolverModelError("generations must contain GenerationRecord objects.")
        object.__setattr__(self, "generations", generations)
        provenance = require_mapping(self.provenance or {}, "provenance")
        provenance.setdefault("created_at", self.created_at)
        provenance.setdefault("source", "verfeinert.ansatz_evolver")
        provenance.setdefault("input_hashes", {})
        object.__setattr__(self, "provenance", provenance)
        object.__setattr__(self, "metadata", require_mapping(self.metadata, "metadata"))
        object.__setattr__(
            self,
            "execution_metadata",
            require_mapping(self.execution_metadata, "execution_metadata"),
        )

    def to_dict(self) -> dict[str, Any]:
        """Return a canonical EvolutionRun JSON document."""
        execution = {
            "evolver_executed_metrics": False,
            "qnodes_executed_by_evolver": False,
            "analysis_requested": False,
            "analysis_results_ingested": False,
            "selection_executed": False,
            "plots_generated_by_evolver": False,
        }
        execution.update(self.execution_metadata)
        execution["evolver_executed_metrics"] = False
        execution["qnodes_executed_by_evolver"] = False
        execution["plots_generated_by_evolver"] = False

        run_metadata: dict[str, Any] = {
            "created_at": self.created_at,
            "status": self.status,
            "software_version": self.software_version,
            "git_commit": self.git_commit,
            "execution": execution,
        }
        payload: dict[str, Any] = {
            "schema_version": EVOLUTION_RUN_SCHEMA_VERSION,
            "evolution_run_id": self.evolution_run_id,
            "run_metadata": run_metadata,
            "configuration": self.configuration,
            "generations": [generation.to_dict() for generation in self.generations],
            "provenance": self.provenance,
        }
        if self.metadata:
            payload["metadata"] = self.metadata
        return to_json_safe(payload)


__all__ = [
    "ANALYSIS_RESULT_SCHEMA_VERSION",
    "CANDIDATE_SCHEMA_VERSION",
    "EVOLUTION_RUN_SCHEMA_VERSION",
    "AnalysisResultRef",
    "CandidateRef",
    "EvolutionEvent",
    "EvolutionRunState",
    "EvolverModelError",
    "GenerationRecord",
    "utc_now_iso",
]
