"""Metadata-only candidate compilation and optional callable-source generation."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import csv
import json
from pathlib import Path
import re
from typing import Any, Mapping, Sequence

from verfeinert.core.io import ensure_output_root, read_json, to_json_safe, write_json
from verfeinert.core.validation import require_bool, require_non_empty_text

from .operations import KNOWN_BETA_GATES, PARAMETERIZED_GATES, TWO_QUBIT_GATES
from .validation import GeneratorValidationError


CANDIDATE_HASH_SCHEMA_VERSION = "verfeinert.generator.candidate_hash.beta_v1"
CANDIDATE_METADATA_SCHEMA_VERSION = "verfeinert.compiled_candidates.v1"
CANDIDATE_MANIFEST_SCHEMA_VERSION = "verfeinert.candidate_compilation_manifest.v1"

CALLABLE_BACKEND = "pennylane_source_v0"


@dataclass(frozen=True)
class CandidateCompilationConfig:
    """Configuration for metadata-only candidate compilation."""

    run_id: str
    package_name: str = "compiled_evolver_candidates"
    output_root: str | Path | None = None
    generation_index: int | None = None
    require_operations: bool = False
    require_parameter_count: bool = False
    require_parent_links: bool = True
    normalize_gates: bool = True
    allow_metadata_only: bool = True
    write_csv: bool = True
    write_json: bool = True
    write_manifest: bool = True
    write_callable_module: bool = False
    callable_module_name: str = "compiled_candidate_ansatzes.py"
    callable_backend: str = CALLABLE_BACKEND
    callable_registry_name: str = "CIRCUIT_REGISTRY"
    allow_unsupported_gates_in_callable_module: bool = False
    scientific_validity_label: str = "compiled_metadata_not_scientifically_evaluated"
    random_seed: int = 42

    def __post_init__(self) -> None:
        for field_name in (
            "run_id",
            "package_name",
            "callable_module_name",
            "callable_backend",
            "callable_registry_name",
            "scientific_validity_label",
        ):
            object.__setattr__(
                self,
                field_name,
                require_non_empty_text(getattr(self, field_name), field_name),
            )
        if self.callable_backend != CALLABLE_BACKEND:
            raise GeneratorValidationError(f"callable_backend must be {CALLABLE_BACKEND!r}.")
        if self.generation_index is not None:
            if type(self.generation_index) is not int or self.generation_index < 0:
                raise GeneratorValidationError("generation_index must be None or >= 0.")
        if type(self.random_seed) is not int:
            raise TypeError("random_seed must be an integer.")
        for field_name in (
            "require_operations",
            "require_parameter_count",
            "require_parent_links",
            "normalize_gates",
            "allow_metadata_only",
            "write_csv",
            "write_json",
            "write_manifest",
            "write_callable_module",
            "allow_unsupported_gates_in_callable_module",
        ):
            object.__setattr__(self, field_name, require_bool(getattr(self, field_name), field_name))


@dataclass(frozen=True)
class CandidateValidationIssue:
    """Validation warning or error for a compiled candidate."""

    circuit_id: str | None
    severity: str
    field: str
    message: str

    def __post_init__(self) -> None:
        if self.severity not in {"warning", "error"}:
            raise GeneratorValidationError("severity must be 'warning' or 'error'.")
        object.__setattr__(self, "field", require_non_empty_text(self.field, "issue.field"))
        object.__setattr__(self, "message", require_non_empty_text(self.message, "issue.message"))

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe issue record."""
        return to_json_safe(asdict(self))


