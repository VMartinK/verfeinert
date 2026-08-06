"""Tests for public canonical ansatz_generator exporters."""

from __future__ import annotations

import ast
import json
from pathlib import Path
import tempfile
import unittest

from verfeinert.ansatz_analyzer import validate_candidate_document, validate_staged_package_document
from verfeinert.ansatz_generator import (
    CandidateJsonExportConfig,
    StagedPackageJsonExportConfig,
    build_sanz19_candidate_record,
    build_sanz19_candidate_records,
    export_candidate_json,
    export_staged_package_json,
    move_first_gate_to_end_on_wire,
    write_staged_package_json,
)
from verfeinert.core import read_json


PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXPORTER_ROOT = PROJECT_ROOT / "verfeinert" / "ansatz_generator" / "exporters"
CREATED_AT = "2026-08-06T00:00:00Z"

FORBIDDEN_IMPORT_PREFIXES = (
    "verfeinert.ansatz_analyzer",
    "verfeinert.ansatz_evolver",
    "ansatz_analyzer",
    "ansatz_evolver",
    "notebook",
    "nbformat",
    "nbclient",
    "pennylane",
    "matplotlib",
)

FORBIDDEN_TOKENS = (
    "/home/",
    "C:\\Users",
    "\\Users\\",
    "Thesis_Data_Processing",
    "python/analysis",
    "analysis_results",
    "analysis_exports",
    "TFG",
)


def _candidate_config(**overrides) -> CandidateJsonExportConfig:
    values = {
        "created_at": CREATED_AT,
        "source_label": "ansatz_generator_exporter_test",
        "git_commit": None,
        "discover_git_commit": False,
    }
    values.update(overrides)
    return CandidateJsonExportConfig(**values)


def _package_config(**overrides) -> StagedPackageJsonExportConfig:
    values = {
        "package_id": "exporter-package",
        "candidate_export": _candidate_config(),
        "created_at": CREATED_AT,
        "producer": "ansatz_generator_exporter_test",
        "git_commit": None,
        "discover_git_commit": False,
    }
    values.update(overrides)
    return StagedPackageJsonExportConfig(**values)


def _mutated_child(parent: dict) -> dict:
    mutation = move_first_gate_to_end_on_wire(parent["operations"], 0)
    child = dict(parent)
    child.update(
        {
            "circuit_id": "SANZ19-A02-L1-M001",
            "parent_circuit_id": parent["circuit_id"],
            "root_circuit_id": parent["circuit_id"],
            "generation_index": 1,
            "variant_index": 1,
            "mutation_type": "move_first_gate_to_end_on_wire",
            "mutation_status": mutation["mutation_status"],
            "mutation_target_gate_name": mutation["mutation_target_gate_name"],
            "mutation_target_wires": mutation["mutation_target_wires"],
            "mutation_original_position": mutation["mutation_original_position"],
            "mutation_new_position": mutation["mutation_new_position"],
            "operations": mutation["operations"],
        }
    )
    return child


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    return imports


