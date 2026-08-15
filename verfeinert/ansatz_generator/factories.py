"""Public candidate factories for generic structural mutation workflows."""

from __future__ import annotations

import copy
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from verfeinert import __version__
from verfeinert.core import stable_hash, to_json_safe
from verfeinert.core.validation import CoreValidationError, require_identifier, require_non_empty_text

from .exporters import (
    CANONICAL_CANDIDATE_HASH_SCHEMA_VERSION,
    CANDIDATE_SCHEMA_VERSION,
)
from .exporters.candidate_json import validate_candidate_json
from .operations import DEFAULT_GATE_REGISTRY
from .validation import GeneratorValidationError


INSERTION_STRATEGIES = ("before_first_multiqubit", "append")
EDGE_SELECTION_MODES = ("first", "variant_index_cycle", "parent_index_cycle")


@dataclass(frozen=True)
class InsertGateMutationFactory:
    """Create child Candidate JSON by inserting one configured gate.

    The factory is intentionally small: mutation requests provide the gate,
    qubits/edge, insertion strategy, and optional candidate-id template through
    recipe parameters. This keeps campaign schedules in configuration while
    preserving a normal public ``CandidateFactory`` callable boundary.
    """

    default_gate: str | None = None
    default_qubits: tuple[int, ...] | None = None
    default_edges: tuple[tuple[int, int], ...] = ()
    default_insertion_strategy: str = "before_first_multiqubit"
    default_edge_selection: str = "parent_index_cycle"
    default_candidate_id_template: str = "{root_candidate_id}_g{generation:03d}-{recipe_id}-v{variant_ordinal:03d}"
    source_label: str = "verfeinert.ansatz_generator.insert_gate_mutation_factory"
    created_at: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.default_gate is not None:
            object.__setattr__(self, "default_gate", _gate_name(self.default_gate))
        if self.default_qubits is not None:
            object.__setattr__(self, "default_qubits", _qubits(self.default_qubits, "default_qubits"))
        object.__setattr__(
            self,
            "default_edges",
            tuple(_edge(edge, "default_edges") for edge in self.default_edges),
        )
        if self.default_insertion_strategy not in INSERTION_STRATEGIES:
            raise GeneratorValidationError(
                f"default_insertion_strategy must be one of {INSERTION_STRATEGIES}.",
            )
        if self.default_edge_selection not in EDGE_SELECTION_MODES:
            raise GeneratorValidationError(
                f"default_edge_selection must be one of {EDGE_SELECTION_MODES}.",
            )
        object.__setattr__(self, "source_label", require_non_empty_text(self.source_label, "source_label"))
        object.__setattr__(self, "metadata", to_json_safe(dict(self.metadata)))

    def __call__(self, request: Any, parent_candidate: Mapping[str, Any]) -> dict[str, Any]:
        """Return a validated canonical child Candidate JSON document."""
        parent = validate_candidate_json(parent_candidate)
        parameters = _request_parameters(request)
        metadata = _request_metadata(request)
        gate = _gate_name(parameters.get("gate") or parameters.get("mutation_gate") or self.default_gate)
        qubits = _request_qubits(
            parameters,
            metadata,
            request=request,
            default_qubits=self.default_qubits,
            default_edges=self.default_edges,
            default_edge_selection=self.default_edge_selection,
        )
        insertion_strategy = str(parameters.get("insertion_strategy") or self.default_insertion_strategy)
        if insertion_strategy not in INSERTION_STRATEGIES:
            raise GeneratorValidationError(f"insertion_strategy must be one of {INSERTION_STRATEGIES}.")

        child_id = _child_candidate_id(
            parameters,
            metadata,
            request=request,
            parent=parent,
            gate=gate,
            default_template=self.default_candidate_id_template,
        )
        circuit = _mutated_circuit(
            parent["circuit"],
            gate=gate,
            qubits=qubits,
            parameters=parameters,
            request_metadata=metadata,
            request=request,
            insertion_strategy=insertion_strategy,
        )
        lineage = _child_lineage(child_id=child_id, request=request, parent=parent, gate=gate, parameters=parameters)
        child = {
            "schema_version": CANDIDATE_SCHEMA_VERSION,
            "candidate_id": child_id,
            "identity": {
                "structural_hash": _mutation_structural_hash(
                    circuit,
                    canonicalize_equivalent_insertions=(
                        parameters.get("propagation_policy") == "repeat_mutated_single_layer"
                    ),
                ),
                "lineage_hash": stable_hash(lineage),
                "hash_schema_version": parent["identity"].get(
                    "hash_schema_version",
                    CANONICAL_CANDIDATE_HASH_SCHEMA_VERSION,
                ),
            },
            "circuit": circuit,
            "lineage": lineage,
            "metadata": to_json_safe(
                {
                    **dict(parent.get("metadata", {})),
                    **dict(self.metadata),
                    "generator_source": "verfeinert.ansatz_generator",
                    "mutation_factory": "insert_gate",
                    "mutation_recipe_id": _request_attr(request, "recipe_id"),
                },
            ),
            "provenance": {
                "created_at": self.created_at or _utc_timestamp(),
                "source": {
                    "kind": "mutation",
                    "label": self.source_label,
                },
                "software_version": __version__,
                "git_commit": None,
                "input_hashes": {},
            },
        }
        return validate_candidate_json(child)


