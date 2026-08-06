"""Tests for generator connectivity, constraints, lineage, and candidates."""

from __future__ import annotations

import unittest

from verfeinert.ansatz_generator import (
    CandidateRecord,
    Connectivity,
    ConstraintSet,
    LineageRecord,
)
from verfeinert.ansatz_generator.validation import GeneratorValidationError


class AnsatzGeneratorConstraintTests(unittest.TestCase):
    def test_connectivity_validates_directed_and_undirected_edges(self) -> None:
        undirected = Connectivity(n_qubits=3, edges=((0, 1),), directed=False)
        self.assertTrue(undirected.allows(1, 0))
        self.assertFalse(undirected.allows(1, 2))

        directed = Connectivity(n_qubits=3, edges=((0, 1),), directed=True)
        self.assertTrue(directed.allows(0, 1))
        self.assertFalse(directed.allows(1, 0))

        with self.assertRaises(GeneratorValidationError):
            Connectivity(n_qubits=2, edges=((0, 2),))
        with self.assertRaises(GeneratorValidationError):
            Connectivity(n_qubits=2, edges=((0, 0),))

    def test_constraints_normalize_gates_and_query_edges(self) -> None:
        constraints = ConstraintSet(
            allowed_gates=("RX", "CX"),
            allowed_inserted_gates=("CZ",),
            connectivity=Connectivity(n_qubits=2, edges=((0, 1),)),
        )

        self.assertTrue(constraints.is_gate_allowed("rx"))
        self.assertFalse(constraints.is_gate_allowed("rz"))
        self.assertTrue(constraints.is_inserted_gate_allowed("cz"))
        self.assertTrue(constraints.is_edge_allowed(1, 0))

    def test_lineage_and_candidate_records_validate_identity(self) -> None:
        lineage = LineageRecord(
            circuit_id="SANZ19-A02-L1_G01-V001",
            parent_circuit_id="SANZ19-A02-L1",
            root_circuit_id="SANZ19-A02-L1",
            generation_index=1,
            variant_index=1,
        )
        candidate = CandidateRecord(
            circuit_id=lineage.circuit_id,
            lineage=lineage,
            layer=1,
            operations=({"gate": "rx", "wires": [0]}, {"gate": "cx", "wires": [0, 1]}),
            parameter_count=1,
        )

        self.assertEqual(candidate.operation_count, 2)
        self.assertEqual(candidate.two_qubit_operation_count, 1)
        self.assertEqual(candidate.to_dict()["lineage"]["parent_circuit_id"], "SANZ19-A02-L1")

        with self.assertRaises(GeneratorValidationError):
            LineageRecord(circuit_id="bad id with spaces")
        with self.assertRaises(GeneratorValidationError):
            CandidateRecord(circuit_id="c1", operations=(), layer=-1)


if __name__ == "__main__":
    unittest.main()