@dataclass(frozen=True)
class CompiledCandidateRecord:
    """Analyzer-staging-friendly metadata record for one compiled candidate."""

    circuit_id: str
    generation_index: int
    parent_circuit_id: str | None
    root_circuit_id: str
    layer: int
    variant_index: int | None
    recipe_id: str | None
    operations: list[dict[str, Any]]
    parameter_count: int | None
    operation_count: int
    two_qubit_operation_count: int
    structural_hash: str
    lineage_provenance_hash: str
    source_candidate_id: str
    source_backend_name: str | None
    scientific_circuit_validity: str
    requires_generator_compilation: bool
    compiled_metadata_validated: bool
    callable_module: str | None
    callable_name: str | None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe candidate record."""
        return to_json_safe(asdict(self))


@dataclass(frozen=True)
class CandidateCompilationResult:
    """Result of compiling candidate records into staged metadata."""

    records: list[dict[str, Any]]
    output_root: Path | None
    metadata_json_path: Path | None
    metadata_csv_path: Path | None
    manifest_path: Path | None
    callable_module_path: Path | None
    issues: list[CandidateValidationIssue]
    package_manifest: dict[str, Any]
    wrote_files: tuple[str, ...]
    callable_generation_supported: bool = False
    scientific_metrics_executed: bool = False
    qnodes_executed: bool = False

    def issue_records(self) -> list[dict[str, Any]]:
        """Return JSON-safe validation issue records."""
        return [issue.to_dict() for issue in self.issues]


def normalize_operation_record(
    operation: Mapping[str, Any] | Sequence[Any],
    *,
    config: CandidateCompilationConfig,
) -> dict[str, Any]:
    """Normalize one operation record."""
    normalized, issues = _normalize_operation_record_with_issues(
        operation,
        config=config,
        circuit_id=None,
    )
    errors = [issue for issue in issues if issue.severity == "error"]
    if errors:
        raise GeneratorValidationError(errors[0].message)
    return normalized


def normalize_candidate_record(
    record: Mapping[str, Any],
    *,
    config: CandidateCompilationConfig,
) -> tuple[dict[str, Any], list[CandidateValidationIssue]]:
    """Normalize a generic candidate mapping for analyzer/evolver staging."""
    if not isinstance(record, Mapping):
        raise TypeError("record must be a mapping.")
    source = dict(record)
    metadata = _dict_or_empty(source.get("metadata"))
    genome = _dict_or_empty(source.get("genome"))
    candidate_id = _first_present(source, ("circuit_id", "child_id", "candidate_id", "id"))
    source_candidate_id = str(candidate_id) if candidate_id is not None else ""
    issues: list[CandidateValidationIssue] = []
    if not source_candidate_id.strip():
        issues.append(_issue(None, "error", "circuit_id", "missing circuit_id"))
        source_candidate_id = "missing_circuit_id"
    circuit_id = source_candidate_id

    generation_index = _optional_int(source.get("generation_index", config.generation_index))
    if generation_index is None:
        generation_index = 0
    if generation_index < 0:
        issues.append(_issue(circuit_id, "error", "generation_index", "must be >= 0"))

    parent_circuit_id = _optional_string(_first_present(source, ("parent_circuit_id", "parent_id")))
    root_circuit_id = (
        _optional_string(_first_present(source, ("root_circuit_id", "root_id")))
        or parent_circuit_id
        or circuit_id
    )
    if config.require_parent_links and generation_index > 0 and not parent_circuit_id:
        issues.append(
            _issue(
                circuit_id,
                "error",
                "parent_circuit_id",
                "parent_circuit_id is required for generated candidates",
            )
        )

    layer = _optional_int(source.get("layer", metadata.get("layer")))
    if layer is None or layer <= 0:
        issues.append(_issue(circuit_id, "error", "layer", "layer must be positive"))
        layer = 0

    raw_operations = _first_non_none(
        source.get("operations"),
        metadata.get("operations"),
        genome.get("operations"),
    )
    normalized_operations: list[dict[str, Any]] = []
    if raw_operations is None:
        severity = "error" if config.require_operations else "warning"
        issues.append(_issue(circuit_id, severity, "operations", "operations are missing"))
    elif not isinstance(raw_operations, (list, tuple)):
        issues.append(_issue(circuit_id, "error", "operations", "operations must be a list or tuple"))
    else:
        for operation in raw_operations:
            try:
                normalized, operation_issues = _normalize_operation_record_with_issues(
                    operation,
                    config=config,
                    circuit_id=circuit_id,
                )
            except (TypeError, ValueError) as exc:
                issues.append(_issue(circuit_id, "error", "operations", str(exc)))
                continue
            normalized_operations.append(normalized)
            issues.extend(operation_issues)

    explicit_operation_count = _optional_int(source.get("operation_count"))
    operation_count = explicit_operation_count if explicit_operation_count is not None else len(normalized_operations)
    explicit_two_qubit_count = _optional_int(source.get("two_qubit_operation_count"))
    two_qubit_operation_count = (
        explicit_two_qubit_count
        if explicit_two_qubit_count is not None
        else _two_qubit_count(normalized_operations)
    )
    explicit_parameter_count = _optional_int(source.get("parameter_count"))
    parameter_count = explicit_parameter_count if explicit_parameter_count is not None else _parameter_count(normalized_operations)
    if parameter_count is None:
        severity = "error" if config.require_parameter_count else "warning"
        issues.append(_issue(circuit_id, severity, "parameter_count", "parameter_count is missing and could not be derived"))

    source_backend_name = _optional_string(
        _first_non_none(
            source.get("source_backend_name"),
            metadata.get("beta_backend_name"),
            source.get("beta_backend_name"),
        )
    )
    mutation_metadata = _mutation_metadata(source, metadata)
    structural_hash = _optional_string(source.get("structural_hash"))
    lineage_hash = _optional_string(
        source.get("lineage_provenance_hash")
        or source.get("lineage_hash")
        or metadata.get("lineage_provenance_hash")
    )
    payload = {
        "circuit_id": circuit_id,
        "generation_index": generation_index,
        "parent_circuit_id": parent_circuit_id,
        "root_circuit_id": root_circuit_id,
        "layer": layer,
        "variant_index": _optional_int(source.get("variant_index")),
        "recipe_id": _optional_string(source.get("recipe_id")),
        "operations": normalized_operations,
        "parameter_count": parameter_count,
        "operation_count": operation_count,
        "two_qubit_operation_count": two_qubit_operation_count,
        "source_candidate_id": source_candidate_id,
        "source_backend_name": source_backend_name,
        "scientific_circuit_validity": config.scientific_validity_label,
        "requires_generator_compilation": True,
        "callable_module": None,
        "callable_name": None,
        "metadata": {
            **metadata,
            **mutation_metadata,
            "candidate_compilation_boundary": "metadata_only",
            "compiler_run_id": config.run_id,
            "requires_generator_compilation": True,
            "hash_schema_version": CANDIDATE_HASH_SCHEMA_VERSION,
        },
    }
    payload["structural_hash"] = structural_hash or compute_candidate_structural_hash(payload)
    payload["lineage_provenance_hash"] = lineage_hash or compute_candidate_lineage_hash(payload)
    payload["compiled_metadata_validated"] = not any(issue.severity == "error" for issue in issues)
    return CompiledCandidateRecord(**payload).to_dict(), issues


def compute_candidate_structural_hash(record: Mapping[str, Any]) -> str:
    """Compute a Beta-compatible deterministic structural hash."""
    payload = {
        "operations": _json_safe(record.get("operations") or []),
        "layer": record.get("layer"),
        "parameter_count": record.get("parameter_count"),
        "operation_count": record.get("operation_count"),
        "two_qubit_operation_count": record.get("two_qubit_operation_count"),
    }
    return _sha256_json_beta(payload)


def compute_candidate_lineage_hash(record: Mapping[str, Any]) -> str:
    """Compute a Beta-compatible deterministic lineage provenance hash."""
    metadata = _dict_or_empty(record.get("metadata"))
    payload = {
        "circuit_id": record.get("circuit_id"),
        "parent_circuit_id": record.get("parent_circuit_id"),
        "root_circuit_id": record.get("root_circuit_id"),
        "generation_index": record.get("generation_index"),
        "variant_index": record.get("variant_index"),
        "mutation_type": record.get("mutation_type") or metadata.get("mutation_type"),
        "mutation_gate": record.get("mutation_gate") or metadata.get("mutation_gate"),
    }
    return _sha256_json_beta(payload)


def sanitize_python_identifier(name: str) -> str:
    """Return a deterministic safe Python identifier."""
    token = re.sub(r"\W+", "_", str(name)).strip("_")
    if not token:
        token = "candidate"
    if token[0].isdigit():
        token = f"candidate_{token}"
    if not token.startswith("candidate_"):
        token = f"candidate_{token}"
    return token


def candidate_callable_name(circuit_id: str) -> str:
    """Return the callable function name for a candidate ID."""
    return sanitize_python_identifier(circuit_id)


def compile_operation_to_source(
    operation: Mapping[str, Any],
    *,
    param_index: int,
    allow_unsupported: bool = False,
) -> tuple[str, int]:
    """Compile one normalized operation to PennyLane source text."""
    if not isinstance(operation, Mapping):
        raise TypeError("operation must be a mapping.")
    gate = str(operation.get("gate", "")).lower()
    wires = operation.get("wires")
    if not isinstance(wires, list) or not wires:
        raise GeneratorValidationError("operation must contain normalized non-empty wires.")
    _validate_wire_arity(gate, wires)
    next_index = int(param_index)
    if gate in PARAMETERIZED_GATES:
        theta = f"params[{next_index}]"
        next_index += 1
        source = _parameterized_gate_source(gate, theta, wires)
    else:
        source = _static_gate_source(gate, wires)
    if source is None:
        if not allow_unsupported:
            raise GeneratorValidationError(f"unsupported gate for callable compilation: {gate!r}")
        return (
            f"    raise NotImplementedError(\"Unsupported gate {gate!r} in compiled candidate callable\")",
            next_index,
        )
    return source, next_index


def compile_candidate_callable_source(
    record: Mapping[str, Any],
    *,
    config: CandidateCompilationConfig,
) -> str:
    """Compile a candidate record into a Python function source string."""
    callable_name = _optional_string(record.get("callable_name")) or candidate_callable_name(str(record.get("circuit_id")))
    operations = record.get("operations") or []
    if not isinstance(operations, list):
        raise GeneratorValidationError("record operations must be a normalized list.")
    lines = [
        f"def {callable_name}(params, *, output_mode=\"state\", hamiltonian=None):",
        "    \"\"\"Apply compiled candidate operations when invoked inside a QNode.\"\"\"",
        "    import pennylane as qml",
        "    params = [] if params is None else list(params)",
    ]
    param_index = 0
    for operation in operations:
        source, param_index = compile_operation_to_source(
            operation,
            param_index=param_index,
            allow_unsupported=config.allow_unsupported_gates_in_callable_module,
        )
        lines.extend(source.splitlines())
    lines.extend(
        [
            "    normalized_mode = str(output_mode).lower()",
            "    if normalized_mode == \"state\":",
            "        return qml.state()",
            "    if normalized_mode == \"expval\":",
            "        if hamiltonian is None:",
            "            raise ValueError(\"hamiltonian is required for expval mode\")",
            "        return qml.expval(hamiltonian)",
            "    raise ValueError(\"output_mode must be 'state' or 'expval'\")",
        ]
    )
    return "\n".join(lines)


def build_callable_module_source(
    records: Sequence[Mapping[str, Any]],
    *,
    config: CandidateCompilationConfig,
) -> str:
    """Build deterministic Python source for compiled candidate callables."""
    records_with_names = _records_with_callable_fields(records, config=config)
    function_sources = [compile_candidate_callable_source(record, config=config) for record in records_with_names]
    registry_entries = [
        f"    {json.dumps(str(record['circuit_id']))}: {record['callable_name']},"
        for record in records_with_names
    ]
    exported_names = _unique_strings(
        (
            "SCIENTIFIC_VALIDITY",
            "QNODES_EXECUTED",
            "SCIENTIFIC_METRICS_EXECUTED",
            config.callable_registry_name,
            "CALLABLE_REGISTRY",
            "CIRCUIT_REGISTRY",
            *(str(record["callable_name"]) for record in records_with_names),
        )
    )
    aliases = []
    if config.callable_registry_name != "CIRCUIT_REGISTRY":
        aliases.append(f"CIRCUIT_REGISTRY = {config.callable_registry_name}")
    aliases.append(f"CALLABLE_REGISTRY = {config.callable_registry_name}")
    all_names = ",\n    ".join(json.dumps(name) for name in exported_names)
    return "\n\n".join(
        [
            '"""Generated candidate callables for Verfeinert metadata packages."""',
            "from __future__ import annotations",
            "",
            'SCIENTIFIC_VALIDITY = "callable_compiled_not_scientifically_evaluated"',
            "QNODES_EXECUTED = False",
            "SCIENTIFIC_METRICS_EXECUTED = False",
            *function_sources,
            f"{config.callable_registry_name} = {{",
            *registry_entries,
            "}",
            *aliases,
            f"__all__ = [\n    {all_names}\n]",
            "",
        ]
    )


def write_callable_module(
    path: str | Path,
    records: Sequence[Mapping[str, Any]],
    *,
    config: CandidateCompilationConfig,
) -> Path:
    """Write generated callable source without importing or invoking it."""
    module_path = Path(path).expanduser().resolve(strict=False)
    if module_path.suffix != ".py":
        raise GeneratorValidationError("callable module path must end in .py.")
    module_path.parent.mkdir(parents=True, exist_ok=True)
    module_path.write_text(build_callable_module_source(records, config=config), encoding="utf-8")
    return module_path


def compile_candidate_records(
    records: Sequence[Mapping[str, Any]],
    *,
    config: CandidateCompilationConfig,
) -> CandidateCompilationResult:
    """Compile generic metadata records into staged candidate metadata."""
    if not isinstance(records, Sequence) or isinstance(records, (str, bytes)):
        raise TypeError("records must be a sequence of mappings.")
    compiled_records: list[dict[str, Any]] = []
    issues: list[CandidateValidationIssue] = []
    seen_ids: set[str] = set()
    for record in records:
        compiled, record_issues = normalize_candidate_record(record, config=config)
        circuit_id = str(compiled["circuit_id"])
        if circuit_id in seen_ids:
            record_issues.append(_issue(circuit_id, "error", "circuit_id", "duplicate circuit_id"))
            compiled["compiled_metadata_validated"] = False
        seen_ids.add(circuit_id)
        compiled_records.append(compiled)
        issues.extend(record_issues)
    errors = [issue for issue in issues if issue.severity == "error"]
    if errors:
        messages = "; ".join(f"{issue.circuit_id or '<unknown>'}:{issue.field}: {issue.message}" for issue in errors)
        raise GeneratorValidationError(f"candidate compilation failed: {messages}")
    if config.write_callable_module:
        compiled_records = _records_with_callable_fields(compiled_records, config=config)
        build_callable_module_source(compiled_records, config=config)
    result = _build_result(
        compiled_records,
        config=config,
        issues=issues,
        output_root=None,
        metadata_json_path=None,
        metadata_csv_path=None,
        manifest_path=None,
        wrote_files=(),
    )
    if config.output_root is not None:
        return write_candidate_staged_package(result, config=config)
    return result


def write_candidate_staged_package(
    result_or_records: CandidateCompilationResult | Sequence[Mapping[str, Any]],
    *,
    config: CandidateCompilationConfig,
) -> CandidateCompilationResult:
    """Write a compiled metadata package under ``config.output_root``."""
    if config.output_root is None:
        if isinstance(result_or_records, CandidateCompilationResult):
            return result_or_records
        return compile_candidate_records(result_or_records, config=config)
    result = (
        result_or_records
        if isinstance(result_or_records, CandidateCompilationResult)
        else compile_candidate_records(result_or_records, config=_config_without_output(config))
    )
    output_root = ensure_output_root(
        config.output_root,
        source_root=Path(__file__).resolve().parents[1],
    )
    package_root = output_root / config.run_id
    package_root.mkdir(parents=True, exist_ok=True)
    metadata_json_path = package_root / "metadata.json" if config.write_json else None
    metadata_csv_path = package_root / "metadata.csv" if config.write_csv else None
    manifest_path = package_root / "package_manifest.json" if config.write_manifest else None
    callable_module_path = package_root / config.callable_module_name if config.write_callable_module else None
    records = _records_with_callable_fields(result.records, config=config) if config.write_callable_module else result.records
    wrote_files: list[str] = []
    manifest = _package_manifest(
        records,
        config=config,
        output_root=package_root,
        metadata_json_path=metadata_json_path,
        metadata_csv_path=metadata_csv_path,
        manifest_path=manifest_path,
        callable_module_path=callable_module_path,
    )
    if callable_module_path is not None:
        write_callable_module(callable_module_path, records, config=config)
        wrote_files.append(str(callable_module_path))
    if metadata_json_path is not None:
        write_json(metadata_json_path, _metadata_json_payload(records, manifest))
        wrote_files.append(str(metadata_json_path))
    if metadata_csv_path is not None:
        _write_csv(metadata_csv_path, records)
        wrote_files.append(str(metadata_csv_path))
    if manifest_path is not None:
        write_json(manifest_path, manifest)
        wrote_files.append(str(manifest_path))
    return _build_result(
        records,
        config=config,
        issues=result.issues,
        output_root=package_root,
        metadata_json_path=metadata_json_path,
        metadata_csv_path=metadata_csv_path,
        manifest_path=manifest_path,
        callable_module_path=callable_module_path,
        wrote_files=tuple(wrote_files),
    )


def load_compiled_candidate_records(path: str | Path) -> list[dict[str, Any]]:
    """Load compiled candidates from metadata JSON or CSV."""
    resolved = Path(path).expanduser().resolve(strict=False)
    if resolved.is_dir():
        json_path = resolved / "metadata.json"
        csv_path = resolved / "metadata.csv"
        if json_path.exists():
            resolved = json_path
        elif csv_path.exists():
            resolved = csv_path
        else:
            raise FileNotFoundError(f"No metadata.json or metadata.csv found in {resolved}")
    if not resolved.exists():
        raise FileNotFoundError(f"compiled candidate metadata not found: {resolved}")
    if resolved.suffix == ".json":
        payload = read_json(resolved)
        records = payload.get("candidates") if isinstance(payload, dict) else payload
        if not isinstance(records, list):
            raise GeneratorValidationError("metadata JSON must contain a candidates list.")
        return [to_json_safe(record) for record in records]
    if resolved.suffix == ".csv":
        with resolved.open("r", encoding="utf-8", newline="") as handle:
            return [{key: _parse_csv_value(value) for key, value in row.items()} for row in csv.DictReader(handle)]
    raise GeneratorValidationError(f"Unsupported compiled candidate file: {resolved}")


def _normalize_operation_record_with_issues(
    operation: Mapping[str, Any] | Sequence[Any],
    *,
    config: CandidateCompilationConfig,
    circuit_id: str | None,
) -> tuple[dict[str, Any], list[CandidateValidationIssue]]:
    if isinstance(operation, Mapping):
        data = dict(operation)
        gate = _optional_string(data.get("gate") or data.get("name"))
        wires_value = data.get("wires", data.get("qubits"))
        params = data.get("params", data.get("parameters"))
        metadata = _dict_or_empty(data.get("metadata"))
        parameterized = data.get("parameterized")
    elif isinstance(operation, (list, tuple)):
        if len(operation) < 2:
            raise GeneratorValidationError("tuple/list operations must contain at least gate and wires.")
        gate = _optional_string(operation[0])
        wires_value = operation[1]
        params = operation[2] if len(operation) > 2 else None
        metadata = {}
        parameterized = None
    else:
        raise GeneratorValidationError("operation must be a mapping, tuple, or list.")
    if not gate:
        raise GeneratorValidationError("operation gate is required.")
    gate = gate.lower() if config.normalize_gates else gate
    wires = _normalize_wires(wires_value)
    if parameterized is None:
        parameterized = gate.lower() in PARAMETERIZED_GATES or bool(params)
    if type(parameterized) is not bool:
        raise GeneratorValidationError("operation parameterized flag must be boolean when provided.")
    issues: list[CandidateValidationIssue] = []
    if gate.lower() not in KNOWN_BETA_GATES:
        severity = "warning" if config.allow_metadata_only else "error"
        issues.append(_issue(circuit_id, severity, "operations.gate", f"unknown gate {gate!r}"))
    else:
        try:
            _validate_wire_arity(gate.lower(), wires)
        except GeneratorValidationError as exc:
            issues.append(_issue(circuit_id, "error", "operations.wires", str(exc)))
    return {
        "gate": gate,
        "wires": wires,
        "parameterized": parameterized,
        "params": _normalize_params(params),
        "metadata": to_json_safe(metadata),
    }, issues


def _records_with_callable_fields(
    records: Sequence[Mapping[str, Any]],
    *,
    config: CandidateCompilationConfig,
) -> list[dict[str, Any]]:
    used_names: dict[str, int] = {}
    result: list[dict[str, Any]] = []
    for record in records:
        copied = dict(record)
        base_name = candidate_callable_name(str(copied["circuit_id"]))
        count = used_names.get(base_name, 0) + 1
        used_names[base_name] = count
        callable_name = base_name if count == 1 else f"{base_name}_{count}"
        copied["callable_module"] = config.callable_module_name
        copied["callable_name"] = callable_name
        copied["scientific_circuit_validity"] = "callable_compiled_not_scientifically_evaluated"
        metadata = _dict_or_empty(copied.get("metadata"))
        metadata["callable_backend"] = config.callable_backend
        metadata["callable_registry_name"] = config.callable_registry_name
        copied["metadata"] = metadata
        result.append(copied)
    return result


def _validate_wire_arity(gate: str, wires: list[int]) -> None:
    if gate in {"rx", "ry", "rz", "x", "y", "z", "h"} and len(wires) != 1:
        raise GeneratorValidationError(f"gate {gate!r} requires exactly one wire.")
    if gate in TWO_QUBIT_GATES and len(wires) != 2:
        raise GeneratorValidationError(f"gate {gate!r} requires exactly two wires.")


def _parameterized_gate_source(gate: str, theta: str, wires: list[int]) -> str | None:
    return {
        "rx": f"    qml.RX({theta}, wires={wires[0]})",
        "ry": f"    qml.RY({theta}, wires={wires[0]})",
        "rz": f"    qml.RZ({theta}, wires={wires[0]})",
        "crx": f"    qml.CRX({theta}, wires={wires!r})",
        "cry": f"    qml.CRY({theta}, wires={wires!r})",
        "crz": f"    qml.CRZ({theta}, wires={wires!r})",
        "isingxx": f"    qml.IsingXX({theta}, wires={wires!r})",
        "isingyy": f"    qml.IsingYY({theta}, wires={wires!r})",
        "isingzz": f"    qml.IsingZZ({theta}, wires={wires!r})",
    }.get(gate)


def _static_gate_source(gate: str, wires: list[int]) -> str | None:
    if gate == "x":
        return f"    qml.PauliX(wires={wires[0]})"
    if gate == "y":
        return f"    qml.PauliY(wires={wires[0]})"
    if gate == "z":
        return f"    qml.PauliZ(wires={wires[0]})"
    if gate == "h":
        return f"    qml.Hadamard(wires={wires[0]})"
    if gate in {"cx", "cnot"}:
        return f"    qml.CNOT(wires={wires!r})"
    if gate == "cz":
        return f"    qml.CZ(wires={wires!r})"
    if gate == "swap":
        return f"    qml.SWAP(wires={wires!r})"
    return None


def _normalize_wires(value: Any) -> list[int]:
    if value is None:
        raise GeneratorValidationError("operation wires are required.")
    if isinstance(value, int):
        wires = [value]
    elif isinstance(value, (list, tuple)):
        wires = list(value)
    else:
        raise GeneratorValidationError("operation wires must be an int, list, or tuple.")
    if not wires:
        raise GeneratorValidationError("operation wires cannot be empty.")
    try:
        normalized = [int(item) for item in wires]
    except Exception as exc:
        raise GeneratorValidationError("operation wires must be integer-like.") from exc
    if any(item < 0 for item in normalized):
        raise GeneratorValidationError("operation wires must be >= 0.")
    if len(set(normalized)) != len(normalized):
        raise GeneratorValidationError("operation wires must not repeat.")
    return normalized


def _normalize_params(value: Any) -> list[Any] | None:
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        return [to_json_safe(item) for item in value]
    return [to_json_safe(value)]


def _parameter_count(operations: list[dict[str, Any]]) -> int | None:
    if not operations:
        return None
    total = 0
    for operation in operations:
        params = operation.get("params")
        if params is not None:
            total += len(params)
        elif operation.get("parameterized"):
            total += 1
    return total


def _two_qubit_count(operations: list[dict[str, Any]]) -> int:
    return sum(
        1
        for operation in operations
        if str(operation.get("gate", "")).lower() in TWO_QUBIT_GATES
        or len(operation.get("wires") or []) == 2
    )


def _build_result(
    records: list[dict[str, Any]],
    *,
    config: CandidateCompilationConfig,
    issues: list[CandidateValidationIssue],
    output_root: Path | None,
    metadata_json_path: Path | None,
    metadata_csv_path: Path | None,
    manifest_path: Path | None,
    callable_module_path: Path | None = None,
    wrote_files: tuple[str, ...],
) -> CandidateCompilationResult:
    manifest = _package_manifest(
        records,
        config=config,
        output_root=output_root,
        metadata_json_path=metadata_json_path,
        metadata_csv_path=metadata_csv_path,
        manifest_path=manifest_path,
        callable_module_path=callable_module_path,
    )
    return CandidateCompilationResult(
        records=records,
        output_root=output_root,
        metadata_json_path=metadata_json_path,
        metadata_csv_path=metadata_csv_path,
        manifest_path=manifest_path,
        callable_module_path=callable_module_path,
        issues=issues,
        package_manifest=manifest,
        wrote_files=wrote_files,
        callable_generation_supported=callable_module_path is not None,
        scientific_metrics_executed=False,
        qnodes_executed=False,
    )


def _package_manifest(
    records: list[dict[str, Any]],
    *,
    config: CandidateCompilationConfig,
    output_root: Path | None,
    metadata_json_path: Path | None,
    metadata_csv_path: Path | None,
    manifest_path: Path | None,
    callable_module_path: Path | None = None,
) -> dict[str, Any]:
    return to_json_safe(
        {
            "schema_version": CANDIDATE_MANIFEST_SCHEMA_VERSION,
            "run_id": config.run_id,
            "package_name": config.package_name,
            "candidate_count": len(records),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "output_root": output_root,
            "metadata_json": metadata_json_path,
            "metadata_csv": metadata_csv_path,
            "manifest_path": manifest_path,
            "callable_module": callable_module_path,
            "callable_registry_name": config.callable_registry_name,
            "callable_backend": config.callable_backend,
            "callable_generation_supported": callable_module_path is not None,
            "source": "ansatz_generator_candidate_compilation_boundary",
            "scientific_metrics_executed": False,
            "qnodes_executed": False,
            "limitation": "Candidates are metadata/staged candidates, not scientifically evaluated circuits.",
        }
    )


def _metadata_json_payload(records: list[dict[str, Any]], manifest: dict[str, Any]) -> dict[str, Any]:
    return to_json_safe(
        {
            "schema_version": CANDIDATE_METADATA_SCHEMA_VERSION,
            "artifact_format": "candidate_compilation_boundary_metadata",
            "run_id": manifest["run_id"],
            "package_name": manifest["package_name"],
            "candidates": records,
            "summary": {
                "candidate_count": len(records),
                "callable_generation_supported": manifest.get("callable_generation_supported", False),
                "scientific_metrics_executed": False,
                "qnodes_executed": False,
            },
            "package_manifest": manifest,
        }
    )


def _write_csv(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    columns = sorted({key for record in records for key in record})
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for record in records:
            writer.writerow({key: _csv_safe(record.get(key)) for key in columns})


def _csv_safe(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list, tuple, set)):
        return json.dumps(to_json_safe(value), sort_keys=True)
    return str(to_json_safe(value))


def _parse_csv_value(value: str) -> Any:
    if value == "":
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def _config_without_output(config: CandidateCompilationConfig) -> CandidateCompilationConfig:
    return CandidateCompilationConfig(
        run_id=config.run_id,
        package_name=config.package_name,
        output_root=None,
        generation_index=config.generation_index,
        require_operations=config.require_operations,
        require_parameter_count=config.require_parameter_count,
        require_parent_links=config.require_parent_links,
        normalize_gates=config.normalize_gates,
        allow_metadata_only=config.allow_metadata_only,
        write_csv=config.write_csv,
        write_json=config.write_json,
        write_manifest=config.write_manifest,
        write_callable_module=False,
        callable_module_name=config.callable_module_name,
        callable_backend=config.callable_backend,
        callable_registry_name=config.callable_registry_name,
        allow_unsupported_gates_in_callable_module=config.allow_unsupported_gates_in_callable_module,
        scientific_validity_label=config.scientific_validity_label,
        random_seed=config.random_seed,
    )


def _json_safe(value: Any) -> Any:
    return to_json_safe(value)


def _sha256_json_beta(payload: Any) -> str:
    import hashlib

    encoded = json.dumps(_json_safe(payload), sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _issue(circuit_id: str | None, severity: str, field: str, message: str) -> CandidateValidationIssue:
    return CandidateValidationIssue(
        circuit_id=str(circuit_id) if circuit_id is not None else None,
        severity=severity,
        field=field,
        message=message,
    )


def _dict_or_empty(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _first_present(source: Mapping[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key in source:
            return source[key]
    return None


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


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)


def _mutation_metadata(source: Mapping[str, Any], metadata: Mapping[str, Any]) -> dict[str, Any]:
    keys = ("mutation_type", "mutation_gate", "beta_backend_name", "metadata_operation_beta")
    return {
        key: to_json_safe(_first_non_none(source.get(key), metadata.get(key)))
        for key in keys
        if _first_non_none(source.get(key), metadata.get(key)) is not None
    }


def _unique_strings(values: Sequence[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return tuple(result)


__all__ = [
    "CALLABLE_BACKEND",
    "CANDIDATE_HASH_SCHEMA_VERSION",
    "CANDIDATE_MANIFEST_SCHEMA_VERSION",
    "CANDIDATE_METADATA_SCHEMA_VERSION",
    "CandidateCompilationConfig",
    "CandidateCompilationResult",
    "CandidateValidationIssue",
    "CompiledCandidateRecord",
    "build_callable_module_source",
    "candidate_callable_name",
    "compile_candidate_callable_source",
    "compile_candidate_records",
    "compile_operation_to_source",
    "compute_candidate_lineage_hash",
    "compute_candidate_structural_hash",
    "load_compiled_candidate_records",
    "normalize_candidate_record",
    "normalize_operation_record",
    "sanitize_python_identifier",
    "write_callable_module",
    "write_candidate_staged_package",
]
