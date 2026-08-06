"""Pure structural wire-local mutation primitives."""

from __future__ import annotations

import copy
import hashlib
import json
from typing import Any, Mapping, Sequence

from verfeinert.core.io import to_json_safe


def find_first_operation_on_wire(operations: Sequence[Mapping[str, Any]], wire: int) -> int | None:
    """Return the first operation index touching ``wire``."""
    selected_wire = int(wire)
    for index, operation in enumerate(operations):
        if selected_wire in _operation_wires(operation):
            return index
    return None


def find_last_operation_on_wire(operations: Sequence[Mapping[str, Any]], wire: int) -> int | None:
    """Return the last operation index touching ``wire``."""
    selected_wire = int(wire)
    for index in range(len(operations) - 1, -1, -1):
        if selected_wire in _operation_wires(operations[index]):
            return index
    return None


def remove_first_gate_on_wire(operations: Sequence[Mapping[str, Any]], wire: int) -> dict[str, Any]:
    """Remove the first whole operation touching ``wire``."""
    source = _operation_records(operations)
    target_index = find_first_operation_on_wire(source, int(wire))
    if target_index is None:
        return _result(source, source, None, None, "skipped_noop")
    mutated = [operation for index, operation in enumerate(source) if index != target_index]
    return _result(source, mutated, target_index, None, "valid_mutation")


def move_first_gate_to_end_on_wire(operations: Sequence[Mapping[str, Any]], wire: int) -> dict[str, Any]:
    """Move the first operation touching ``wire`` after related local operations."""
    source = _operation_records(operations)
    target_index = find_first_operation_on_wire(source, int(wire))
    if target_index is None:
        return _result(source, source, None, None, "skipped_noop")
    target = source[target_index]
    target_wires = set(_operation_wires(target))
    remaining = [operation for index, operation in enumerate(source) if index != target_index]
    last_related = None
    for index, operation in enumerate(remaining):
        if target_wires.intersection(_operation_wires(operation)):
            last_related = index
    insert_index = len(remaining) if last_related is None else int(last_related) + 1
    mutated = remaining[:insert_index] + [target] + remaining[insert_index:]
    status = "skipped_noop" if detect_no_op(source, mutated) else "valid_mutation"
    return _result(source, mutated, target_index, insert_index, status)


def swap_first_last_gate_on_wire(operations: Sequence[Mapping[str, Any]], wire: int) -> dict[str, Any]:
    """Swap the first and last operations touching ``wire``."""
    source = _operation_records(operations)
    first = find_first_operation_on_wire(source, int(wire))
    last = find_last_operation_on_wire(source, int(wire))
    if first is None or last is None or first == last:
        return _result(source, source, first, last, "skipped_noop")
    mutated = _operation_records(source)
    mutated[first], mutated[last] = mutated[last], mutated[first]
    status = "skipped_noop" if detect_no_op(source, mutated) else "valid_mutation"
    return _result(source, mutated, first, last, status)


def structural_hash_operations(operations: Sequence[Mapping[str, Any]]) -> str:
    """Return a deterministic hash over normalized operation structure."""
    payload = [
        {
            "gate": str(operation.get("gate", "")).lower(),
            "wires": _operation_wires(operation),
            "parameterized": bool(operation.get("parameterized", False)),
            "params": to_json_safe(operation.get("params") or operation.get("parameters") or []),
        }
        for operation in _renumber_operations(operations)
    ]
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def detect_no_op(
    original_operations: Sequence[Mapping[str, Any]],
    mutated_operations: Sequence[Mapping[str, Any]],
) -> bool:
    """Return true when two operation sequences are structurally identical."""
    return structural_hash_operations(original_operations) == structural_hash_operations(mutated_operations)


def _result(
    original: list[dict[str, Any]],
    mutated: list[dict[str, Any]],
    original_position: int | None,
    new_position: int | None,
    status: str,
) -> dict[str, Any]:
    target = original[original_position] if original_position is not None else None
    return {
        "operations": _renumber_operations(mutated),
        "mutation_status": status,
        "no_op_status": "skipped_noop" if status == "skipped_noop" else "not_noop",
        "mutation_original_position": original_position,
        "mutation_new_position": new_position,
        "mutation_target_gate_index": original_position,
        "mutation_target_gate_name": str(target.get("gate", "")).lower() if target is not None else None,
        "mutation_target_wires": _operation_wires(target) if target is not None else [],
        "mutation_target_n_qubits": len(_operation_wires(target)) if target is not None else 0,
    }


def _operation_records(operations: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return _renumber_operations(copy.deepcopy([dict(operation) for operation in operations]))


def _renumber_operations(operations: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for index, operation in enumerate(operations):
        item = copy.deepcopy(dict(operation))
        item["order"] = index
        metadata = dict(item.get("metadata") or {})
        metadata["order"] = index
        metadata.setdefault("layer_local_order", index)
        item["metadata"] = metadata
        records.append(item)
    return records


def _operation_wires(operation: Mapping[str, Any] | None) -> list[int]:
    if operation is None:
        return []
    raw = operation.get("wires", operation.get("qubits", ()))
    if raw is None:
        return []
    if isinstance(raw, int):
        return [int(raw)]
    return [int(item) for item in list(raw)]


__all__ = [
    "detect_no_op",
    "find_first_operation_on_wire",
    "find_last_operation_on_wire",
    "move_first_gate_to_end_on_wire",
    "remove_first_gate_on_wire",
    "structural_hash_operations",
    "swap_first_last_gate_on_wire",
]
