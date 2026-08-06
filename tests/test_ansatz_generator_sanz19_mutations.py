"""Tests for Sanz19 templates and structural mutation primitives."""

from __future__ import annotations

import copy
import unittest

from verfeinert.ansatz_generator import (
    SANZ19_TEMPLATE_IDS,
    SUPPORTED_SANZ19_LAYERS,
    build_sanz19_candidate_record,
    build_sanz19_candidate_records,
    build_sanz19_operations,
    detect_no_op,
    find_first_operation_on_wire,
    find_last_operation_on_wire,
    move_first_gate_to_end_on_wire,
    normalize_sanz19_template_id,
    remove_first_gate_on_wire,
    structural_hash_operations,
    swap_first_last_gate_on_wire,
)


def _op(gate: str, wires: list[int]) -> dict[str, object]:
    return {
        "gate": gate,
        "wires": wires,
        "parameterized": gate in {"rx", "ry", "rz", "crx", "cry", "crz"},
        "metadata": {"layer_index": 0},
    }


class AnsatzGeneratorSanz19MutationTests(unittest.TestCase):
    def test_sanz19_templates_are_reproducible(self) -> None:
        self.assertEqual(len(SANZ19_TEMPLATE_IDS), 19)
        self.assertEqual(SUPPORTED_SANZ19_LAYERS, (1, 2, 3))
        self.assertEqual(normalize_sanz19_template_id("a02"), "A02")

        records = build_sanz19_candidate_records(SANZ19_TEMPLATE_IDS, SUPPORTED_SANZ19_LAYERS)
        self.assertEqual(len(records), 57)
        self.assertEqual(records[0]["circuit_id"], "SANZ19-A01-L1")
        self.assertEqual(records[-1]["circuit_id"], "SANZ19-A19-L3")

        a02_ops = build_sanz19_operations("A02", n_qubits=4, n_layers=1)
        self.assertEqual(a02_ops[0]["gate"], "rx")
        self.assertEqual(a02_ops[1]["gate"], "rz")
        self.assertEqual(a02_ops[-1]["gate"], "cx")
        self.assertEqual([operation["metadata"]["order"] for operation in a02_ops], list(range(len(a02_ops))))

        candidate = build_sanz19_candidate_record("A02", 1)
        self.assertEqual(candidate["metadata"]["source"], "SANZ19")
        self.assertEqual(candidate["operations"], build_sanz19_candidate_record("A02", 1)["operations"])

    def test_structural_mutations_are_pure_and_deterministic(self) -> None:
        operations = [_op("rx", [0]), _op("cx", [0, 1]), _op("ry", [1]), _op("rz", [2])]
        original = copy.deepcopy(operations)

        self.assertEqual(find_first_operation_on_wire(operations, 1), 1)
        self.assertEqual(find_last_operation_on_wire(operations, 1), 2)

        removed = remove_first_gate_on_wire(operations, 1)
        self.assertEqual(removed["mutation_status"], "valid_mutation")
        self.assertEqual(removed["mutation_target_gate_name"], "cx")
        self.assertEqual(len(removed["operations"]), 3)

        moved = move_first_gate_to_end_on_wire(operations, 1)
        self.assertEqual(moved["mutation_status"], "valid_mutation")
        self.assertEqual(moved["operations"][2]["gate"], "cx")

        swapped = swap_first_last_gate_on_wire(operations, 1)
        self.assertEqual(swapped["operations"][1]["gate"], "ry")
        self.assertEqual(swapped["operations"][2]["gate"], "cx")

        self.assertTrue(detect_no_op([_op("rx", [0])], [_op("rx", [0])]))
        self.assertEqual(structural_hash_operations([_op("rx", [0])]), structural_hash_operations([_op("rx", [0])]))
        self.assertNotEqual(structural_hash_operations([_op("rx", [0])]), structural_hash_operations([_op("ry", [0])]))
        self.assertEqual(operations, original)


if __name__ == "__main__":
    unittest.main()
