"""Schema-contract tests for ansatz_generator canonical projections."""

from __future__ import annotations

import ast
import json
from pathlib import Path
import tempfile
from typing import Any, Mapping
import unittest

from jsonschema import Draft202012Validator, ValidationError

from verfeinert.ansatz_generator import (
    CandidateCompilationConfig,
    build_sanz19_candidate_record,
    compile_candidate_records,
    move_first_gate_to_end_on_wire,
)
from verfeinert.core.hashing import stable_hash
from verfeinert.core.schema_resources import schema_registry


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCHEMAS_ROOT = PROJECT_ROOT / "schemas"
GENERATOR_ROOT = PROJECT_ROOT / "verfeinert" / "ansatz_generator"
CREATED_AT = "2026-08-04T00:00:00Z"
SOFTWARE_VERSION = "0.0.0"
ZERO_HASH = "0" * 64

SCHEMA_FILES = {
    "candidate": SCHEMAS_ROOT / "candidate.schema.json",
    "staged_package": SCHEMAS_ROOT / "staged_package.schema.json"
}

FORBIDDEN_IMPORTS = {
    "verfeinert.ansatz_analyzer",
    "verfeinert.ansatz_evolver",
    "ansatz_analyzer",
    "ansatz_evolver",
    "notebook",
    "nbclient",
    "nbformat",
}

FORBIDDEN_TOKENS = (
    "Thesis_Data_Processing",
    "analysis_results",
    "analysis_exports",
    "/home/",
    "TFG",
    "tmp/candidate_compilation_boundary",
)


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _validator(schema_name: str) -> Draft202012Validator:
    schema = _read_json(SCHEMA_FILES[schema_name])
    return Draft202012Validator(schema, registry=schema_registry(SCHEMA_FILES))


