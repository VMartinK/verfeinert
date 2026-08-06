"""Tests for metadata-only candidate compilation and staging."""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from verfeinert.ansatz_generator import (
    CANDIDATE_MANIFEST_SCHEMA_VERSION,
    CANDIDATE_METADATA_SCHEMA_VERSION,
    CandidateCompilationBoundary,
    CandidateCompilationConfig,
    build_callable_module_source,
    compile_candidate_records,
    compile_operation_to_source,
    compute_candidate_lineage_hash,
    compute_candidate_structural_hash,
    load_compiled_candidate_records,
    normalize_candidate_record,
    normalize_operation_record,
)
from verfeinert.ansatz_generator.validation import GeneratorValidationError
from verfeinert.core.io import read_json


EXPECTED_STRUCTURAL_HASH = "1e570166e0cef6151ea5dac603c2db7d92af4d6f574bc34bea01ac46ec706164"
EXPECTED_LINEAGE_HASH = "9497fa31f16f16c54af63d3783a4aabf54b6b70c2995970c9afc42ae83a1612e"


def _records() -> list[dict[str, object]]:
    return [
        {
            "circuit_id": "ARTIFICIAL_A_G001-V001",
            "generation_index": 1,
            "parent_circuit_id": "ARTIFICIAL_A",
            "root_circuit_id": "ARTIFICIAL_A",
            "layer": 1,
            "variant_index": 1,
            "recipe_id": "generation_001_beta:1:1",
            "operations": [
                {"gate": "rx", "wires": [0], "parameterized": True},
                {"name": "cx", "qubits": [0, 1]},
            ],
            "metadata": {
                "mutation_type": "insert",
                "mutation_gate": "cx",
                "beta_backend_name": "metadata_operation_beta",
            },
        },
        {
            "circuit_id": "ARTIFICIAL_A_G001-V002",
            "generation_index": 1,
            "parent_circuit_id": "ARTIFICIAL_A",
            "root_circuit_id": "ARTIFICIAL_A",
            "layer": 1,
            "variant_index": 2,
            "operations": [("ry", [0]), {"gate": "rz", "wires": 0, "params": [0.5]}],
            "parameter_count": 2,
            "metadata": {"mutation_type": "substitute", "mutation_gate": "ry"},
        },
    ]


class AnsatzGeneratorCompilationTests(unittest.TestCase):
    def test_operation_and_candidate_normalization_hash_contract(self) -> None:
        config = CandidateCompilationConfig(run_id="candidate_smoke")
        operation = normalize_operation_record({"name": "CX", "qubits": [0, 1]}, config=config)
        self.assertEqual(operation["gate"], "cx")
        self.assertEqual(operation["wires"], [0, 1])

        normalized, issues = normalize_candidate_record(_records()[0], config=config)
        self.assertEqual(issues, [])
        self.assertEqual(normalized["operation_count"], 2)
        self.assertEqual(normalized["two_qubit_operation_count"], 1)
        self.assertEqual(normalized["parameter_count"], 1)
        self.assertEqual(normalized["structural_hash"], EXPECTED_STRUCTURAL_HASH)
        self.assertEqual(normalized["lineage_provenance_hash"], EXPECTED_LINEAGE_HASH)
        self.assertEqual(compute_candidate_structural_hash(normalized), EXPECTED_STRUCTURAL_HASH)
        self.assertEqual(compute_candidate_lineage_hash(normalized), EXPECTED_LINEAGE_HASH)

    def test_compile_candidate_records_is_metadata_only(self) -> None:
        self.assertIs(CandidateCompilationBoundary, compile_candidate_records)
        result = compile_candidate_records(
            _records(),
            config=CandidateCompilationConfig(run_id="candidate_compile"),
        )

        self.assertEqual(result.output_root, None)
        self.assertEqual(result.wrote_files, ())
        self.assertEqual(len(result.records), 2)
        self.assertFalse(result.scientific_metrics_executed)
        self.assertFalse(result.qnodes_executed)
        self.assertTrue(all(record["compiled_metadata_validated"] for record in result.records))

        with self.assertRaises(GeneratorValidationError):
            compile_candidate_records(
                [_records()[0], _records()[0]],
                config=CandidateCompilationConfig(run_id="duplicate"),
            )

    def test_staged_package_creation_uses_caller_output_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_root = Path(tmp) / "outputs"
            result = compile_candidate_records(
                _records(),
                config=CandidateCompilationConfig(
                    run_id="generation_001_compiled_beta",
                    output_root=output_root,
                    generation_index=1,
                ),
            )

            self.assertEqual(result.output_root, output_root.resolve() / "generation_001_compiled_beta")
            self.assertTrue(result.metadata_json_path.exists())
            self.assertTrue(result.metadata_csv_path.exists())
            self.assertTrue(result.manifest_path.exists())
            self.assertEqual(len(result.wrote_files), 3)

            payload = read_json(result.metadata_json_path)
            manifest = read_json(result.manifest_path)
            self.assertEqual(payload["schema_version"], CANDIDATE_METADATA_SCHEMA_VERSION)
            self.assertEqual(manifest["schema_version"], CANDIDATE_MANIFEST_SCHEMA_VERSION)
            self.assertFalse(payload["summary"]["qnodes_executed"])
            self.assertFalse(manifest["scientific_metrics_executed"])
            self.assertEqual(len(load_compiled_candidate_records(result.output_root)), 2)
            self.assertEqual(len(load_compiled_candidate_records(result.metadata_csv_path)), 2)

    def test_callable_source_generation_does_not_import_or_execute(self) -> None:
        config = CandidateCompilationConfig(run_id="callable_test", write_callable_module=True)
        result = compile_candidate_records(_records(), config=config)
        source = build_callable_module_source(result.records, config=config)
        self.assertIn("QNODES_EXECUTED = False", source)
        self.assertIn("SCIENTIFIC_METRICS_EXECUTED = False", source)
        self.assertIn("CIRCUIT_REGISTRY", source)
        self.assertNotIn("@qml.qnode", source.lower())

        source_line, next_index = compile_operation_to_source(
            {"gate": "rx", "wires": [0], "parameterized": True},
            param_index=0,
        )
        self.assertIn("qml.RX(params[0]", source_line)
        self.assertEqual(next_index, 1)

        with self.assertRaises(GeneratorValidationError):
            compile_candidate_records(
                [
                    {
                        "circuit_id": "BAD",
                        "generation_index": 1,
                        "parent_circuit_id": "P",
                        "root_circuit_id": "P",
                        "layer": 1,
                        "operations": [{"gate": "unknown", "wires": [0]}],
                    }
                ],
                config=CandidateCompilationConfig(run_id="bad", write_callable_module=True),
            )


if __name__ == "__main__":
    unittest.main()
