"""Export generator candidate records as canonical Candidate JSON."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from verfeinert import __version__
from verfeinert.core import current_git_commit, ensure_output_root, stable_hash, to_json_safe, write_json
from verfeinert.core.schema_resources import load_schema as load_packaged_schema
from verfeinert.core.validation import CoreValidationError, require_identifier, require_non_empty_text

from ..operations import DEFAULT_GATE_REGISTRY
from ..validation import GeneratorValidationError


CANDIDATE_SCHEMA_VERSION = "verfeinert.candidate.v1"
CANONICAL_CANDIDATE_HASH_SCHEMA_VERSION = "verfeinert.candidate_hash.v1"
DEFAULT_GATE_NAMESPACE = "verfeinert.default_gates"
DEFAULT_EXPORTER_LABEL = "verfeinert.ansatz_generator"
ALLOWED_SOURCE_KINDS = {"template", "mutation", "import", "manual", "generated"}
ALLOWED_OPERATION_ROLES = {
    "rotation",
    "entangler",
    "controlled_rotation",
    "basis_change",
    "measurement_preparation",
    "other",
}


@dataclass(frozen=True)
class CandidateJsonExportConfig:
    """Options for exporting one generator record as canonical Candidate JSON."""

    candidate_id: str | None = None
    candidate_id_prefix: str | None = None
    n_qubits: int | None = None
    created_at: str | None = None
    source_kind: str | None = None
    source_label: str = DEFAULT_EXPORTER_LABEL
    software_version: str = __version__
    git_commit: str | None = None
    discover_git_commit: bool = True
    input_hashes: Mapping[str, str] = field(default_factory=dict)
    gate_namespace: str = DEFAULT_GATE_NAMESPACE
    metadata: Mapping[str, Any] = field(default_factory=dict)
    hash_schema_version: str = CANONICAL_CANDIDATE_HASH_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.candidate_id is not None:
            object.__setattr__(self, "candidate_id", _require_identifier(self.candidate_id, "candidate_id"))
        if self.candidate_id_prefix is not None:
            object.__setattr__(self, "candidate_id_prefix", _require_identifier(self.candidate_id_prefix, "candidate_id_prefix"))
        if self.n_qubits is not None:
            if type(self.n_qubits) is not int or self.n_qubits < 1:
                raise GeneratorValidationError("n_qubits must be None or a positive integer.")
        if self.source_kind is not None and self.source_kind not in ALLOWED_SOURCE_KINDS:
            allowed = ", ".join(sorted(ALLOWED_SOURCE_KINDS))
            raise GeneratorValidationError(f"source_kind must be one of: {allowed}.")
        object.__setattr__(self, "source_label", require_non_empty_text(self.source_label, "source_label"))
        object.__setattr__(self, "software_version", require_non_empty_text(self.software_version, "software_version"))
        object.__setattr__(self, "gate_namespace", require_non_empty_text(self.gate_namespace, "gate_namespace"))
        object.__setattr__(
            self,
            "hash_schema_version",
            require_non_empty_text(self.hash_schema_version, "hash_schema_version"),
        )
        object.__setattr__(self, "input_hashes", _hash_mapping(self.input_hashes))
        object.__setattr__(self, "metadata", to_json_safe(dict(self.metadata)))


def export_candidate_json(
    record: Mapping[str, Any] | Any,
    *,
    config: CandidateJsonExportConfig | None = None,
    candidate_id: str | None = None,
    id_map: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Return a schema-validated canonical Candidate JSON document."""
    export_config = config or CandidateJsonExportConfig()
    source = _record_mapping(record)
    canonical_id = (
        _require_identifier(candidate_id, "candidate_id")
        if candidate_id is not None
        else _canonical_candidate_id(source, export_config)
    )
    parameter_state = _ParameterState()
    operations = _canonical_operations(
        _raw_operations(source),
        gate_namespace=export_config.gate_namespace,
        parameter_state=parameter_state,
    )
    parameters = parameter_state.parameters()
    n_qubits = _canonical_n_qubits(operations, configured_n_qubits=export_config.n_qubits, source=source)
    circuit = {
        "n_qubits": n_qubits,
        "wire_order": list(range(n_qubits)),
        "parameters": parameters,
        "operations": operations,
    }
    lineage = _canonical_lineage(source, canonical_id, id_map=id_map)
    candidate = {
        "schema_version": CANDIDATE_SCHEMA_VERSION,
        "candidate_id": canonical_id,
        "identity": {
            "structural_hash": _canonical_structural_hash(circuit),
            "lineage_hash": stable_hash(lineage),
            "hash_schema_version": export_config.hash_schema_version,
        },
        "circuit": circuit,
        "lineage": lineage,
        "metadata": _canonical_metadata(source, export_config),
        "provenance": _canonical_provenance(source, lineage, export_config),
    }
    return validate_candidate_json(candidate)


