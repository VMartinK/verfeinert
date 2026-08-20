"""Internal analyzer records around canonical JSON contracts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
import re
from typing import Any

from verfeinert.core.io.serialization import to_json_safe


ANALYSIS_RESULT_SCHEMA_VERSION = "verfeinert.analysis_result.v1"
METRIC_STATUSES = ("computed", "skipped", "failed")
_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$")


class AnalyzerModelError(ValueError):
    """Raised when an internal analyzer record cannot be constructed."""


@dataclass(frozen=True)
class OperationView:
    """Lightweight internal view of a canonical operation document."""

    operation_id: str
    gate_name: str
    qubits: tuple[int, ...]
    parameters: tuple[dict[str, Any], ...] = ()
    layer: int | None = None
    order: int | None = None
    role: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    gate_namespace: str | None = field(default=None, kw_only=True)
    gate_version: str | None = field(default=None, kw_only=True)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "operation_id",
            _require_identifier(self.operation_id, "operation_id"),
        )
        object.__setattr__(
            self,
            "gate_name",
            _require_non_empty_text(self.gate_name, "gate_name").lower(),
        )
        if self.gate_namespace is not None:
            object.__setattr__(
                self,
                "gate_namespace",
                _require_non_empty_text(self.gate_namespace, "gate_namespace"),
            )
        if self.gate_version is not None:
            object.__setattr__(
                self,
                "gate_version",
                _require_non_empty_text(self.gate_version, "gate_version"),
            )
        qubits = tuple(_require_non_negative_int(item, "qubits") for item in self.qubits)
        if not qubits:
            raise AnalyzerModelError("qubits must not be empty.")
        object.__setattr__(self, "qubits", qubits)
        object.__setattr__(
            self,
            "parameters",
            tuple(_require_mapping(item, "parameters") for item in self.parameters),
        )
        if self.layer is not None:
            object.__setattr__(
                self,
                "layer",
                _require_non_negative_int(self.layer, "layer"),
            )
        if self.order is not None:
            object.__setattr__(
                self,
                "order",
                _require_non_negative_int(self.order, "order"),
            )
        if self.role is not None:
            object.__setattr__(
                self,
                "role",
                _require_non_empty_text(self.role, "role"),
            )
        object.__setattr__(self, "metadata", _require_mapping(self.metadata, "metadata"))

    @classmethod
    def from_document(cls, document: Mapping[str, Any]) -> "OperationView":
        """Build an operation view from canonical operation JSON."""
        operation = dict(document)
        gate = operation.get("gate")
        if not isinstance(gate, Mapping):
            raise AnalyzerModelError("operation.gate must be a mapping.")
        return cls(
            operation_id=operation["operation_id"],
            gate_name=gate["name"],
            gate_namespace=gate.get("namespace"),
            gate_version=gate.get("version"),
            qubits=tuple(operation["qubits"]),
            parameters=tuple(operation.get("parameters", ())),
            layer=operation.get("layer"),
            order=operation.get("order"),
            role=operation.get("role"),
            metadata=dict(operation.get("metadata", {})),
        )

    @property
    def is_two_qubit(self) -> bool:
        """Return whether the operation acts on exactly two qubits."""
        return len(self.qubits) == 2

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe internal representation."""
        return to_json_safe(
            {
                "operation_id": self.operation_id,
                "gate_name": self.gate_name,
                "gate_namespace": self.gate_namespace,
                "gate_version": self.gate_version,
                "qubits": list(self.qubits),
                "parameters": list(self.parameters),
                "layer": self.layer,
                "order": self.order,
                "role": self.role,
                "metadata": self.metadata,
            },
        )