def _mutated_circuit(
    parent_circuit: Mapping[str, Any],
    *,
    gate: str,
    qubits: tuple[int, ...],
    parameters: Mapping[str, Any],
    request_metadata: Mapping[str, Any],
    request: Any,
    insertion_strategy: str,
) -> dict[str, Any]:
    circuit = copy.deepcopy(dict(parent_circuit))
    if parameters.get("propagation_policy") == "repeat_mutated_single_layer":
        return _repeat_mutated_single_layer_circuit(
            circuit,
            gate=gate,
            qubits=qubits,
            parameters=parameters,
            request_metadata=request_metadata,
            request=request,
            insertion_strategy=insertion_strategy,
        )
    existing_parameters = [dict(parameter) for parameter in circuit.get("parameters", [])]
    operation_parameters, circuit_parameters = _operation_parameters(
        gate,
        parameters,
        existing_parameters,
    )
    operations = [dict(operation) for operation in circuit["operations"]]
    insert_at = _insertion_index(operations, insertion_strategy, explicit_index=parameters.get("insertion_index"))
    operation = _insert_operation(
        gate=gate,
        qubits=qubits,
        parameters=parameters,
        operation_parameters=operation_parameters,
        request_metadata=request_metadata,
        request=request,
        layer=int(parameters.get("layer", 0)),
    )
    mutated_operations = _renumber_operations(operations[:insert_at] + [operation] + operations[insert_at:])
    if bool(parameters.get("renumber_parameters", True)):
        mutated_operations, circuit_parameters = _renumber_parameter_references(
            mutated_operations,
            circuit_parameters,
        )
    return {
        "n_qubits": int(circuit["n_qubits"]),
        "wire_order": list(circuit.get("wire_order") or range(int(circuit["n_qubits"]))),
        "parameters": circuit_parameters,
        "operations": mutated_operations,
    }


def _mutation_structural_hash(
    circuit: Mapping[str, Any],
    *,
    canonicalize_equivalent_insertions: bool,
) -> str:
    if not canonicalize_equivalent_insertions:
        return stable_hash(
            {
                "n_qubits": circuit["n_qubits"],
                "wire_order": circuit.get("wire_order"),
                "parameters": circuit["parameters"],
                "operations": circuit["operations"],
            },
        )
    return stable_hash(
        {
            "n_qubits": circuit["n_qubits"],
            "wire_order": circuit.get("wire_order"),
            "operations": [_structural_operation_signature(operation) for operation in circuit["operations"]],
        },
    )


def _structural_operation_signature(operation: Mapping[str, Any]) -> dict[str, Any]:
    gate = operation.get("gate")
    if isinstance(gate, Mapping):
        gate_signature = {
            "name": gate.get("name"),
            "namespace": gate.get("namespace"),
        }
    else:
        gate_signature = {"name": gate}
    return {
        "gate": gate_signature,
        "qubits": list(operation.get("qubits", operation.get("wires", ()))),
        "layer": operation.get("layer"),
        "role": operation.get("role"),
        "parameters": [_structural_parameter_signature(parameter) for parameter in operation.get("parameters", ())],
    }


def _structural_parameter_signature(parameter: Mapping[str, Any]) -> dict[str, Any]:
    item = dict(parameter)
    if item.get("kind") == "reference":
        return {"kind": "reference"}
    if item.get("kind") == "literal":
        return {"kind": "literal", "value": to_json_safe(item.get("value"))}
    return to_json_safe(item)


