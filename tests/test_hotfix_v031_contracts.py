"""v0.3.1 hotfix contract-hardening regression tests."""

from __future__ import annotations

from importlib import metadata
from pathlib import Path
import tempfile
import tomllib
import unittest
from unittest import mock

import yaml

import verfeinert
from verfeinert._version import PACKAGE_NAME, SOURCE_TREE_VERSION
from verfeinert.ansatz_analyzer import (
    AnalyzerConfig,
    AnalyzerConfigError,
    StructuralCostConfig,
)
from verfeinert.ansatz_evolver import EvolverConfig
from verfeinert.core import CoreValidationError
from verfeinert.core.config import ExecutionConfig
from verfeinert.workflow import WorkflowConfig, WorkflowConfigError, WorkflowRunner


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CREATED_AT = "2026-08-20T00:00:00Z"


def _bounds() -> dict[str, dict[str, float]]:
    return {
        "parameter_count": {"min": 0.0, "max": 16.0},
        "depth": {"min": 0.0, "max": 32.0},
        "two_qubit_operation_count": {"min": 0.0, "max": 8.0},
    }


def _workflow_mapping(output_root: Path) -> dict:
    return {
        "run": {"run_id": "v031-multiprocessing", "created_at": CREATED_AT},
        "paths": {"output_root": str(output_root)},
        "workflow": {
            "campaign_type": "individual",
            "scientific_execution": ["generate", "analyze"],
            "postprocessing": [],
        },
        "execution": {
            "mode": "multiprocessing",
            "parallelize_candidates": True,
            "worker_count": 2,
        },
        "generation": {
            "family": "sanz19",
            "template_ids": ["A02"],
            "layers": [1],
            "n_qubits": 4,
            "candidate_id_prefix": "v031",
        },
        "analyzer": {
            "selected_metrics": ["structural_cost"],
            "structural_cost": {"reference_bounds": _bounds()},
        },
    }


class HotfixV031ContractTests(unittest.TestCase):
    def test_authoritative_version_surfaces_are_synchronized(self) -> None:
        project = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        citation = yaml.safe_load((PROJECT_ROOT / "CITATION.cff").read_text(encoding="utf-8"))
        changelog = (PROJECT_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        expected = project["project"]["version"]

        self.assertEqual(SOURCE_TREE_VERSION, expected)
        self.assertEqual(metadata.version(PACKAGE_NAME), expected)
        self.assertEqual(verfeinert.__version__, expected)
        self.assertEqual(citation["version"], expected)
        self.assertIn(f"## v{expected} -", changelog)

    def test_direct_analyzer_rejects_scientific_multiprocessing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_root = root / "inputs"
            input_root.mkdir()

            with self.assertRaisesRegex(AnalyzerConfigError, "multiprocessing executor primitives"):
                AnalyzerConfig(
                    run_id="v031-analyzer",
                    input_roots=(input_root,),
                    output_root=root / "outputs",
                    selected_metrics=("structural_cost",),
                    structural_cost=StructuralCostConfig(reference_bounds=_bounds()),
                    execution=ExecutionConfig(
                        mode="multiprocessing",
                        parallelize_candidates=True,
                        worker_count=2,
                    ),
                )

    def test_workflow_rejects_multiprocessing_before_scientific_work(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_root = Path(tmp) / "outputs"
            config = WorkflowConfig.from_mapping(_workflow_mapping(output_root))

            with mock.patch.object(
                WorkflowRunner,
                "_generate_records",
                side_effect=AssertionError("generation must not start"),
            ):
                with self.assertRaisesRegex(WorkflowConfigError, "multiprocessing executor primitives"):
                    WorkflowRunner(config).run()

    def test_evolver_config_rejects_scientific_multiprocessing_claims(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(CoreValidationError, "multiprocessing executor primitives"):
                EvolverConfig(
                    run_id="v031-evolver",
                    output_root=Path(tmp) / "outputs",
                    execution=ExecutionConfig(
                        mode="multiprocessing",
                        parallelize_candidates=True,
                        worker_count=2,
                    ),
                )

    def test_sequential_workflow_execution_still_runs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            mapping = _workflow_mapping(Path(tmp) / "outputs")
            mapping["execution"] = {"mode": "sequential"}
            result = WorkflowRunner(WorkflowConfig.from_mapping(mapping)).run()

            self.assertEqual(result.executed_operations, ("generate", "analyze"))
            self.assertEqual(result.candidate_ids, ("v031-a02-l1",))


if __name__ == "__main__":
    unittest.main()