@dataclass(frozen=True)
class CandidateView:
    """Internal view of the fields the analyzer needs from Candidate JSON."""

    candidate_id: str
    structural_hash: str
    lineage_hash: str | None
    hash_schema_version: str
    n_qubits: int
    wire_order: tuple[int, ...] | None
    parameters: tuple[dict[str, Any], ...]
    operations: tuple[OperationView, ...]
    lineage: dict[str, Any]
    metadata: dict[str, Any]
    provenance: dict[str, Any]
    source_uri: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "candidate_id",
            _require_identifier(self.candidate_id, "candidate_id"),
        )
        if not _SHA256_RE.fullmatch(str(self.structural_hash)):
            raise AnalyzerModelError("structural_hash must be a SHA-256 hex string.")
        if self.lineage_hash is not None and not _SHA256_RE.fullmatch(str(self.lineage_hash)):
            raise AnalyzerModelError("lineage_hash must be null or a SHA-256 hex string.")
        object.__setattr__(
            self,
            "hash_schema_version",
            _require_non_empty_text(
                self.hash_schema_version,
                "hash_schema_version",
            ),
        )
        object.__setattr__(
            self,
            "n_qubits",
            _require_positive_int(self.n_qubits, "n_qubits"),
        )
        if self.wire_order is not None:
            object.__setattr__(
                self,
                "wire_order",
                tuple(
                    _require_non_negative_int(item, "wire_order")
                    for item in self.wire_order
                ),
            )
        operations = tuple(self.operations)
        if not operations:
            raise AnalyzerModelError("candidate operations must not be empty.")
        if any(not isinstance(operation, OperationView) for operation in operations):
            raise AnalyzerModelError("operations must contain OperationView records.")
        object.__setattr__(self, "operations", operations)
        object.__setattr__(
            self,
            "parameters",
            tuple(_require_mapping(item, "parameters") for item in self.parameters),
        )
        object.__setattr__(self, "lineage", _require_mapping(self.lineage, "lineage"))
        object.__setattr__(self, "metadata", _require_mapping(self.metadata, "metadata"))
        object.__setattr__(
            self,
            "provenance",
            _require_mapping(self.provenance, "provenance"),
        )

    @classmethod
    def from_document(
        cls,
        document: Mapping[str, Any],
        *,
        source_uri: str | None = None,
    ) -> "CandidateView":
        """Build a candidate view from canonical Candidate JSON."""
        candidate = dict(document)
        identity = candidate["identity"]
        circuit = candidate["circuit"]
        return cls(
            candidate_id=candidate["candidate_id"],
            structural_hash=identity["structural_hash"],
            lineage_hash=identity.get("lineage_hash"),
            hash_schema_version=identity["hash_schema_version"],
            n_qubits=circuit["n_qubits"],
            wire_order=(
                tuple(circuit["wire_order"])
                if "wire_order" in circuit
                else None
            ),
            parameters=tuple(circuit.get("parameters", ())),
            operations=tuple(
                OperationView.from_document(operation)
                for operation in circuit["operations"]
            ),
            lineage=dict(candidate["lineage"]),
            metadata=dict(candidate["metadata"]),
            provenance=dict(candidate["provenance"]),
            source_uri=source_uri,
        )

    @property
    def parameter_count(self) -> int:
        """Return the trainable canonical circuit parameter count."""
        return sum(1 for item in self.parameters if item.get("kind") == "trainable")

    @property
    def operation_count(self) -> int:
        """Return the number of canonical operations."""
        return len(self.operations)

    @property
    def two_qubit_operation_count(self) -> int:
        """Return the number of operations acting on exactly two qubits."""
        return sum(1 for operation in self.operations if operation.is_two_qubit)

    @property
    def declared_depth(self) -> int | None:
        """Return optional structural depth recorded in candidate metadata."""
        structural = self.metadata.get("structural")
        if not isinstance(structural, Mapping) or "depth" not in structural:
            return None
        value = structural["depth"]
        return _require_non_negative_int(value, "metadata.structural.depth")

    def to_candidate_ref(self) -> dict[str, Any]:
        """Build the AnalysisResult candidate reference."""
        reference: dict[str, Any] = {
            "candidate_id": self.candidate_id,
            "structural_hash": self.structural_hash,
        }
        if self.source_uri:
            reference["candidate_uri"] = self.source_uri
        return reference


@dataclass(frozen=True)
class MetricRecord:
    """Canonical AnalysisResult metric record."""

    metric_id: str
    name: str
    status: str
    value: float | dict[str, Any] | list[Any] | None = None
    units: str | None = None
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "metric_id",
            _require_identifier(self.metric_id, "metric_id"),
        )
        object.__setattr__(self, "name", _require_non_empty_text(self.name, "name"))
        if self.status not in METRIC_STATUSES:
            raise AnalyzerModelError(f"Unsupported metric status: {self.status!r}.")
        if self.units is not None:
            object.__setattr__(
                self,
                "units",
                _require_non_empty_text(self.units, "units"),
            )
        if self.error is not None:
            object.__setattr__(self, "error", str(self.error))
        object.__setattr__(self, "metadata", _require_mapping(self.metadata, "metadata"))

    def to_dict(self) -> dict[str, Any]:
        """Return a schema-conformant metric dictionary."""
        payload: dict[str, Any] = {
            "metric_id": self.metric_id,
            "name": self.name,
            "status": self.status,
        }
        if self.value is not None:
            payload["value"] = self.value
        if self.units is not None:
            payload["units"] = self.units
        if self.error is not None:
            payload["error"] = self.error
        if self.metadata:
            payload["metadata"] = self.metadata
        return to_json_safe(payload)