class AnsatzGeneratorExporterTests(unittest.TestCase):
    def test_public_import_path_exports_single_candidate(self) -> None:
        source = build_sanz19_candidate_record("A02", 1, n_qubits=4)
        candidate = export_candidate_json(
            source,
            config=_candidate_config(
                candidate_id_prefix="cx01",
                n_qubits=4,
                metadata={"example": "cx01_single_analysis"},
            ),
        )

        validate_candidate_document(candidate)
        self.assertEqual(candidate["candidate_id"], "cx01-a02-l1")
        self.assertEqual(candidate["schema_version"], "verfeinert.candidate.v1")
        self.assertEqual(candidate["circuit"]["n_qubits"], 4)
        self.assertEqual(candidate["provenance"]["source"]["kind"], "template")
        self.assertIn(
            "cx",
            {operation["gate"]["name"] for operation in candidate["circuit"]["operations"]},
        )

    def test_candidate_export_is_deterministic_and_preserves_structure(self) -> None:
        source = build_sanz19_candidate_record("A02", 1, n_qubits=2)
        first = export_candidate_json(source, config=_candidate_config(n_qubits=2))
        second = export_candidate_json(source, config=_candidate_config(n_qubits=2))
        changed = dict(source)
        changed["operations"] = [
            *source["operations"],
            {
                "gate": "h",
                "wires": [0],
                "parameterized": False,
                "params": None,
                "metadata": {"layer_index": 0, "order": len(source["operations"]), "role": "basis_change"},
            },
        ]
        changed_candidate = export_candidate_json(changed, config=_candidate_config(candidate_id="changed-a02-l1", n_qubits=2))

        self.assertEqual(first, second)
        self.assertNotEqual(
            first["identity"]["structural_hash"],
            changed_candidate["identity"]["structural_hash"],
        )
        self.assertEqual(first["identity"]["lineage_hash"], second["identity"]["lineage_hash"])

    def test_staged_package_export_validates_and_preserves_lineage(self) -> None:
        parent = build_sanz19_candidate_record("A02", 1, n_qubits=2)
        child = _mutated_child(parent)
        package = export_staged_package_json(
            [parent, child],
            config=_package_config(),
        )

        validate_staged_package_document(package)
        self.assertEqual(package["manifest"]["candidate_count"], 2)
        parent_candidate, child_candidate = package["candidates"]
        self.assertEqual(child_candidate["lineage"]["parent_candidate_id"], parent_candidate["candidate_id"])
        self.assertEqual(child_candidate["lineage"]["root_candidate_id"], parent_candidate["candidate_id"])
        self.assertEqual(child_candidate["lineage"]["mutation"]["source_candidate_id"], parent_candidate["candidate_id"])
        self.assertEqual(child_candidate["lineage"]["mutation"]["type"], "move_first_gate_to_end_on_wire")

    def test_staged_package_write_uses_relative_artifacts_under_output_root(self) -> None:
        records = build_sanz19_candidate_records(["A02"], [1, 2], n_qubits=2)
        with tempfile.TemporaryDirectory() as tmp:
            output_root = Path(tmp) / "exports"
            result = write_staged_package_json(
                records,
                config=_package_config(output_root=output_root),
            )

            self.assertIsNotNone(result.staged_package_path)
            self.assertEqual(len(result.candidate_paths), 2)
            self.assertTrue(result.staged_package_path.is_file())
            self.assertTrue(result.staged_package_path.resolve().is_relative_to(output_root.resolve()))
            for candidate_path in result.candidate_paths:
                self.assertTrue(candidate_path.resolve().is_relative_to(output_root.resolve()))
                validate_candidate_document(read_json(candidate_path))
            staged_package = validate_staged_package_document(read_json(result.staged_package_path))
            for artifact in staged_package["artifacts"]:
                self.assertFalse(Path(artifact["uri"]).is_absolute())
                self.assertTrue(artifact["hash"])

            generated_text = "\n".join(
                path.read_text(encoding="utf-8")
                for path in [result.staged_package_path, *result.candidate_paths]
            )
            for token in FORBIDDEN_TOKENS:
                self.assertNotIn(token, generated_text)

    def test_exporter_source_has_no_forbidden_dependency_coupling(self) -> None:
        violations: list[str] = []
        for path in sorted(EXPORTER_ROOT.rglob("*.py")):
            for module in _imported_modules(path):
                if any(
                    module == forbidden or module.startswith(f"{forbidden}.")
                    for forbidden in FORBIDDEN_IMPORT_PREFIXES
                ):
                    violations.append(f"{path.relative_to(PROJECT_ROOT)} imports {module}")
            text = path.read_text(encoding="utf-8")
            for token in FORBIDDEN_TOKENS:
                if token in text:
                    violations.append(f"{path.relative_to(PROJECT_ROOT)} contains {token!r}")

        self.assertEqual(violations, [])

    def test_written_package_json_is_stable_for_fixed_inputs(self) -> None:
        records = build_sanz19_candidate_records(["A02"], [1], n_qubits=2)
        with tempfile.TemporaryDirectory() as first_tmp, tempfile.TemporaryDirectory() as second_tmp:
            first = write_staged_package_json(
                records,
                config=_package_config(output_root=Path(first_tmp) / "exports"),
            )
            second = write_staged_package_json(
                records,
                config=_package_config(output_root=Path(second_tmp) / "exports"),
            )

            first_payload = read_json(first.staged_package_path)
            second_payload = read_json(second.staged_package_path)
            first_payload["artifacts"] = [
                {key: value for key, value in artifact.items() if key != "hash"}
                for artifact in first_payload["artifacts"]
            ]
            second_payload["artifacts"] = [
                {key: value for key, value in artifact.items() if key != "hash"}
                for artifact in second_payload["artifacts"]
            ]
            self.assertEqual(first_payload, second_payload)


if __name__ == "__main__":
    unittest.main()
