"""Tests for the public Verfeinert workflow runner."""

from __future__ import annotations

import ast
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from verfeinert.core.io import PathValidationError
from verfeinert.workflow import WorkflowConfig, WorkflowConfigError, WorkflowRunner


PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_ROOT = PROJECT_ROOT / "verfeinert" / "workflow"
CREATED_AT = "2026-08-06T00:00:00Z"


def _workflow_mapping(output_root: Path) -> dict:
    return {
        "run": {
            "run_id": "runner-minimal",
            "created_at": CREATED_AT,
            "random_seed": 11,
        },
        "paths": {
            "output_root": str(output_root),
        },
        "generation": {
            "family": "sanz19",
            "template_ids": ["A02"],
            "layers": [1],
            "n_qubits": 4,
            "candidate_id_prefix": "runner",
        },
        "analyzer": {
            "selected_metrics": ["structural_cost"],
            "structural_cost": {
                "reference_id": "runner-set",
                "reference_bounds": {
                    "parameter_count": {"min": 1, "max": 16},
                    "depth": {"min": 1, "max": 32},
                    "two_qubit_operation_count": {"min": 0, "max": 8},
                },
            },
            "ranking": {
                "score_components": {"cost.structural_cost": 1.0},
                "combination": "weighted_sum",
                "ascending": True,
            },
        },
        "evolver": {
            "selection_mode": "fitness",
            "policy_id": "runner-selection",
            "metric_name": "structural_cost",
            "keep": 1,
            "direction": "minimize",
            "max_generations": 1,
        },
    }


class WorkflowRunnerTests(unittest.TestCase):
    def test_runner_minimal_execution_produces_artifacts(self) -> None:
        with TemporaryDirectory() as temp_dir:
            config = WorkflowConfig.from_mapping(_workflow_mapping(Path(temp_dir) / "outputs"))
            result = WorkflowRunner(config).run()

            self.assertEqual(result.candidate_ids, ("runner-a02-l1",))
            self.assertEqual(result.survivor_candidate_ids, ("runner-a02-l1",))
            self.assertTrue(result.staged_package_path.is_file())
            self.assertTrue(all(path.is_file() for path in result.analysis_result_paths))
            self.assertTrue(result.evolution_run_path.is_file())
            self.assertIsNotNone(result.ranking_json_path)
            self.assertIsNotNone(result.ranking_csv_path)
            self.assertEqual(result.provenance["runner"], "verfeinert.workflow")
            self.assertFalse(result.provenance["execution"]["qnodes_executed_by_runner"])

            evolution = json.loads(result.evolution_run_path.read_text(encoding="utf-8"))
            generation = evolution["generations"][0]
            self.assertEqual(generation["candidate_refs"][0]["candidate_id"], "runner-a02-l1")
            self.assertEqual(generation["analysis_result_refs"][0]["candidate_id"], "runner-a02-l1")

    def test_invalid_configuration_is_rejected(self) -> None:
        with TemporaryDirectory() as temp_dir:
            mapping = _workflow_mapping(Path(temp_dir) / "outputs")
            mapping["generation"]["family"] = "campaign_specific_branch"
            with self.assertRaises(WorkflowConfigError):
                WorkflowConfig.from_mapping(mapping)

    def test_output_root_separation_is_enforced(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            mapping = _workflow_mapping(root / "inputs" / "nested")
            mapping["paths"]["input_roots"] = [str(root / "inputs")]
            with self.assertRaises(PathValidationError):
                WorkflowConfig.from_mapping(mapping)

    def test_provided_generation_requires_candidate_records(self) -> None:
        with TemporaryDirectory() as temp_dir:
            mapping = _workflow_mapping(Path(temp_dir) / "outputs")
            mapping["generation"]["family"] = "provided"
            config = WorkflowConfig.from_mapping(mapping)
            with self.assertRaises(WorkflowConfigError):
                WorkflowRunner(config).run()

    def test_workflow_source_has_no_campaign_or_scientific_branches(self) -> None:
        forbidden_import_prefixes = (
            "pandas",
            "matplotlib",
            "pennylane",
            "nbformat",
            "nbclient",
            "notebook",
            "Thesis_Data_Processing",
        )
        forbidden_text = (
            "CX01",
            "CX_01",
            "MIXT",
            "Thesis_Data_Processing",
            "qml.QNode",
            "generated_callables",
            "/home/",
        )
        violations: list[str] = []
        for path in WORKFLOW_ROOT.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            for token in forbidden_text:
                if token in text:
                    violations.append(f"{path.relative_to(PROJECT_ROOT)} contains {token}")
            tree = ast.parse(text, filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name.startswith(forbidden_import_prefixes):
                            violations.append(f"{path.relative_to(PROJECT_ROOT)} imports {alias.name}")
                elif isinstance(node, ast.ImportFrom) and node.module:
                    if node.module.startswith(forbidden_import_prefixes):
                        violations.append(f"{path.relative_to(PROJECT_ROOT)} imports {node.module}")
        self.assertEqual(violations, [])


if __name__ == "__main__":
    unittest.main()