@dataclass(frozen=True)
class CostRecord:
    """Canonical AnalysisResult cost record."""

    structural_cost: float | None = None
    operation_count: int | None = None
    two_qubit_operation_count: int | None = None
    parameter_count: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.structural_cost is not None:
            object.__setattr__(
                self,
                "structural_cost",
                _finite_float(self.structural_cost, "structural_cost"),
            )
        for field_name in (
            "operation_count",
            "two_qubit_operation_count",
            "parameter_count",
        ):
            value = getattr(self, field_name)
            if value is not None:
                object.__setattr__(
                    self,
                    field_name,
                    _require_non_negative_int(value, field_name),
                )
        object.__setattr__(self, "metadata", _require_mapping(self.metadata, "metadata"))

    def to_dict(self) -> dict[str, Any]:
        """Return a schema-conformant cost dictionary."""
        payload: dict[str, Any] = {}
        if self.structural_cost is not None:
            payload["structural_cost"] = self.structural_cost
        if self.operation_count is not None:
            payload["operation_count"] = self.operation_count
        if self.two_qubit_operation_count is not None:
            payload["two_qubit_operation_count"] = self.two_qubit_operation_count
        if self.parameter_count is not None:
            payload["parameter_count"] = self.parameter_count
        if self.metadata:
            payload["metadata"] = self.metadata
        return to_json_safe(payload)


@dataclass(frozen=True)
class ClassificationRecord:
    """Canonical AnalysisResult classification record."""

    classification_id: str
    name: str
    label: str
    threshold: float | None = None
    confidence: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "classification_id",
            _require_identifier(self.classification_id, "classification_id"),
        )
        object.__setattr__(self, "name", _require_non_empty_text(self.name, "name"))
        object.__setattr__(self, "label", _require_non_empty_text(self.label, "label"))
        if self.threshold is not None:
            object.__setattr__(
                self,
                "threshold",
                _finite_float(self.threshold, "threshold"),
            )
        if self.confidence is not None:
            confidence = _finite_float(self.confidence, "confidence")
            if confidence < 0.0 or confidence > 1.0:
                raise AnalyzerModelError("confidence must be between 0 and 1.")
            object.__setattr__(self, "confidence", confidence)
        object.__setattr__(self, "metadata", _require_mapping(self.metadata, "metadata"))

    def to_dict(self) -> dict[str, Any]:
        """Return a schema-conformant classification dictionary."""
        payload: dict[str, Any] = {
            "classification_id": self.classification_id,
            "name": self.name,
            "label": self.label,
        }
        if self.threshold is not None:
            payload["threshold"] = self.threshold
        if self.confidence is not None:
            payload["confidence"] = self.confidence
        if self.metadata:
            payload["metadata"] = self.metadata
        return to_json_safe(payload)


@dataclass(frozen=True)
class AnalysisContext:
    """Run context used while assembling analysis results."""

    run_id: str
    selected_metrics: tuple[str, ...]
    config_snapshot: dict[str, Any]
    permissions: dict[str, bool]
    execution: dict[str, Any]
    random_seed: int | None
    created_at: str
    git_commit: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "run_id", _require_identifier(self.run_id, "run_id"))
        if not self.selected_metrics:
            raise AnalyzerModelError("selected_metrics must not be empty.")
        object.__setattr__(
            self,
            "selected_metrics",
            tuple(_require_non_empty_text(item, "selected_metrics") for item in self.selected_metrics),
        )
        object.__setattr__(
            self,
            "config_snapshot",
            _require_mapping(self.config_snapshot, "config_snapshot"),
        )
        object.__setattr__(
            self,
            "permissions",
            _require_mapping(self.permissions, "permissions"),
        )
        object.__setattr__(
            self,
            "execution",
            _require_mapping(self.execution, "execution"),
        )
        object.__setattr__(
            self,
            "created_at",
            _require_non_empty_text(self.created_at, "created_at"),
        )