def _canonical_candidate(
    source: Mapping[str, Any],
    *,
    candidate_id: str | None = None,
    parent_candidate_id: str | None = None,
    root_candidate_id: str | None = None,
    generation: int | None = None,
    mutation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    selected_candidate_id = candidate_id or str(source["circuit_id"]).lower()
    operations = _canonical_operations(source["operations"])
    parameters = _canonical_parameters(operations)
    circuit = {
        "n_qubits": _n_qubits(operations),
        "wire_order": list(range(_n_qubits(operations))),
        "parameters": parameters,
        "operations": operations,
    }
    lineage = {
        "generation": int(generation if generation is not None else source.get("generation_index", 0)),
        "root_candidate_id": root_candidate_id or selected_candidate_id,
        "parent_candidate_id": parent_candidate_id,
        "mutation": mutation,
    }
    identity = {
        "structural_hash": _canonical_structural_hash(circuit),
        "lineage_hash": stable_hash(lineage),
        "hash_schema_version": "verfeinert.candidate_hash.v1",
    }
    return {
        "schema_version": "verfeinert.candidate.v1",
        "candidate_id": selected_candidate_id,
        "identity": identity,
        "circuit": circuit,
        "lineage": lineage,
        "metadata": {
            "generator_source": "verfeinert.ansatz_generator",
            "template_id": source.get("template_id"),
            "source_schema": "projected_from_generator_record",
        },
        "provenance": {
            "created_at": CREATED_AT,
            "source": {
                "kind": "template" if mutation is None else "mutation",
                "label": "ansatz_generator_schema_contract_test",
            },
            "software_version": SOFTWARE_VERSION,
            "git_commit": None,
            "input_hashes": {},
        },
    }


def _canonical_operations(operations: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    parameter_index = 0
    result: list[dict[str, Any]] = []
    for order, operation in enumerate(operations):
        gate = str(operation["gate"]).lower()
        canonical = {
            "operation_id": f"op-{order:03d}",
            "gate": {
                "name": gate,
                "namespace": "verfeinert.default_gates",
            },
            "qubits": [int(wire) for wire in operation["wires"]],
            "parameters": [],
            "layer": int(operation.get("metadata", {}).get("layer_index", 0)),
            "order": order,
            "role": _canonical_role(operation),
            "metadata": {
                "source_order": int(operation.get("metadata", {}).get("order", order)),
            },
        }
        params = operation.get("params")
        if params:
            canonical["parameters"] = [
                {"kind": "literal", "value": value}
                for value in params
            ]
        elif operation.get("parameterized"):
            parameter_id = f"theta-{parameter_index:03d}"
            canonical["parameters"] = [
                {"kind": "reference", "parameter_id": parameter_id}
            ]
            parameter_index += 1
        result.append(canonical)
    return result


def _canonical_role(operation: Mapping[str, Any]) -> str:
    metadata_role = operation.get("metadata", {}).get("role")
    if metadata_role in {
        "rotation",
        "entangler",
        "controlled_rotation",
        "basis_change",
        "measurement_preparation",
        "other",
    }:
        return str(metadata_role)
    gate = str(operation["gate"]).lower()
    if gate in {"rx", "ry", "rz"}:
        return "rotation"
    if gate in {"crx", "cry", "crz"}:
        return "controlled_rotation"
    if gate in {"h"}:
        return "basis_change"
    if len(operation["wires"]) == 2:
        return "entangler"
    return "other"


def _canonical_parameters(operations: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    parameters: list[dict[str, Any]] = []
    seen: set[str] = set()
    for operation in operations:
        for parameter in operation["parameters"]:
            if parameter["kind"] != "reference":
                continue
            parameter_id = str(parameter["parameter_id"])
            if parameter_id in seen:
                continue
            seen.add(parameter_id)
            parameters.append({
                "parameter_id": parameter_id,
                "kind": "trainable",
                "symbol": parameter_id.replace("-", "_"),
            })
    return parameters


def _n_qubits(operations: list[Mapping[str, Any]]) -> int:
    return max(wire for operation in operations for wire in operation["qubits"]) + 1


def _canonical_structural_hash(circuit: Mapping[str, Any]) -> str:
    return stable_hash({
        "n_qubits": circuit["n_qubits"],
        "wire_order": circuit.get("wire_order"),
        "parameters": circuit["parameters"],
        "operations": circuit["operations"],
    })


def _canonical_staged_package(
    *,
    package_id: str,
    candidates: list[dict[str, Any]],
    output_root: Path,
    artifact_paths: list[Path],
) -> dict[str, Any]:
    return {
        "schema_version": "verfeinert.staged_package.v1",
        "package_id": package_id,
        "manifest": {
            "package_kind": "candidate_package",
            "created_at": CREATED_AT,
            "producer": "verfeinert.ansatz_generator",
            "candidate_count": len(candidates),
            "schema_versions": {
                "candidate": "verfeinert.candidate.v1"
            },
            "execution_flags": {
                "qnodes_executed": False,
                "scientific_metrics_executed": False,
                "generated_callables_imported": False,
            },
        },
        "candidates": candidates,
        "artifacts": [
            {
                "artifact_id": f"artifact-{index:03d}",
                "kind": "metadata" if path.suffix == ".json" else "derived_table",
                "uri": path.relative_to(output_root).as_posix(),
                "format": path.suffix.lstrip("."),
            }
            for index, path in enumerate(artifact_paths)
        ],
        "provenance": {
            "created_at": CREATED_AT,
            "source": "ansatz_generator_schema_contract_test",
            "software_version": SOFTWARE_VERSION,
            "git_commit": None,
            "input_hashes": {},
        },
    }


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


class AnsatzGeneratorSchemaContractTests(unittest.TestCase):
    def test_baseline_candidate_projects_to_canonical_candidate_schema(self) -> None:
        generated = build_sanz19_candidate_record("A02", 1, n_qubits=2)
        candidate = _canonical_candidate(generated, candidate_id="baseline-a02-l1")

        _validator("candidate").validate(candidate)
        self.assertEqual(candidate["lineage"]["generation"], 0)
        self.assertEqual(candidate["lineage"]["parent_candidate_id"], None)
        self.assertTrue(candidate["identity"]["structural_hash"])

    def test_mutated_candidate_projects_with_lineage_and_mutation_metadata(self) -> None:
        baseline = build_sanz19_candidate_record("A02", 1, n_qubits=2)
        mutated = dict(baseline)
        mutation_result = move_first_gate_to_end_on_wire(baseline["operations"], 0)
        mutated["operations"] = mutation_result["operations"]

        mutation = {
            "mutation_id": "mutation-001",
            "type": "move_first_gate_to_end_on_wire",
            "source_candidate_id": "baseline-a02-l1",
            "operation": str(mutation_result["mutation_target_gate_name"]),
            "parameters": {
                "wire": 0,
                "status": mutation_result["mutation_status"],
            },
            "metadata": {
                "target_wires": mutation_result["mutation_target_wires"],
            },
        }
        candidate = _canonical_candidate(
            mutated,
            candidate_id="mutated-a02-l1-001",
            parent_candidate_id="baseline-a02-l1",
            root_candidate_id="baseline-a02-l1",
            generation=1,
            mutation=mutation,
        )

        _validator("candidate").validate(candidate)
        self.assertEqual(candidate["lineage"]["parent_candidate_id"], "baseline-a02-l1")
        self.assertEqual(candidate["lineage"]["mutation"]["type"], "move_first_gate_to_end_on_wire")

    def test_canonical_structural_identity_is_deterministic_and_sensitive(self) -> None:
        first = _canonical_candidate(build_sanz19_candidate_record("A02", 1, n_qubits=2), candidate_id="baseline-a02-l1")
        second = _canonical_candidate(build_sanz19_candidate_record("A02", 1, n_qubits=2), candidate_id="baseline-a02-l1-copy")
        changed_source = build_sanz19_candidate_record("A02", 1, n_qubits=2)
        changed_source["operations"] = [*changed_source["operations"], {
            "gate": "h",
            "wires": [0],
            "parameterized": False,
            "params": None,
            "metadata": {
                "layer_index": 0,
                "order": len(changed_source["operations"]),
                "role": "basis_change",
            },
        }]
        changed = _canonical_candidate(changed_source, candidate_id="changed-a02-l1")

        self.assertEqual(first["identity"]["structural_hash"], second["identity"]["structural_hash"])
        self.assertNotEqual(first["identity"]["structural_hash"], changed["identity"]["structural_hash"])
        self.assertEqual(first["identity"]["structural_hash"], _canonical_structural_hash(first["circuit"]))

    def test_staged_package_result_projects_to_canonical_schema(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_root = Path(tmp).resolve()
            generated = build_sanz19_candidate_record("A02", 1, n_qubits=2)
            result = compile_candidate_records(
                [generated],
                config=CandidateCompilationConfig(
                    run_id="schema-contract-package",
                    output_root=output_root,
                    require_parent_links=False,
                ),
            )
            canonical_candidate = _canonical_candidate(generated, candidate_id="baseline-a02-l1")
            package = _canonical_staged_package(
                package_id="schema-contract-package",
                candidates=[canonical_candidate],
                output_root=output_root,
                artifact_paths=[
                    result.metadata_json_path,
                    result.metadata_csv_path,
                    result.manifest_path,
                ],
            )

            _validator("staged_package").validate(package)
            for artifact in package["artifacts"]:
                self.assertFalse(Path(artifact["uri"]).is_absolute())
            for path in (result.metadata_json_path, result.metadata_csv_path, result.manifest_path):
                self.assertTrue(path.resolve().is_relative_to(output_root))

    def test_generated_artifacts_and_generator_imports_are_portable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_root = Path(tmp).resolve()
            generated = build_sanz19_candidate_record("A02", 1, n_qubits=2)
            result = compile_candidate_records(
                [generated],
                config=CandidateCompilationConfig(
                    run_id="portable-package",
                    output_root=output_root,
                    require_parent_links=False,
                ),
            )
            checked_artifacts = [
                result.metadata_json_path,
                result.metadata_csv_path,
                result.manifest_path,
            ]
            violations: list[str] = []
            for path in checked_artifacts:
                text = path.read_text(encoding="utf-8")
                for token in FORBIDDEN_TOKENS:
                    if token in text:
                        violations.append(f"{path.name} contains {token}")
            for source_path in sorted(GENERATOR_ROOT.rglob("*.py")):
                for module in _imported_modules(source_path):
                    if any(module == forbidden or module.startswith(f"{forbidden}.") for forbidden in FORBIDDEN_IMPORTS):
                        violations.append(f"{source_path.relative_to(PROJECT_ROOT)} imports {module}")
                source_text = source_path.read_text(encoding="utf-8")
                for token in FORBIDDEN_TOKENS:
                    if token in source_text:
                        violations.append(f"{source_path.relative_to(PROJECT_ROOT)} contains {token}")

            self.assertEqual(violations, [])

    def test_raw_generator_staged_metadata_is_documented_as_noncanonical(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            generated = build_sanz19_candidate_record("A02", 1, n_qubits=2)
            result = compile_candidate_records(
                [generated],
                config=CandidateCompilationConfig(
                    run_id="raw-noncanonical-package",
                    output_root=Path(tmp),
                    require_parent_links=False,
                ),
            )
            raw_payload = json.loads(result.metadata_json_path.read_text(encoding="utf-8"))

            self.assertEqual(raw_payload["schema_version"], "verfeinert.compiled_candidates.v1")
            with self.assertRaises(ValidationError):
                _validator("staged_package").validate(raw_payload)


if __name__ == "__main__":
    unittest.main()