def _repeat_mutated_single_layer_circuit(
    circuit: Mapping[str, Any],
    *,
    gate: str,
    qubits: tuple[int, ...],
    parameters: Mapping[str, Any],
    request_metadata: Mapping[str, Any],
    request: Any,
    insertion_strategy: str,
) -> dict[str, Any]:
    source_parameters = {str(parameter["parameter_id"]): dict(parameter) for parameter in circuit.get("parameters", [])}
    operations = [dict(operation) for operation in circuit["operations"]]
    blocks = _layer_blocks(operations)
    base_layer = blocks.get(0, operations)
    layer_count = max(blocks) + 1 if blocks else int(parameters.get("layer_count", 1))
    insert_at = _insertion_index(base_layer, insertion_strategy, explicit_index=parameters.get("insertion_index"))
    new_parameters: list[dict[str, Any]] = []
    repeated: list[dict[str, Any]] = []
    for layer_index in range(layer_count):
        for local_order, operation in enumerate(base_layer[:insert_at]):
            repeated.append(
                _clone_operation_for_repeat(
                    operation,
                    layer_index=layer_index,
                    layer_local_order=local_order,
                    source_parameters=source_parameters,
                    circuit_parameters=new_parameters,
                ),
            )
        operation_parameters, new_parameters = _operation_parameters(gate, parameters, new_parameters)
        repeated.append(
            _insert_operation(
                gate=gate,
                qubits=qubits,
                parameters=parameters,
                operation_parameters=operation_parameters,
                request_metadata=request_metadata,
                request=request,
                layer=layer_index,
                extra_metadata={
                    "layer_index": layer_index,
                    "layer_local_order": insert_at,
                    "propagation_policy": "repeat_mutated_single_layer",
                    "layer_generation_policy": "mutate_then_repeat_layer",
                    "mutation_applied_to_single_layer_block": True,
                },
            ),
        )
        for local_order, operation in enumerate(base_layer[insert_at:], start=insert_at + 1):
            repeated.append(
                _clone_operation_for_repeat(
                    operation,
                    layer_index=layer_index,
                    layer_local_order=local_order,
                    source_parameters=source_parameters,
                    circuit_parameters=new_parameters,
                ),
            )
    return {
        "n_qubits": int(circuit["n_qubits"]),
        "wire_order": list(circuit.get("wire_order") or range(int(circuit["n_qubits"]))),
        "parameters": new_parameters,
        "operations": _renumber_operations(repeated),
    }