@dataclass(frozen=True)
class AnalysisResultRecord:
    """Canonical AnalysisResult JSON wrapper."""

    analysis_result_id: str
    candidate_ref: dict[str, Any]
    metrics: tuple[MetricRecord, ...]
    cost: CostRecord
    classifications: tuple[ClassificationRecord, ...] = ()
    provenance: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    extensions: dict[str, Any] = field(default_factory=dict)
    schema_version: str = ANALYSIS_RESULT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != ANALYSIS_RESULT_SCHEMA_VERSION:
            raise AnalyzerModelError(
                f"schema_version must be {ANALYSIS_RESULT_SCHEMA_VERSION!r}.",
            )
        object.__setattr__(
            self,
            "analysis_result_id",
            _require_identifier(self.analysis_result_id, "analysis_result_id"),
        )
        object.__setattr__(
            self,
            "candidate_ref",
            _require_mapping(self.candidate_ref, "candidate_ref"),
        )
        if any(not isinstance(metric, MetricRecord) for metric in self.metrics):
            raise AnalyzerModelError("metrics must contain MetricRecord values.")
        if not isinstance(self.cost, CostRecord):
            raise AnalyzerModelError("cost must be a CostRecord.")
        if any(
            not isinstance(item, ClassificationRecord)
            for item in self.classifications
        ):
            raise AnalyzerModelError(
                "classifications must contain ClassificationRecord values.",
            )
        object.__setattr__(
            self,
            "provenance",
            _require_mapping(self.provenance, "provenance"),
        )
        object.__setattr__(self, "metadata", _require_mapping(self.metadata, "metadata"))
        object.__setattr__(
            self,
            "extensions",
            _require_mapping(self.extensions, "extensions"),
        )

    def to_dict(self) -> dict[str, Any]:
        """Return a schema-conformant AnalysisResult document."""
        payload: dict[str, Any] = {
            "schema_version": self.schema_version,
            "analysis_result_id": self.analysis_result_id,
            "candidate_ref": self.candidate_ref,
            "metrics": [metric.to_dict() for metric in self.metrics],
            "cost": self.cost.to_dict(),
            "classifications": [
                classification.to_dict()
                for classification in self.classifications
            ],
            "provenance": self.provenance,
        }
        if self.metadata:
            payload["metadata"] = self.metadata
        if self.extensions:
            payload["extensions"] = self.extensions
        return to_json_safe(payload)


_SHA256_RE = re.compile(r"^[a-fA-F0-9]{64}$")


def _require_identifier(value: object, field_name: str) -> str:
    text = _require_non_empty_text(value, field_name)
    if not _IDENTIFIER_RE.fullmatch(text):
        raise AnalyzerModelError(f"{field_name} is not a valid schema identifier.")
    return text


def _require_non_empty_text(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise AnalyzerModelError(f"{field_name} must be a string.")
    text = value.strip()
    if not text:
        raise AnalyzerModelError(f"{field_name} must not be empty.")
    return text


def _require_mapping(value: object, field_name: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise AnalyzerModelError(f"{field_name} must be a mapping.")
    return to_json_safe(dict(value))


def _require_positive_int(value: object, field_name: str) -> int:
    if type(value) is not int or value < 1:
        raise AnalyzerModelError(f"{field_name} must be a positive integer.")
    return value


def _require_non_negative_int(value: object, field_name: str) -> int:
    if type(value) is not int or value < 0:
        raise AnalyzerModelError(f"{field_name} must be a non-negative integer.")
    return value


def _finite_float(value: object, field_name: str) -> float:
    if type(value) not in {int, float}:
        raise AnalyzerModelError(f"{field_name} must be numeric.")
    number = float(value)
    if number != number or number in {float("inf"), float("-inf")}:
        raise AnalyzerModelError(f"{field_name} must be finite.")
    return number


__all__ = [
    "ANALYSIS_RESULT_SCHEMA_VERSION",
    "METRIC_STATUSES",
    "AnalysisContext",
    "AnalysisResultRecord",
    "AnalyzerModelError",
    "CandidateView",
    "ClassificationRecord",
    "CostRecord",
    "MetricRecord",
    "OperationView",
]
