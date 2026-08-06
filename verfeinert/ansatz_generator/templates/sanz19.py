"""Pure Sanz19 reference-template builders for metadata candidates."""

from __future__ import annotations

from typing import Any, Iterable, Sequence

from verfeinert.ansatz_generator.operations import PARAMETERIZED_GATES


SANZ19_TEMPLATE_IDS = tuple(f"A{i:02d}" for i in range(1, 20))
SUPPORTED_SANZ19_LAYERS = (1, 2, 3)


def build_sanz19_operations(
    template_id: str,
    *,
    n_qubits: int = 4,
    n_layers: int = 1,
) -> list[dict[str, Any]]:
    """Return deterministic Sanz19 operations as metadata dictionaries."""
    normalized_template = normalize_sanz19_template_id(template_id)
    if normalized_template != "A01":
        _require_min_qubits(n_qubits, 2, normalized_template)
    if n_layers < 1:
        raise ValueError("n_layers must be >= 1")

    operations: list[dict[str, Any]] = []
    for layer_index in range(n_layers):
        if normalized_template == "A01":
            _append_rotation_block(operations, layer_index=layer_index, template_id=normalized_template, pattern="RXRZ", wires=range(n_qubits), block_id="rotation_layer")
        elif normalized_template == "A02":
            _rxrz_then_pairs(operations, layer_index=layer_index, template_id=normalized_template, n_qubits=n_qubits, pairs=_pairs_chain(n_qubits), gate="cx", block_id="entangler_layer")
        elif normalized_template == "A03":
            _rxrz_then_pairs(operations, layer_index=layer_index, template_id=normalized_template, n_qubits=n_qubits, pairs=_pairs_chain(n_qubits), gate="crz", block_id="controlled_rotation_layer")
        elif normalized_template == "A04":
            _rxrz_then_pairs(operations, layer_index=layer_index, template_id=normalized_template, n_qubits=n_qubits, pairs=_pairs_chain(n_qubits), gate="crx", block_id="controlled_rotation_layer")
        elif normalized_template == "A05":
            _rxrz_pairs_rxrz(operations, layer_index=layer_index, template_id=normalized_template, n_qubits=n_qubits, pairs=_pairs_all_to_all(n_qubits), gate="crz")
        elif normalized_template == "A06":
            _rxrz_pairs_rxrz(operations, layer_index=layer_index, template_id=normalized_template, n_qubits=n_qubits, pairs=_pairs_all_to_all(n_qubits), gate="crx")
        elif normalized_template == "A07":
            _rxrz_brick_rxrz_brick(operations, layer_index=layer_index, template_id=normalized_template, n_qubits=n_qubits, gate="crz")
        elif normalized_template == "A08":
            _rxrz_brick_rxrz_brick(operations, layer_index=layer_index, template_id=normalized_template, n_qubits=n_qubits, gate="crx")
        elif normalized_template == "A09":
            if layer_index == 0:
                _append_static_block(operations, layer_index=0, template_id=normalized_template, gate="h", wires=((wire,) for wire in range(n_qubits)), block_id="basis_change", role="basis_change")
            _append_pair_block(operations, layer_index=layer_index, template_id=normalized_template, pairs=_pairs_chain(n_qubits), gate="cz", block_id="entangler_layer")
            _append_rotation_block(operations, layer_index=layer_index, template_id=normalized_template, pattern="RX", wires=range(n_qubits), block_id="rotation_layer")
        elif normalized_template == "A10":
            _append_rotation_block(operations, layer_index=layer_index, template_id=normalized_template, pattern="RY", wires=range(n_qubits), block_id="rotation_layer_pre")
            _append_pair_block(operations, layer_index=layer_index, template_id=normalized_template, pairs=[*_pairs_chain(n_qubits), (n_qubits - 1, 0)], gate="cz", block_id="entangler_layer")
            _append_rotation_block(operations, layer_index=layer_index, template_id=normalized_template, pattern="RY", wires=range(n_qubits), block_id="rotation_layer_post")
        elif normalized_template == "A11":
            _ryrz_brick_middle_brick(operations, layer_index=layer_index, template_id=normalized_template, n_qubits=n_qubits, gate="cx")
        elif normalized_template == "A12":
            _ryrz_brick_middle_brick(operations, layer_index=layer_index, template_id=normalized_template, n_qubits=n_qubits, gate="cz")
        elif normalized_template == "A13":
            _ry_ring_ry_inverse(operations, layer_index=layer_index, template_id=normalized_template, n_qubits=n_qubits, gate="crz")
        elif normalized_template == "A14":
            _ry_ring_ry_inverse(operations, layer_index=layer_index, template_id=normalized_template, n_qubits=n_qubits, gate="crx")
        elif normalized_template == "A15":
            _ry_ring_ry_inverse(operations, layer_index=layer_index, template_id=normalized_template, n_qubits=n_qubits, gate="cx")
        elif normalized_template == "A16":
            _rxrz_then_two_bricks(operations, layer_index=layer_index, template_id=normalized_template, n_qubits=n_qubits, gate="crz")
        elif normalized_template == "A17":
            _rxrz_then_two_bricks(operations, layer_index=layer_index, template_id=normalized_template, n_qubits=n_qubits, gate="crx")
        elif normalized_template == "A18":
            _rxrz_then_pairs(operations, layer_index=layer_index, template_id=normalized_template, n_qubits=n_qubits, pairs=_pairs_ring(n_qubits), gate="crz", block_id="controlled_rotation_layer")
        elif normalized_template == "A19":
            _rxrz_then_pairs(operations, layer_index=layer_index, template_id=normalized_template, n_qubits=n_qubits, pairs=_pairs_ring(n_qubits), gate="crx", block_id="controlled_rotation_layer")
        else:
            raise KeyError(f"Unknown Sanz19 template_id: {template_id!r}")
    return _renumber_operations(operations)