def _insert_operation(
    *,
    gate: str,
    qubits: tuple[int, ...],
    parameters: Mapping[str, Any],
    operation_parameters: Sequence[Mapping[str, Any]],
    request_metadata: Mapping[str, Any],
    request: Any,
    layer: int,
    extra_metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    metadata = _operation_metadata(parameters, request_metadata=request_metadata, request=request, qubits=qubits)
    metadata.update(dict(extra_metadata or {}))
    return {
        "operation_id": "op-000",
        "gate": {
            "name": gate,
            "namespace": str(parameters.get("gate_namespace") or "verfeinert.default_gates"),
        },
        "qubits": list(qubits),
        "parameters": [dict(parameter) for parameter in operation_parameters],
        "layer": layer,
        "order": 0,
        "role": _operation_role(gate, qubits),
        "metadata": metadata,
    }


def _operation_parameters(
    gate: str,
    parameters: Mapping[str, Any],
    circuit_parameters: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    explicit = parameters.get("parameters", parameters.get("params"))
    if explicit is not None:
        values = explicit if isinstance(explicit, Sequence) and not isinstance(explicit, (str, bytes)) else (explicit,)
        return [_parameter_value(value) for value in values], circuit_parameters

    gate_def = DEFAULT_GATE_REGISTRY.get(gate)
    parameterized = parameters.get("parameterized")
    if parameterized is None:
        parameterized = gate_def.n_params > 0
    if not bool(parameterized):
        return [], circuit_parameters
    parameter_count = int(parameters.get("parameter_count", gate_def.n_params or 1))
    refs: list[dict[str, Any]] = []
    used_ids = {str(parameter["parameter_id"]) for parameter in circuit_parameters}
    for _ in range(parameter_count):
        parameter_id = _next_parameter_id(used_ids)
        used_ids.add(parameter_id)
        circuit_parameters.append(
            {
                "parameter_id": parameter_id,
                "kind": "trainable",
                "symbol": parameter_id.replace("-", "_"),
            },
        )
        refs.append({"kind": "reference", "parameter_id": parameter_id})
    return refs, circuit_parameters


def _parameter_value(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        kind = value.get("kind")
        if kind == "reference" and value.get("parameter_id") is not None:
            return {
                "kind": "reference",
                "parameter_id": require_identifier(str(value["parameter_id"]), "parameter_id"),
            }
        if kind == "literal" and "value" in value:
            return {"kind": "literal", "value": to_json_safe(value["value"])}
        raise GeneratorValidationError("operation parameter mappings must be reference or literal records.")
    if isinstance(value, str):
        return {"kind": "reference", "parameter_id": require_identifier(value, "parameter_id")}
    return {"kind": "literal", "value": to_json_safe(value)}


def _next_parameter_id(used_ids: set[str]) -> str:
    index = 0
    while True:
        parameter_id = f"theta-{index:03d}"
        if parameter_id not in used_ids:
            return parameter_id
        index += 1


def _insertion_index(
    operations: Sequence[Mapping[str, Any]],
    insertion_strategy: str,
    *,
    explicit_index: object = None,
) -> int:
    if explicit_index is not None:
        index = int(explicit_index)
        if index < 0 or index > len(operations):
            raise GeneratorValidationError("insertion_index must be between 0 and the operation count.")
        return index
    if insertion_strategy == "append":
        return len(operations)
    for index, operation in enumerate(operations):
        if len(operation.get("qubits", operation.get("wires", ()))) > 1:
            return index
    return len(operations)


def _layer_blocks(operations: Sequence[Mapping[str, Any]]) -> dict[int, list[dict[str, Any]]]:
    blocks: dict[int, list[dict[str, Any]]] = {}
    for operation in operations:
        metadata = dict(operation.get("metadata", {}))
        raw_layer = metadata.get("layer_index", operation.get("layer"))
        if raw_layer is None:
            return {}
        try:
            layer = int(raw_layer)
        except (TypeError, ValueError):
            return {}
        blocks.setdefault(layer, []).append(copy.deepcopy(dict(operation)))
    for layer, items in blocks.items():
        blocks[layer] = sorted(items, key=lambda item: int(item.get("order", 0)))
    return blocks


def _clone_operation_for_repeat(
    operation: Mapping[str, Any],
    *,
    layer_index: int,
    layer_local_order: int,
    source_parameters: Mapping[str, Mapping[str, Any]],
    circuit_parameters: list[dict[str, Any]],
) -> dict[str, Any]:
    item = copy.deepcopy(dict(operation))
    refs: list[dict[str, Any]] = []
    used_ids = {str(parameter["parameter_id"]) for parameter in circuit_parameters}
    for parameter in item.get("parameters", []):
        parameter_record = dict(parameter)
        if parameter_record.get("kind") != "reference":
            refs.append(parameter_record)
            continue
        old_id = str(parameter_record["parameter_id"])
        new_id = _next_parameter_id(used_ids)
        used_ids.add(new_id)
        old = dict(source_parameters.get(old_id, {}))
        kind = str(old.get("kind", "trainable"))
        new_parameter = {
            "parameter_id": new_id,
            "kind": kind,
            "symbol": new_id.replace("-", "_") if kind == "trainable" else str(old.get("symbol") or new_id),
        }
        if "value" in old:
            new_parameter["value"] = old["value"]
        if "metadata" in old:
            new_parameter["metadata"] = old["metadata"]
        circuit_parameters.append(to_json_safe(new_parameter))
        refs.append({"kind": "reference", "parameter_id": new_id})
    item["parameters"] = refs
    item["layer"] = layer_index
    metadata = dict(item.get("metadata", {}))
    metadata["layer_index"] = layer_index
    metadata["layer_local_order"] = layer_local_order
    item["metadata"] = metadata
    return item


def _renumber_operations(operations: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for order, operation in enumerate(operations):
        item = copy.deepcopy(dict(operation))
        item["operation_id"] = f"op-{order:03d}"
        item["order"] = order
        item.setdefault("layer", 0)
        item.setdefault("role", _operation_role(str(item["gate"]["name"]), tuple(item["qubits"])))
        metadata = dict(item.get("metadata", {}))
        metadata["order"] = order
        metadata["source_order"] = order
        item["metadata"] = to_json_safe(metadata)
        records.append(item)
    return records


def _renumber_parameter_references(
    operations: Sequence[Mapping[str, Any]],
    parameters: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    old_parameters = {str(parameter["parameter_id"]): dict(parameter) for parameter in parameters}
    id_map: dict[str, str] = {}
    new_parameters: list[dict[str, Any]] = []
    records: list[dict[str, Any]] = []
    for operation in operations:
        item = copy.deepcopy(dict(operation))
        refs: list[dict[str, Any]] = []
        for parameter in item.get("parameters", []):
            parameter_record = dict(parameter)
            if parameter_record.get("kind") != "reference":
                refs.append(parameter_record)
                continue
            old_id = str(parameter_record["parameter_id"])
            if old_id not in id_map:
                new_id = f"theta-{len(id_map):03d}"
                id_map[old_id] = new_id
                old = old_parameters.get(old_id, {})
                kind = old.get("kind", "trainable")
                new_parameter = {
                    "parameter_id": new_id,
                    "kind": kind,
                    "symbol": new_id.replace("-", "_") if kind == "trainable" else str(old.get("symbol") or new_id),
                }
                if "value" in old:
                    new_parameter["value"] = old["value"]
                if "metadata" in old:
                    new_parameter["metadata"] = old["metadata"]
                new_parameters.append(to_json_safe(new_parameter))
            refs.append({"kind": "reference", "parameter_id": id_map[old_id]})
        item["parameters"] = refs
        records.append(item)
    return records, new_parameters


def _operation_metadata(
    parameters: Mapping[str, Any],
    *,
    request_metadata: Mapping[str, Any],
    request: Any,
    qubits: tuple[int, ...],
) -> dict[str, Any]:
    payload = dict(parameters.get("operation_metadata", {})) if isinstance(parameters.get("operation_metadata"), Mapping) else {}
    payload.setdefault("edge", list(qubits))
    payload.setdefault("mutation_code", parameters.get("mutation_code") or _request_attr(request, "recipe_id"))
    payload.setdefault("source", parameters.get("source_label") or "verfeinert.generic_insert_gate")
    if parameters.get("insertion_index") is not None:
        payload.setdefault("insertion_index", int(parameters["insertion_index"]))
    if parameters.get("propagation_policy") is not None:
        payload.setdefault("propagation_policy", str(parameters["propagation_policy"]))
    payload.setdefault(
        "variant_index",
        int(request_metadata.get("parent_index", int(_request_attr(request, "variant_index")))) + 1,
    )
    return to_json_safe(payload)


def _child_lineage(
    *,
    child_id: str,
    request: Any,
    parent: Mapping[str, Any],
    gate: str,
    parameters: Mapping[str, Any],
) -> dict[str, Any]:
    parent_lineage = dict(parent["lineage"])
    root_candidate_id = str(
        _request_attr(request, "root_candidate_id")
        or parent_lineage.get("root_candidate_id")
        or parent["candidate_id"],
    )
    mutation_id = _identifier_token(
        str(parameters.get("mutation_id") or _request_attr(request, "request_id") or f"{child_id}-mutation"),
    )
    return {
        "generation": int(_request_attr(request, "generation_index")),
        "root_candidate_id": require_identifier(root_candidate_id, "root_candidate_id"),
        "parent_candidate_id": require_identifier(str(_request_attr(request, "parent_candidate_id")), "parent_candidate_id"),
        "mutation": {
            "mutation_id": require_identifier(mutation_id, "mutation_id"),
            "type": require_identifier(str(_request_attr(request, "mutation_type")), "mutation_type"),
            "source_candidate_id": require_identifier(str(_request_attr(request, "parent_candidate_id")), "source_candidate_id"),
            "operation": gate,
            "parameters": to_json_safe(dict(parameters)),
            "metadata": {
                "policy_id": _request_attr(request, "policy_id"),
                "recipe_id": _request_attr(request, "recipe_id"),
                "variant_index": _request_attr(request, "variant_index"),
            },
        },
    }


def _child_candidate_id(
    parameters: Mapping[str, Any],
    metadata: Mapping[str, Any],
    *,
    request: Any,
    parent: Mapping[str, Any],
    gate: str,
    default_template: str,
) -> str:
    parent_lineage = dict(parent["lineage"])
    root_candidate_id = str(
        _request_attr(request, "root_candidate_id")
        or parent_lineage.get("root_candidate_id")
        or parent["candidate_id"],
    )
    variant_index = int(_request_attr(request, "variant_index"))
    parent_index = int(metadata.get("parent_index", 0))
    fields = {
        "parent_candidate_id": str(_request_attr(request, "parent_candidate_id")),
        "root_candidate_id": root_candidate_id,
        "generation": int(_request_attr(request, "generation_index")),
        "generation_index": int(_request_attr(request, "generation_index")),
        "recipe_id": str(_request_attr(request, "recipe_id")),
        "mutation_type": str(_request_attr(request, "mutation_type")),
        "gate": gate,
        "variant_index": variant_index,
        "variant_ordinal": variant_index + 1,
        "parent_index": parent_index,
        "parent_ordinal": parent_index + 1,
    }
    template = str(parameters.get("candidate_id_template") or default_template)
    try:
        candidate_id = template.format(**fields)
    except (KeyError, ValueError) as exc:
        raise GeneratorValidationError(f"invalid candidate_id_template: {template}") from exc
    return _identifier(candidate_id, "candidate_id")


def _request_qubits(
    parameters: Mapping[str, Any],
    metadata: Mapping[str, Any],
    *,
    request: Any,
    default_qubits: tuple[int, ...] | None,
    default_edges: tuple[tuple[int, int], ...],
    default_edge_selection: str,
) -> tuple[int, ...]:
    if parameters.get("qubits") is not None:
        return _qubits(parameters["qubits"], "qubits")
    if parameters.get("edge") is not None:
        return _edge(parameters["edge"], "edge")
    edges = parameters.get("edges", default_edges)
    if edges:
        edge_records = tuple(_edge(edge, "edges") for edge in edges)
        selection = str(parameters.get("edge_selection") or default_edge_selection)
        if selection not in EDGE_SELECTION_MODES:
            raise GeneratorValidationError(f"edge_selection must be one of {EDGE_SELECTION_MODES}.")
        if selection == "variant_index_cycle":
            index = int(_request_attr(request, "variant_index"))
        elif selection == "parent_index_cycle":
            index = int(metadata.get("parent_index", 0))
        else:
            index = 0
        return edge_records[index % len(edge_records)]
    if default_qubits is None:
        raise GeneratorValidationError("insert-gate mutation requires qubits, edge, or edges.")
    return default_qubits


def _request_parameters(request: Any) -> dict[str, Any]:
    return dict(_request_attr(request, "parameters") or {})


def _request_metadata(request: Any) -> dict[str, Any]:
    return dict(_request_attr(request, "metadata") or {})


def _request_attr(request: Any, name: str) -> Any:
    if isinstance(request, Mapping):
        return request.get(name)
    return getattr(request, name)


def _gate_name(value: object) -> str:
    if value is None:
        raise GeneratorValidationError("insert-gate mutation requires a gate.")
    gate = str(value).strip().lower()
    DEFAULT_GATE_REGISTRY.get(gate)
    return gate


def _qubits(value: object, field_name: str) -> tuple[int, ...]:
    if isinstance(value, int):
        qubits = (value,)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        qubits = tuple(int(item) for item in value)
    else:
        raise GeneratorValidationError(f"{field_name} must be an integer or sequence of integers.")
    if not qubits or any(qubit < 0 for qubit in qubits) or len(set(qubits)) != len(qubits):
        raise GeneratorValidationError(f"{field_name} must contain unique non-negative qubits.")
    return qubits


def _edge(value: object, field_name: str) -> tuple[int, int]:
    qubits = _qubits(value, field_name)
    if len(qubits) != 2:
        raise GeneratorValidationError(f"{field_name} must contain exactly two qubits.")
    return (qubits[0], qubits[1])


def _operation_role(gate: str, qubits: Sequence[int]) -> str:
    if gate in {"rx", "ry", "rz"}:
        return "rotation"
    if gate in {"crx", "cry", "crz"}:
        return "controlled_rotation"
    if gate == "h":
        return "basis_change"
    if len(tuple(qubits)) == 2:
        return "entangler"
    return "other"


def _identifier(value: str, field_name: str) -> str:
    try:
        return require_identifier(value, field_name)
    except CoreValidationError as exc:
        raise GeneratorValidationError(str(exc)) from exc


def _identifier_token(value: str) -> str:
    token = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(value).strip()).strip("-_.")
    return token or "identifier"


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


__all__ = ["EDGE_SELECTION_MODES", "INSERTION_STRATEGIES", "InsertGateMutationFactory"]
