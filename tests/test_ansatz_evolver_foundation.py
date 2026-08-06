"""Foundation tests for the JSON-first ansatz evolver."""

from __future__ import annotations

import ast
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from verfeinert.ansatz_evolver import (
    CandidateRef,
    EvolutionEvent,
    EvolutionRunState,
    EvolverConfig,
    EvolverExecutionPermissions,
    GenerationRecord,
    read_candidate_json,
    validate_evolution_run_document,
)
from verfeinert.ansatz_evolver.exporters import (
    export_evolution_run_json,
    write_evolution_run_json,
)
from verfeinert.core.io import PathValidationError


PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_CANDIDATE = PROJECT_ROOT / "tests" / "fixtures" / "schemas" / "candidate_example.json"
EVOLVER_ROOT = PROJECT_ROOT / "verfeinert" / "ansatz_evolver"


def _candidate_document() -> dict:
    return json.loads(EXAMPLE_CANDIDATE.read_text(encoding="utf-8"))


class EvolverFoundationTests(unittest.TestCase):
    def test_candidate_json_loading_and_reference_creation(self) -> None:
        candidate = read_candidate_json(EXAMPLE_CANDIDATE)
        ref = CandidateRef.from_candidate_document(candidate, candidate_uri="relative://candidate.json")

        self.assertEqual(ref.candidate_id, candidate["candidate_id"])
        self.assertEqual(ref.structural_hash, candidate["identity"]["structural_hash"])
        self.assertEqual(ref.lineage_hash, candidate["identity"]["lineage_hash"])
        self.assertEqual(ref.to_ref_dict()["candidate_uri"], "relative://candidate.json")

    def test_invalid_reference_rejection(self) -> None:
        with self.assertRaises(ValueError):
            CandidateRef(candidate_id="")

    def test_evolver_config_rejects_metric_and_qnode_permissions(self) -> None:
        with TemporaryDirectory() as temp_dir:
            with self.assertRaises(ValueError):
                EvolverConfig(
                    run_id="bad-permissions",
                    output_root=Path(temp_dir) / "outputs",
                    permissions=EvolverExecutionPermissions(allow_qnode_execution=True),
                )

    def test_evolution_run_state_validates_against_schema(self) -> None:
        candidate = _candidate_document()
        ref = CandidateRef.from_candidate_document(candidate)
        generation = GenerationRecord(
            generation_index=0,
            candidate_refs=(ref,),
            survivor_refs=(ref,),
            archive_refs=(ref,),
            events=(
                EvolutionEvent(
                    event_type="initial_population_loaded",
                    candidate_id=ref.candidate_id,
                    status="completed",
                ),
            ),
        )
        state = EvolutionRunState(
            evolution_run_id="evolver-foundation-001",
            status="completed",
            configuration={
                "random_seed": 123,
                "execution": {"mode": "sequential"},
                "mutation_policy": {"policy_id": "none"},
                "selection_policy": {"policy_id": "identity"},
            },
            generations=(generation,),
            created_at="2026-08-04T00:00:00Z",
            git_commit=None,
        )

        document = export_evolution_run_json(state)
        validate_evolution_run_document(document)
        self.assertFalse(document["run_metadata"]["execution"]["evolver_executed_metrics"])
        self.assertFalse(document["run_metadata"]["execution"]["qnodes_executed_by_evolver"])

    def test_evolution_run_write_uses_guarded_output_root(self) -> None:
        candidate = _candidate_document()
        ref = CandidateRef.from_candidate_document(candidate)
        state = EvolutionRunState(
            evolution_run_id="write-run",
            status="planned",
            configuration={"random_seed": None, "execution": {"mode": "sequential"}},
            generations=(GenerationRecord(0, (ref,)),),
            created_at="2026-08-04T00:00:00Z",
            git_commit=None,
        )
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            path = write_evolution_run_json(state, output_root=root / "outputs", input_roots=(root / "inputs",))
            self.assertTrue(path.is_file())
            self.assertTrue(path.resolve().is_relative_to((root / "outputs").resolve()))

            with self.assertRaises(PathValidationError):
                write_evolution_run_json(state, output_root=root / "inputs" / "nested", input_roots=(root / "inputs",))

    def test_boundary_imports_are_dependency_clean(self) -> None:
        forbidden_prefixes = (
            "verfeinert.ansatz_analyzer",
            "verfeinert.ansatz_evolver.visualization",
            "pandas",
            "matplotlib",
            "pennylane",
            "nbformat",
            "nbclient",
            "notebook",
            "Thesis_Data_Processing",
        )
        forbidden_text = (
            "Thesis_Data_Processing",
            "/home/",
            "TFG",
            "generated_callables",
            "qml.QNode",
        )
        violations: list[str] = []
        for path in EVOLVER_ROOT.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            for token in forbidden_text:
                if token in text:
                    violations.append(f"{path.relative_to(PROJECT_ROOT)} contains {token}")
            tree = ast.parse(text, filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name.startswith(forbidden_prefixes):
                            violations.append(f"{path.relative_to(PROJECT_ROOT)} imports {alias.name}")
                elif isinstance(node, ast.ImportFrom) and node.module:
                    if node.module.startswith(forbidden_prefixes):
                        violations.append(f"{path.relative_to(PROJECT_ROOT)} imports {node.module}")
        self.assertEqual(violations, [])


if __name__ == "__main__":
    unittest.main()