def build_sanz19_candidate_record(
    template_id: str,
    layer: int,
    *,
    n_qubits: int = 4,
) -> dict[str, Any]:
    """Return one base Sanz19 parent candidate record."""
    normalized_template = normalize_sanz19_template_id(template_id)
    normalized_layer = int(layer)
    if normalized_layer not in SUPPORTED_SANZ19_LAYERS:
        raise ValueError(f"layer must be one of {SUPPORTED_SANZ19_LAYERS}")
    circuit_id = f"SANZ19-{normalized_template}-L{normalized_layer}"
    operations = build_sanz19_operations(
        normalized_template,
        n_qubits=n_qubits,
        n_layers=normalized_layer,
    )
    return {
        "circuit_id": circuit_id,
        "generation_index": 0,
        "parent_circuit_id": None,
        "root_circuit_id": circuit_id,
        "layer": normalized_layer,
        "L": f"L{normalized_layer}",
        "ansatz_id": normalized_template,
        "template_id": normalized_template,
        "recipe_id": f"{normalized_template}_BASE_L{normalized_layer}",
        "mutation_type": "base_sanz_parent",
        "mutation_gate": None,
        "candidate_status": "generation_0_parent_pool",
        "source_backend_name": "sanz19_clean_metadata_builder",
        "operations": operations,
        "metadata": {
            "source": "SANZ19",
            "template_id": normalized_template,
            "ansatz_id": normalized_template,
            "layer": normalized_layer,
            "L": f"L{normalized_layer}",
            "candidate_status": "generation_0_parent_pool",
            "generation_0_parent_pool": True,
            "mutation_source": "base_sanz_template",
        },
    }


def build_sanz19_candidate_records(
    template_ids: Sequence[str],
    layers: Sequence[int],
    *,
    n_qubits: int = 4,
) -> list[dict[str, Any]]:
    """Return deterministic base Sanz19 records for template/layer pairs."""
    return [
        build_sanz19_candidate_record(template_id, int(layer), n_qubits=n_qubits)
        for template_id in template_ids
        for layer in layers
    ]


def normalize_sanz19_template_id(template_id: str) -> str:
    """Return canonical ``Axx`` Sanz19 template identifier."""
    if not isinstance(template_id, str):
        raise TypeError(f"template_id must be str, got {type(template_id)}")
    normalized = template_id.strip().upper()
    if normalized not in SANZ19_TEMPLATE_IDS:
        raise KeyError(f"Unknown Sanz19 template_id: {template_id!r}")
    return normalized


def _rxrz_then_pairs(
    operations: list[dict[str, Any]],
    *,
    layer_index: int,
    template_id: str,
    n_qubits: int,
    pairs: Iterable[tuple[int, int]],
    gate: str,
    block_id: str,
) -> None:
    _append_rotation_block(operations, layer_index=layer_index, template_id=template_id, pattern="RXRZ", wires=range(n_qubits), block_id="rotation_layer")
    _append_pair_block(operations, layer_index=layer_index, template_id=template_id, pairs=pairs, gate=gate, block_id=block_id)