def write_candidate_json(
    record: Mapping[str, Any] | Any,
    path: str | Path,
    *,
    config: CandidateJsonExportConfig | None = None,
    candidate_id: str | None = None,
    id_map: Mapping[str, str] | None = None,
) -> Path:
    """Write one canonical Candidate JSON document after schema validation."""
    target = Path(path).expanduser().resolve(strict=False)
    ensure_output_root(target.parent, source_root=_package_source_root())
    candidate = export_candidate_json(
        record,
        config=config,
        candidate_id=candidate_id,
        id_map=id_map,
    )
    return write_json(target, candidate)


def validate_candidate_json(candidate: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a canonical Candidate JSON mapping and return a JSON-safe copy."""
    payload = to_json_safe(dict(candidate))
    _candidate_validator().validate(payload)
    return payload


def _record_mapping(record: Mapping[str, Any] | Any) -> dict[str, Any]:
    if isinstance(record, Mapping):
        return to_json_safe(dict(record))
    to_dict = getattr(record, "to_dict", None)
    if callable(to_dict):
        payload = to_dict()
        if isinstance(payload, Mapping):
            return to_json_safe(dict(payload))
    raise TypeError("record must be a mapping or expose to_dict().")


def _raw_operations(source: Mapping[str, Any]) -> list[dict[str, Any]]:
    genome = _mapping_or_empty(source.get("genome"))
    metadata = _mapping_or_empty(source.get("metadata"))
    raw = _first_non_none(source.get("operations"), genome.get("operations"), metadata.get("operations"))
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        raise GeneratorValidationError("candidate operations must be a sequence.")
    operations: list[dict[str, Any]] = []
    for operation in raw:
        if isinstance(operation, Mapping):
            operations.append(to_json_safe(dict(operation)))
            continue
        to_dict = getattr(operation, "to_dict", None)
        if callable(to_dict):
            payload = to_dict()
            if isinstance(payload, Mapping):
                operations.append(to_json_safe(dict(payload)))
                continue
        raise GeneratorValidationError("candidate operations must contain mappings or Operation records.")
    if not operations:
        raise GeneratorValidationError("candidate operations must not be empty.")
    return operations


def _canonical_operations(
    operations: Sequence[Mapping[str, Any]],
    *,
    gate_namespace: str,
    parameter_state: "_ParameterState",
) -> list[dict[str, Any]]:
    canonical: list[dict[str, Any]] = []
    for order, operation in enumerate(operations):
        metadata = _mapping_or_empty(operation.get("metadata"))
        gate_name = DEFAULT_GATE_REGISTRY.normalize(str(_first_non_none(operation.get("gate"), operation.get("name"))))
        gate_def = DEFAULT_GATE_REGISTRY.get(gate_name)
        qubits = _operation_qubits(operation)
        if len(qubits) != gate_def.n_wires:
            raise GeneratorValidationError(f"gate {gate_name!r} expects {gate_def.n_wires} qubit(s).")
        canonical.append(
            {
                "operation_id": f"op-{order:03d}",
                "gate": {
                    "name": gate_name,
                    "namespace": gate_namespace,
                },
                "qubits": qubits,
                "parameters": _operation_parameters(operation, gate_def.n_params, parameter_state),
                "layer": _non_negative_int(
                    _first_non_none(operation.get("layer"), metadata.get("layer_index"), 0),
                    field_name="operation.layer",
                ),
                "order": order,
                "role": _operation_role(operation, gate_name, qubits),
                "metadata": _operation_metadata(operation, metadata, order),
            }
        )
    return canonical


def _operation_parameters(
    operation: Mapping[str, Any],
    expected_count: int,
    parameter_state: "_ParameterState",
) -> list[dict[str, Any]]:
    raw_params = _first_non_none(operation.get("params"), operation.get("parameters"))
    if raw_params is None:
        values: list[Any] = []
    elif isinstance(raw_params, Sequence) and not isinstance(raw_params, (str, bytes)):
        values = list(raw_params)
    else:
        values = [raw_params]

    if values:
        return [_canonical_parameter_value(value, parameter_state) for value in values]

    parameterized = bool(operation.get("parameterized", expected_count > 0))
    if parameterized:
        return [
            {"kind": "reference", "parameter_id": parameter_state.generated_parameter_id()}
            for _ in range(expected_count or 1)
        ]
    return []


def _canonical_parameter_value(value: Any, parameter_state: "_ParameterState") -> dict[str, Any]:
    if isinstance(value, Mapping):
        kind = value.get("kind")
        if kind == "reference" and value.get("parameter_id") is not None:
            parameter_id = _require_identifier(str(value["parameter_id"]), "parameter_id")
            parameter_state.register(parameter_id, str(value.get("symbol") or parameter_id.replace("-", "_")))
            return {"kind": "reference", "parameter_id": parameter_id}
        if kind == "literal" and "value" in value:
            return {"kind": "literal", "value": to_json_safe(value["value"])}
        raise GeneratorValidationError("parameter mappings must be canonical reference or literal records.")
    if isinstance(value, str):
        return {
            "kind": "reference",
            "parameter_id": parameter_state.symbol_parameter_id(value),
        }
    return {"kind": "literal", "value": to_json_safe(value)}


def _operation_qubits(operation: Mapping[str, Any]) -> list[int]:
    raw = _first_non_none(operation.get("wires"), operation.get("qubits"))
    if raw is None:
        raise GeneratorValidationError("operation qubits are required.")
    if isinstance(raw, int):
        values = [raw]
    elif isinstance(raw, Sequence) and not isinstance(raw, (str, bytes)):
        values = list(raw)
    else:
        raise GeneratorValidationError("operation qubits must be an integer or sequence of integers.")
    qubits = [int(value) for value in values]
    if not qubits or any(qubit < 0 for qubit in qubits):
        raise GeneratorValidationError("operation qubits must be non-empty non-negative integers.")
    if len(set(qubits)) != len(qubits):
        raise GeneratorValidationError("operation qubits must not repeat.")
    return qubits


def _operation_role(operation: Mapping[str, Any], gate_name: str, qubits: Sequence[int]) -> str:
    metadata = _mapping_or_empty(operation.get("metadata"))
    metadata_role = metadata.get("role")
    if metadata_role in ALLOWED_OPERATION_ROLES:
        return str(metadata_role)
    if gate_name in {"rx", "ry", "rz"}:
        return "rotation"
    if gate_name in {"crx", "cry", "crz"}:
        return "controlled_rotation"
    if gate_name == "h":
        return "basis_change"
    if len(qubits) == 2:
        return "entangler"
    return "other"


def _operation_metadata(operation: Mapping[str, Any], metadata: Mapping[str, Any], order: int) -> dict[str, Any]:
    payload = dict(to_json_safe(dict(metadata)))
    payload.setdefault("source_order", _non_negative_int(_first_non_none(metadata.get("order"), operation.get("order"), order), field_name="operation.order"))
    return payload


def _canonical_n_qubits(
    operations: Sequence[Mapping[str, Any]],
    *,
    configured_n_qubits: int | None,
    source: Mapping[str, Any],
) -> int:
    observed = max(qubit for operation in operations for qubit in operation["qubits"]) + 1
    source_n_qubits = _optional_positive_int(_first_non_none(source.get("n_qubits"), source.get("num_qubits")))
    selected = configured_n_qubits or source_n_qubits or observed
    if selected < observed:
        raise GeneratorValidationError("n_qubits cannot be smaller than the largest operation qubit index.")
    return selected


def _canonical_lineage(
    source: Mapping[str, Any],
    candidate_id: str,
    *,
    id_map: Mapping[str, str] | None,
) -> dict[str, Any]:
    lineage_source = _mapping_or_empty(source.get("lineage"))
    generation = _non_negative_int(
        _first_non_none(source.get("generation_index"), lineage_source.get("generation_index"), 0),
        field_name="lineage.generation",
    )
    raw_parent = _optional_string(_first_non_none(source.get("parent_circuit_id"), source.get("parent_id"), lineage_source.get("parent_circuit_id")))
    raw_root = _optional_string(_first_non_none(source.get("root_circuit_id"), source.get("root_id"), lineage_source.get("root_circuit_id")))
    parent_candidate_id = _mapped_identifier(raw_parent, id_map) if raw_parent else None
    root_candidate_id = _mapped_identifier(raw_root, id_map) if raw_root else candidate_id
    mutation = _canonical_mutation(source, candidate_id, parent_candidate_id, id_map=id_map)
    return {
        "generation": generation,
        "root_candidate_id": root_candidate_id,
        "parent_candidate_id": parent_candidate_id,
        "mutation": mutation,
    }


def _canonical_mutation(
    source: Mapping[str, Any],
    candidate_id: str,
    parent_candidate_id: str | None,
    *,
    id_map: Mapping[str, str] | None,
) -> dict[str, Any] | None:
    metadata = _mapping_or_empty(source.get("metadata"))
    mutation_type = _optional_string(_first_non_none(source.get("mutation_type"), metadata.get("mutation_type")))
    if not mutation_type or mutation_type == "base_sanz_parent":
        return None
    source_id = parent_candidate_id or _mapped_identifier(_source_id(source), id_map) or candidate_id
    parameters = {
        key: source.get(key)
        for key in (
            "mutation_status",
            "mutation_original_position",
            "mutation_new_position",
            "mutation_target_gate_index",
            "mutation_target_wires",
            "variant_index",
        )
        if source.get(key) is not None
    }
    return {
        "mutation_id": _require_identifier(_optional_string(source.get("mutation_id")) or f"{candidate_id}-mutation", "mutation_id"),
        "type": mutation_type,
        "source_candidate_id": source_id,
        "operation": _optional_string(_first_non_none(source.get("mutation_gate"), source.get("mutation_target_gate_name"), metadata.get("mutation_gate"))),
        "parameters": to_json_safe(parameters),
        "metadata": {
            key: to_json_safe(value)
            for key, value in metadata.items()
            if str(key).startswith("mutation_")
        },
    }


def _canonical_metadata(source: Mapping[str, Any], config: CandidateJsonExportConfig) -> dict[str, Any]:
    metadata = _mapping_or_empty(source.get("metadata"))
    payload = {
        **metadata,
        "generator_source": "verfeinert.ansatz_generator",
        "source_record_id": _source_id(source),
    }
    for key in ("template_id", "ansatz_id", "layer", "recipe_id", "source_backend_name"):
        if source.get(key) is not None:
            payload[key] = source[key]
    payload.update(dict(config.metadata))
    return to_json_safe(payload)


def _canonical_provenance(
    source: Mapping[str, Any],
    lineage: Mapping[str, Any],
    config: CandidateJsonExportConfig,
) -> dict[str, Any]:
    source_kind = config.source_kind or _infer_source_kind(source, lineage)
    git_commit = config.git_commit
    if git_commit is None and config.discover_git_commit:
        git_commit = current_git_commit()
    return {
        "created_at": config.created_at or _utc_timestamp(),
        "source": {
            "kind": source_kind,
            "label": config.source_label,
        },
        "software_version": config.software_version,
        "git_commit": git_commit,
        "input_hashes": dict(config.input_hashes),
    }


def _infer_source_kind(source: Mapping[str, Any], lineage: Mapping[str, Any]) -> str:
    if lineage.get("mutation") is not None:
        return "mutation"
    metadata = _mapping_or_empty(source.get("metadata"))
    mutation_type = _optional_string(_first_non_none(source.get("mutation_type"), metadata.get("mutation_type")))
    if mutation_type == "base_sanz_parent" or metadata.get("source") == "SANZ19":
        return "template"
    return "generated"


def _canonical_structural_hash(circuit: Mapping[str, Any]) -> str:
    return stable_hash(
        {
            "n_qubits": circuit["n_qubits"],
            "wire_order": circuit.get("wire_order"),
            "parameters": circuit["parameters"],
            "operations": circuit["operations"],
        }
    )


def _canonical_candidate_id(
    source: Mapping[str, Any],
    config: CandidateJsonExportConfig,
) -> str:
    if config.candidate_id is not None:
        return config.candidate_id
    raw_id = _source_id(source)
    if config.candidate_id_prefix:
        template_id = _optional_string(_first_non_none(source.get("template_id"), source.get("ansatz_id")))
        layer = _optional_positive_int(source.get("layer"))
        if template_id is not None and layer is not None:
            return _require_identifier(
                f"{config.candidate_id_prefix}-{template_id.lower()}-l{layer}",
                "candidate_id",
            )
        return _require_identifier(f"{config.candidate_id_prefix}-{_identifier_token(raw_id)}", "candidate_id")
    return _require_identifier(_identifier_token(raw_id), "candidate_id")


def _source_id(source: Mapping[str, Any]) -> str:
    value = _first_non_none(source.get("circuit_id"), source.get("child_id"), source.get("candidate_id"), source.get("id"))
    if value is None:
        raise GeneratorValidationError("candidate record must contain circuit_id, child_id, candidate_id, or id.")
    return require_non_empty_text(str(value), "source candidate id")


def _mapped_identifier(value: str | None, id_map: Mapping[str, str] | None) -> str | None:
    if value is None:
        return None
    mapped = id_map.get(value) if id_map is not None else None
    return _require_identifier(mapped or _identifier_token(value), "lineage candidate id")


def _identifier_token(value: str) -> str:
    token = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(value).strip()).strip("-_.").lower()
    if not token:
        token = "candidate"
    if not token[0].isalnum():
        token = f"candidate-{token}"
    return token


def _hash_mapping(value: Mapping[str, str]) -> dict[str, str]:
    payload: dict[str, str] = {}
    for key, digest in dict(value).items():
        payload[_require_identifier(str(key), "input_hashes key")] = require_non_empty_text(str(digest), "input_hashes value")
    return payload


def _candidate_validator() -> Draft202012Validator:
    schema = _read_schema("candidate")
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())


def _read_schema(name: str) -> dict[str, Any]:
    return load_packaged_schema(name)


def _package_source_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _mapping_or_empty(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _first_non_none(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _non_negative_int(value: Any, *, field_name: str) -> int:
    if type(value) is bool:
        raise GeneratorValidationError(f"{field_name} must be a non-negative integer.")
    number = int(value)
    if number < 0:
        raise GeneratorValidationError(f"{field_name} must be a non-negative integer.")
    return number


def _optional_positive_int(value: Any) -> int | None:
    if value is None:
        return None
    if type(value) is bool:
        raise GeneratorValidationError("integer fields must not be booleans.")
    number = int(value)
    if number < 1:
        raise GeneratorValidationError("integer fields must be positive.")
    return number


def _require_identifier(value: str, field_name: str) -> str:
    try:
        return require_identifier(value, field_name)
    except CoreValidationError as exc:
        raise GeneratorValidationError(str(exc)) from exc


class _ParameterState:
    def __init__(self) -> None:
        self._by_symbol: dict[str, str] = {}
        self._registered: set[str] = set()
        self._records: list[dict[str, str]] = []

    def generated_parameter_id(self) -> str:
        parameter_id = f"theta-{len(self._by_symbol):03d}"
        self.register(parameter_id, parameter_id.replace("-", "_"))
        return parameter_id

    def symbol_parameter_id(self, symbol: str) -> str:
        normalized_symbol = require_non_empty_text(symbol, "parameter symbol")
        if normalized_symbol not in self._by_symbol:
            parameter_id = f"theta-{len(self._by_symbol):03d}"
            self.register(parameter_id, normalized_symbol)
            self._by_symbol[normalized_symbol] = parameter_id
        return self._by_symbol[normalized_symbol]

    def register(self, parameter_id: str, symbol: str) -> None:
        selected = _require_identifier(parameter_id, "parameter_id")
        if selected not in self._registered:
            self._registered.add(selected)
            self._by_symbol.setdefault(symbol, selected)
            self._records.append(
                {
                    "parameter_id": selected,
                    "kind": "trainable",
                    "symbol": require_non_empty_text(symbol, "parameter symbol"),
                }
            )

    def parameters(self) -> list[dict[str, str]]:
        return [dict(record) for record in self._records]


__all__ = [
    "CANONICAL_CANDIDATE_HASH_SCHEMA_VERSION",
    "CANDIDATE_SCHEMA_VERSION",
    "CandidateJsonExportConfig",
    "export_candidate_json",
    "validate_candidate_json",
    "write_candidate_json",
]
