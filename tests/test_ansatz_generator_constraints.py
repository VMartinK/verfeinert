"""Tests for generator connectivity, constraints, lineage, and candidates."""

from __future__ import annotations

import unittest

from verfeinert.ansatz_generator import (
    CandidateJsonExportConfig,
    CandidateRecord,
    Connectivity,
    ConstraintSet,
    InsertGateMutationFactory,
    LineageRecord,
    build_sanz19_candidate_record,
    export_candidate_json,
    validate_candidate_constraints,
)
from verfeinert.ansatz_generator.validation import GeneratorValidationError


CREATED_AT = "2026-08-06T00:00:00Z"


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

    def test_constraints_roundtrip_and_validate_candidate_gates_and_connectivity(self) -> None:
        constraints = ConstraintSet.from_mapping(
            {
                "allowed_gates": ["rz", "rx", "cx"],
                "allowed_inserted_gates": ["cz"],
                "connectivity": {"n_qubits": 4, "topology": "linear"},
            },
        )
        self.assertEqual(
            ConstraintSet.from_mapping(constraints.to_dict()).to_dict(),
            constraints.to_dict(),
        )

        source = build_sanz19_candidate_record("A02", 1, n_qubits=4)
        candidate = export_candidate_json(
            source,
            config=CandidateJsonExportConfig(
                candidate_id_prefix="constraint",
                n_qubits=4,
                created_at=CREATED_AT,
                source_label="constraint-test",
                git_commit=None,
                discover_git_commit=False,
                constraints=constraints,
            ),
        )
        self.assertEqual(validate_candidate_constraints(candidate, constraints), candidate)

        disallowed_gate = ConstraintSet(
            allowed_gates=("rx", "rz"),
            connectivity=Connectivity.linear(4),
        )
        with self.assertRaisesRegex(GeneratorValidationError, "gate 'cx'.*not allowed"):
            validate_candidate_constraints(candidate, disallowed_gate)

        disallowed_edge = ConstraintSet(
            allowed_gates=("rx", "rz", "cx"),
            connectivity=Connectivity(n_qubits=4, edges=((0, 1),)),
        )
        with self.assertRaisesRegex(GeneratorValidationError, "edge .*not allowed"):
            validate_candidate_constraints(candidate, disallowed_edge)

    def test_candidate_export_rejects_constraint_violations(self) -> None:
        source = build_sanz19_candidate_record("A02", 1, n_qubits=4)
        with self.assertRaisesRegex(GeneratorValidationError, "edge .*not allowed"):
            export_candidate_json(
                source,
                config=CandidateJsonExportConfig(
                    candidate_id_prefix="constraint",
                    n_qubits=4,
                    created_at=CREATED_AT,
                    source_label="constraint-test",
                    git_commit=None,
                    discover_git_commit=False,
                    constraints=ConstraintSet(
                        allowed_gates=("rx", "rz", "cx"),
                        connectivity=Connectivity(n_qubits=4, edges=((0, 1),)),
                    ),
                ),
            )

    def test_insert_gate_factory_enforces_constraint_intent_and_child_validity(self) -> None:
        parent = export_candidate_json(
            build_sanz19_candidate_record("A02", 1, n_qubits=4),
            config=CandidateJsonExportConfig(
                candidate_id_prefix="constraint",
                n_qubits=4,
                created_at=CREATED_AT,
                source_label="constraint-test",
                git_commit=None,
                discover_git_commit=False,
            ),
        )
        constraints = ConstraintSet(
            allowed_gates=("rx", "rz", "cx", "cz"),
            allowed_inserted_gates=("cz",),
            connectivity=Connectivity.linear(4),
        )
        factory = InsertGateMutationFactory(constraints=constraints, created_at=CREATED_AT)
        request = _mutation_request({"gate": "cz", "edge": [1, 2], "parameterized": False})

        child = factory(request, parent)

        self.assertEqual(child["lineage"]["parent_candidate_id"], parent["candidate_id"])
        self.assertIn("cz", {operation["gate"]["name"] for operation in child["circuit"]["operations"]})
        self.assertEqual(validate_candidate_constraints(child, constraints), child)

        with self.assertRaisesRegex(GeneratorValidationError, "inserted gate 'h'.*not allowed"):
            factory(_mutation_request({"gate": "h", "qubits": [0], "parameterized": False}), parent)

        with self.assertRaisesRegex(GeneratorValidationError, "inserted edge \\[0, 2\\].*not allowed"):
            factory(_mutation_request({"gate": "cz", "edge": [0, 2], "parameterized": False}), parent)

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


def _mutation_request(parameters: dict) -> dict:
    return {
        "request_id": "constraint-parent:insert:001",
        "parent_candidate_id": "constraint-a02-l1",
        "generation_index": 1,
        "mutation_type": "insert",
        "policy_id": "constraint-policy",
        "recipe_id": "insert-cz",
        "variant_index": 0,
        "parameters": parameters,
        "metadata": {},
    }


if __name__ == "__main__":
    unittest.main()