def _rxrz_pairs_rxrz(
    operations: list[dict[str, Any]],
    *,
    layer_index: int,
    template_id: str,
    n_qubits: int,
    pairs: Iterable[tuple[int, int]],
    gate: str,
) -> None:
    _append_rotation_block(operations, layer_index=layer_index, template_id=template_id, pattern="RXRZ", wires=range(n_qubits), block_id="rotation_layer_pre")
    _append_pair_block(operations, layer_index=layer_index, template_id=template_id, pairs=pairs, gate=gate, block_id="controlled_rotation_layer")
    _append_rotation_block(operations, layer_index=layer_index, template_id=template_id, pattern="RXRZ", wires=range(n_qubits), block_id="rotation_layer_post")


def _rxrz_brick_rxrz_brick(
    operations: list[dict[str, Any]],
    *,
    layer_index: int,
    template_id: str,
    n_qubits: int,
    gate: str,
) -> None:
    _append_rotation_block(operations, layer_index=layer_index, template_id=template_id, pattern="RXRZ", wires=range(n_qubits), block_id="rotation_layer_pre")
    _append_pair_block(operations, layer_index=layer_index, template_id=template_id, pairs=_pairs_brick(n_qubits, 1), gate=gate, block_id="brick_controlled_rotation_layer_odd")
    _append_rotation_block(operations, layer_index=layer_index, template_id=template_id, pattern="RXRZ", wires=range(n_qubits), block_id="rotation_layer_post")
    _append_pair_block(operations, layer_index=layer_index, template_id=template_id, pairs=_pairs_brick(n_qubits, 2), gate=gate, block_id="brick_controlled_rotation_layer_even")


def _ryrz_brick_middle_brick(
    operations: list[dict[str, Any]],
    *,
    layer_index: int,
    template_id: str,
    n_qubits: int,
    gate: str,
) -> None:
    _append_rotation_block(operations, layer_index=layer_index, template_id=template_id, pattern="RYRZ", wires=range(n_qubits), block_id="rotation_layer")
    _append_pair_block(operations, layer_index=layer_index, template_id=template_id, pairs=_pairs_brick(n_qubits, 1), gate=gate, block_id="brick_entangler_layer_odd")
    _append_rotation_block(operations, layer_index=layer_index, template_id=template_id, pattern="RYRZ", wires=range(1, n_qubits - 1), block_id="middle_rotation_layer")
    _append_pair_block(operations, layer_index=layer_index, template_id=template_id, pairs=_pairs_brick(n_qubits, 2), gate=gate, block_id="brick_entangler_layer_even")


def _ry_ring_ry_inverse(
    operations: list[dict[str, Any]],
    *,
    layer_index: int,
    template_id: str,
    n_qubits: int,
    gate: str,
) -> None:
    _append_rotation_block(operations, layer_index=layer_index, template_id=template_id, pattern="RY", wires=range(n_qubits), block_id="rotation_layer_pre")
    _append_pair_block(operations, layer_index=layer_index, template_id=template_id, pairs=_pairs_ring(n_qubits), gate=gate, block_id="ring_controlled_layer")
    _append_rotation_block(operations, layer_index=layer_index, template_id=template_id, pattern="RY", wires=range(n_qubits), block_id="rotation_layer_post")
    _append_pair_block(operations, layer_index=layer_index, template_id=template_id, pairs=_pairs_ring_inverse(n_qubits), gate=gate, block_id="ring_inverse_controlled_layer")


def _rxrz_then_two_bricks(
    operations: list[dict[str, Any]],
    *,
    layer_index: int,
    template_id: str,
    n_qubits: int,
    gate: str,
) -> None:
    _append_rotation_block(operations, layer_index=layer_index, template_id=template_id, pattern="RXRZ", wires=range(n_qubits), block_id="rotation_layer")
    _append_pair_block(operations, layer_index=layer_index, template_id=template_id, pairs=_pairs_brick(n_qubits, 1), gate=gate, block_id="brick_controlled_rotation_layer_odd")
    _append_pair_block(operations, layer_index=layer_index, template_id=template_id, pairs=_pairs_brick(n_qubits, 2), gate=gate, block_id="brick_controlled_rotation_layer_even")


