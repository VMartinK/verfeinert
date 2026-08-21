"""Workflow integration tests for publication visualization profiles."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest import mock

from verfeinert.ansatz_analyzer import AnalysisPipeline
from verfeinert.workflow import WorkflowConfig, WorkflowConfigError, WorkflowRunner


CREATED_AT = "2026-08-21T00:00:00Z"
HAS_MATPLOTLIB = importlib.util.find_spec("matplotlib") is not None


def _analysis_result(
    candidate_id: str,
    *,
    expressibility: float | None = 1.5,
    trainability: float | None = 0.5,
    cost: float = 0.25,
    generation: int = 0,
    layer: int = 1,
    lineage: str = "lineage-a",
) -> dict:
    metrics = []
    if expressibility is not None:
        metrics.append(
            {
                "metric_id": f"metric-expressibility-{candidate_id}",
                "name": "expressibility",
                "status": "computed",
                "value": {"expressibility": expressibility, "dkl": 10 ** -expressibility},
            },
        )
    if trainability is not None:
        metrics.append(
            {
                "metric_id": f"metric-trainability-{candidate_id}",
                "name": "trainability",
                "status": "computed",
                "value": {"trainability": trainability, "holmes_metric": trainability},
            },
        )
    return {
        "schema_version": "verfeinert.analysis_result.v1",
        "analysis_result_id": f"analysis-{candidate_id}",
        "candidate_ref": {"candidate_id": candidate_id, "structural_hash": "6" * 64},
        "metrics": metrics,
        "cost": {"structural_cost": cost},
        "classifications": [],
        "metadata": {
            "candidate_semantics": {
                "lineage": {
                    "generation": generation,
                    "root_candidate_id": lineage,
                    "parent_candidate_id": None if generation == 0 else lineage,
                },
                "source_context": {"layer": layer},
            },
        },
        "provenance": {
            "created_at": CREATED_AT,
            "analyzer": "workflow-publication-visualization-test",
            "execution": {"qnodes_executed": False},
        },
    }


def _evolution_run() -> dict:
    return {
        "schema_version": "verfeinert.evolution_run.v1",
        "evolution_run_id": "publication-evolution",
        "run_metadata": {
            "created_at": CREATED_AT,
            "status": "completed",
            "software_version": "test",
            "git_commit": None,
            "execution": {
                "evolver_executed_metrics": False,
                "qnodes_executed_by_evolver": False,
                "analysis_requested": False,
                "analysis_results_ingested": False,
                "selection_executed": False,
                "plots_generated_by_evolver": False,
            },
        },
        "configuration": {"random_seed": 13, "execution": {}},
        "generations": [
            {
                "generation_index": 0,
                "candidate_refs": [{"candidate_id": "root"}],
                "survivor_refs": [{"candidate_id": "root"}],
                "archive_refs": [{"candidate_id": "root"}],
            },
            {
                "generation_index": 1,
                "parent_refs": [{"candidate_id": "root"}],
                "candidate_refs": [{"candidate_id": "child-a"}, {"candidate_id": "child-b"}],
                "survivor_refs": [{"candidate_id": "child-a"}],
                "archive_refs": [{"candidate_id": "child-a"}],
                "rejected_refs": [{"candidate_id": "child-b"}],
            },
        ],
        "provenance": {
            "created_at": CREATED_AT,
            "source": "workflow-publication-visualization-test",
            "input_hashes": {},
        },
    }


def _write(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _workflow_mapping(output_root: Path, *, run_id: str, artifacts: dict, visualization: dict) -> dict:
    return {
        "run": {"run_id": run_id, "created_at": CREATED_AT},
        "paths": {"output_root": str(output_root)},
        "workflow": {
            "campaign_type": "individual",
            "scientific_execution": [],
            "postprocessing": ["visualization"],
            "visualization": visualization,
        },
        "analyzer": {"selected_metrics": ["structural_cost"]},
        "artifacts": artifacts,
    }


@unittest.skipUnless(HAS_MATPLOTLIB, "Matplotlib is not installed.")
class WorkflowPublicationVisualizationTests(unittest.TestCase):
    def test_publication_individual_profile_exports_prepared_analysis_figures(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            alpha = _write(root / "inputs" / "alpha.json", _analysis_result("alpha"))
            beta = _write(
                root / "inputs" / "beta.json",
                _analysis_result("beta", trainability=0.8, layer=2, lineage="lineage-b"),
            )
            mapping = _workflow_mapping(
                root / "outputs",
                run_id="publication-individual",
                artifacts={"analysis_results": [str(alpha), str(beta)]},
                visualization={
                    "profile": "publication",
                    "figure_set": "individual",
                    "formats": ["png"],
                },
            )

            with mock.patch.object(AnalysisPipeline, "run_and_write", side_effect=AssertionError("analyzer must not run")):
                result = WorkflowRunner(WorkflowConfig.from_mapping(mapping)).run()

            self.assertEqual(result.executed_operations, ("visualization",))
            self.assertEqual(
                [path.name for path in result.visualization_paths],
                ["individual_by_layer.png", "individual_by_lineage.png"],
            )
            self.assertTrue(all(path.is_file() for path in result.visualization_paths))
            self.assertTrue(all(path.parent.name == "publication" for path in result.visualization_paths))
            self.assertTrue(result.provenance["execution"]["visualization_executed"])
            self.assertTrue(result.provenance["execution"]["figure_exported"])

    def test_publication_profile_honors_configured_export_formats(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = _write(root / "inputs" / "alpha.json", _analysis_result("alpha"))
            mapping = _workflow_mapping(
                root / "outputs",
                run_id="publication-formats",
                artifacts={"analysis_results": [str(source)]},
                visualization={
                    "profile": "publication",
                    "figures": ["individual_by_layer"],
                    "formats": ["png", "svg"],
                },
            )

            result = WorkflowRunner(WorkflowConfig.from_mapping(mapping)).run()

            self.assertEqual(
                [path.name for path in result.visualization_paths],
                ["individual_by_layer.png", "individual_by_layer.svg"],
            )
            self.assertTrue(all(path.is_file() for path in result.visualization_paths))

    def test_publication_evolution_profile_exports_generation_counts(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            evolution_path = _write(root / "inputs" / "evolution_run.json", _evolution_run())
            mapping = _workflow_mapping(
                root / "outputs",
                run_id="publication-evolution",
                artifacts={"evolution_run": str(evolution_path)},
                visualization={
                    "profile": "publication",
                    "figure_set": "evolution",
                    "formats": ["png"],
                },
            )

            with mock.patch.object(WorkflowRunner, "_run_evolution", side_effect=AssertionError("evolution must not run")):
                result = WorkflowRunner(WorkflowConfig.from_mapping(mapping)).run()

            self.assertEqual(result.executed_operations, ("visualization",))
            self.assertEqual(
                [path.name for path in result.visualization_paths],
                ["evolution_candidate_counts.png"],
            )
            self.assertTrue(result.visualization_paths[0].is_file())
            self.assertFalse(result.provenance["execution"]["evolution_exported"])

    def test_publication_profile_rejects_missing_objective_metrics(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = _write(
                root / "inputs" / "structural-only.json",
                _analysis_result("structural-only", expressibility=None, trainability=None),
            )
            mapping = _workflow_mapping(
                root / "outputs",
                run_id="publication-missing-metrics",
                artifacts={"analysis_results": [str(source)]},
                visualization={
                    "profile": "publication",
                    "figures": ["individual_by_layer"],
                    "formats": ["png"],
                },
            )

            with self.assertRaisesRegex(WorkflowConfigError, "no supported input artifact"):
                WorkflowRunner(WorkflowConfig.from_mapping(mapping)).run()


if __name__ == "__main__":
    unittest.main()