def _append_rotation_block(
    operations: list[dict[str, Any]],
    *,
    layer_index: int,
    template_id: str,
    pattern: str,
    wires: Iterable[int],
    block_id: str,
) -> None:
    for wire in wires:
        if pattern == "RXRZ":
            _append_operation(operations, gate="rx", wires=(wire,), template_id=template_id, layer_index=layer_index, block_id=block_id, role="rotation")
            _append_operation(operations, gate="rz", wires=(wire,), template_id=template_id, layer_index=layer_index, block_id=block_id, role="rotation")
        elif pattern == "RY":
            _append_operation(operations, gate="ry", wires=(wire,), template_id=template_id, layer_index=layer_index, block_id=block_id, role="rotation")
        elif pattern == "RYRZ":
            _append_operation(operations, gate="ry", wires=(wire,), template_id=template_id, layer_index=layer_index, block_id=block_id, role="rotation")
            _append_operation(operations, gate="rz", wires=(wire,), template_id=template_id, layer_index=layer_index, block_id=block_id, role="rotation")
        elif pattern == "RX":
            _append_operation(operations, gate="rx", wires=(wire,), template_id=template_id, layer_index=layer_index, block_id=block_id, role="rotation")
        else:
            raise ValueError(f"Unsupported rotation pattern: {pattern!r}")


def _append_static_block(
    operations: list[dict[str, Any]],
    *,
    layer_index: int,
    template_id: str,
    gate: str,
    wires: Iterable[Sequence[int]],
    block_id: str,
    role: str,
) -> None:
    for item in wires:
        _append_operation(operations, gate=gate, wires=item, template_id=template_id, layer_index=layer_index, block_id=block_id, role=role)


def _append_pair_block(
    operations: list[dict[str, Any]],
    *,
    layer_index: int,
    template_id: str,
    pairs: Iterable[tuple[int, int]],
    gate: str,
    block_id: str,
) -> None:
    role = "controlled_rotation" if gate in {"crx", "cry", "crz"} else "entangler"
    for control, target in pairs:
        _append_operation(operations, gate=gate, wires=(control, target), template_id=template_id, layer_index=layer_index, block_id=block_id, role=role)


def _append_operation(
    operations: list[dict[str, Any]],
    *,
    gate: str,
    wires: Sequence[int],
    template_id: str,
    layer_index: int,
    block_id: str,
    role: str,
) -> None:
    order = len(operations)
    operations.append(
        {
            "gate": gate,
            "wires": [int(wire) for wire in wires],
            "parameterized": gate in PARAMETERIZED_GATES,
            "params": None,
            "metadata": {
                "source": "SANZ19",
                "template_id": template_id,
                "layer_index": int(layer_index),
                "order": int(order),
                "block_id": block_id,
                "role": role,
            },
        }
    )


def _renumber_operations(operations: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for order, operation in enumerate(operations):
        item = dict(operation)
        metadata = dict(item.get("metadata") or {})
        metadata["order"] = int(order)
        item["metadata"] = metadata
        result.append(item)
    return result


def _pairs_chain(n_qubits: int) -> list[tuple[int, int]]:
    return [(n_qubits - index, n_qubits - index - 1) for index in range(1, n_qubits)]


def _pairs_brick(n_qubits: int, offset: int) -> list[tuple[int, int]]:
    if offset not in (1, 2):
        raise ValueError(f"brick offset must be 1 or 2, got {offset}")
    return [(wire, wire - 1) for wire in range(offset, n_qubits, 2)]


def _pairs_all_to_all(n_qubits: int) -> list[tuple[int, int]]:
    return [
        (control, target)
        for control in range(n_qubits - 1, -1, -1)
        for target in range(n_qubits - 1, -1, -1)
        if control != target
    ]


def _pairs_ring(n_qubits: int) -> list[tuple[int, int]]:
    return [(wire, (wire + 1) % n_qubits) for wire in range(n_qubits - 1, -1, -1)]


def _pairs_ring_inverse(n_qubits: int) -> list[tuple[int, int]]:
    order = [n_qubits - 1] + list(range(n_qubits - 1))
    return [(wire % n_qubits, (wire - 1) % n_qubits) for wire in order]


def _require_min_qubits(n_qubits: int, minimum: int, template_id: str) -> None:
    if n_qubits < minimum:
        raise ValueError(f"Sanz19 template {template_id} requires at least {minimum} qubits")


__all__ = [
    "SANZ19_TEMPLATE_IDS",
    "SUPPORTED_SANZ19_LAYERS",
    "build_sanz19_candidate_record",
    "build_sanz19_candidate_records",
    "build_sanz19_operations",
    "normalize_sanz19_template_id",
]
