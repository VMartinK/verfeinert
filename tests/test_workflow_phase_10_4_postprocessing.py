"""Phase 10.4 workflow tests for persisted postprocessing artifacts."""

from __future__ import annotations

import csv
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from verfeinert.ansatz_analyzer import (
    AnalysisPipeline,
    AnalysisResultCollection,
    ComparisonConfig,
    ComparisonSource,
    compare_analysis_collections,
)
from verfeinert.ansatz_analyzer.metrics.runtime import optional_dependency_available
from verfeinert.ansatz_analyzer.tables import write_comparison_json
from verfeinert.core.io import read_json
from verfeinert.workflow import WorkflowConfig, WorkflowRunner


CREATED_AT = "2026-08-13T00:00:00Z"


def _metric_configs() -> tuple[dict, dict]:
    return (
        {
            "configuration": {
                "n_qubits": 4,
                "n_pairs": 3,
                "n_bins": 4,
                "rng_seed": 42,
                "rng_policy": "per_circuit",
            },
        },
        {
            "configuration": {
                "n_qubits": 4,
                "n_repeats": 3,
                "trainability_n_pairs": 3,
                "rng_seed": 42,
                "rng_policy": "per_circuit",
                "hamiltonian_kind": "sum_x",
                "hamiltonian": "local_x",
                "hamiltonian_scale": 1.0,
            },
            "hamiltonian": "local_x",
            "hamiltonian_kind": "sum_x",
            "hamiltonian_definition": "H = sum_i X_i",
            "hamiltonian_scale": 1.0,
        },
    )


def _cost_metadata() -> dict:
    return {
        "cost_model": "reference_normalized_structural_cost",
        "definition": "weighted average of reference-normalized structure",
        "reference_id": "workflow-shared-reference",
        "reference_bounds": {
            "parameter_count": {"min": 0.0, "max": 10.0},
            "depth": {"min": 0.0, "max": 20.0},
            "two_qubit_operation_count": {"min": 0.0, "max": 8.0},
        },
        "component_weights": {
            "parameter_count": 1.0,
            "depth": 1.0,
            "two_qubit_operation_count": 1.0,
        },
        "depth_source": "metadata.structural.depth",
    }


def _analysis_result(
    candidate_id: str,
    *,
    expressibility: float,
    trainability: float,
    cost: float,
    generation: int = 0,
) -> dict:
    express_meta, train_meta = _metric_configs()
    return {
        "schema_version": "verfeinert.analysis_result.v1",
        "analysis_result_id": f"analysis-{candidate_id}",
        "candidate_ref": {"candidate_id": candidate_id, "structural_hash": "2" * 64},
        "metrics": [
            {
                "metric_id": f"metric-expressibility-{candidate_id}",
                "name": "expressibility",
                "status": "computed",
                "value": {"expressibility": expressibility, "dkl": 10 ** -expressibility},
                "metadata": express_meta,
            },
            {
                "metric_id": f"metric-trainability-{candidate_id}",
                "name": "trainability",
                "status": "computed",
                "value": {"trainability": trainability, "holmes_metric": trainability},
                "metadata": train_meta,
            },
        ],
        "cost": {
            "structural_cost": cost,
            "parameter_count": 3,
            "operation_count": 5,
            "two_qubit_operation_count": 2,
            "metadata": _cost_metadata(),
        },
        "classifications": [],
        "metadata": {
            "candidate_semantics": {
                "lineage": {
                    "generation": generation,
                    "root_candidate_id": candidate_id if generation == 0 else "root",
                    "parent_candidate_id": None if generation == 0 else "root",
                },
                "source_context": {"layer": generation + 1},
            },
        },
        "provenance": {
            "created_at": CREATED_AT,
            "analyzer": "phase-10-4-workflow-test",
            "execution": {"qnodes_executed": False},
        },
    }


def _write(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _evolution_run() -> dict:
    return {
        "schema_version": "verfeinert.evolution_run.v1",
        "evolution_run_id": "persisted-evolution",
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
        "configuration": {"random_seed": 17, "execution": {}},
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
                "candidate_refs": [{"candidate_id": "child"}],
                "survivor_refs": [{"candidate_id": "child"}],
                "archive_refs": [{"candidate_id": "child"}],
            },
        ],
        "provenance": {
            "created_at": CREATED_AT,
            "source": "phase-10-4-workflow-test",
            "input_hashes": {},
        },
    }


def _workflow_mapping(output_root: Path, *, run_id: str, postprocessing, comparisons=(), artifacts=None) -> dict:
    return {
        "run": {"run_id": run_id, "created_at": CREATED_AT},
        "paths": {"output_root": str(output_root)},
        "workflow": {
            "campaign_type": "individual",
            "scientific_execution": [],
            "postprocessing": list(postprocessing),
        },
        "analyzer": {
            "selected_metrics": ["structural_cost"],
            "ranking": {
                "score_components": {"expressibility": 1.0, "trainability": 1.0},
                "combination": "product",
                "ascending": False,
            },
            "pareto": {
                "objectives": [
                    {"metric_name": "trainability", "direction": "maximize"},
                    {"metric_name": "expressibility", "direction": "maximize"},
                ],
            },
        },
        "artifacts": artifacts or {},
        "comparisons": list(comparisons),
    }


class WorkflowPhase104PostprocessingTests(unittest.TestCase):
    def test_analysis_result_artifacts_compare_and_export_csv_without_analysis(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            a_path = _write(root / "inputs" / "a.json", _analysis_result("candidate-a", expressibility=2.0, trainability=0.6, cost=0.2))
            b_path = _write(root / "inputs" / "b.json", _analysis_result("candidate-b", expressibility=1.5, trainability=0.9, cost=0.3))
            mapping = _workflow_mapping(
                root / "outputs",
                run_id="analysis-to-comparison-csv",
                postprocessing=("comparison", "csv"),
                comparisons=[
                    {
                        "comparison_id": "selected-ab",
                        "sources": [
                            {"source_id": "run-a", "analysis_results": [str(a_path)]},
                            {"source_id": "run-b", "analysis_results": [str(b_path)]},
                        ],
                        "cost_thresholds": [1.0],
                    },
                ],
            )

            with mock.patch.object(AnalysisPipeline, "run_and_write", side_effect=AssertionError("analyzer must not run")):
                result = WorkflowRunner(WorkflowConfig.from_mapping(mapping)).run()

            self.assertEqual(result.executed_operations, ("comparison", "export_csv"))
            self.assertEqual(result.analysis_result_paths, ())
            self.assertEqual(len(result.comparison_json_paths), 1)
            self.assertEqual(len(result.comparison_csv_paths), 1)
            self.assertFalse(result.provenance["execution"]["analysis_executed"])
            self.assertTrue(result.provenance["execution"]["comparison_executed"])
            with result.comparison_csv_paths[0].open("r", encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual({row["candidate_id"] for row in rows}, {"candidate-a", "candidate-b"})

    def test_comparison_result_artifact_exports_csv_without_recomputing_comparison(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            comparison = compare_analysis_collections(
                (
                    ComparisonSource(
                        "run-a",
                        AnalysisResultCollection.from_records([
                            _analysis_result("candidate-a", expressibility=2.0, trainability=0.6, cost=0.2),
                        ]),
                    ),
                    ComparisonSource(
                        "run-b",
                        AnalysisResultCollection.from_records([
                            _analysis_result("candidate-b", expressibility=1.5, trainability=0.9, cost=0.3),
                        ]),
                    ),
                ),
                config=ComparisonConfig(comparison_id="persisted-ab"),
            )
            artifact = write_comparison_json(
                comparison,
                output_root=root / "inputs",
                run_id="persisted",
                input_roots=(root / "source",),
            )
            mapping = _workflow_mapping(
                root / "outputs",
                run_id="comparison-json-to-csv",
                postprocessing=("csv",),
                artifacts={"comparison_results": [str(artifact.path)]},
            )

            with mock.patch("verfeinert.workflow.runner.compare_analysis_collections", side_effect=AssertionError("comparison must not rerun")):
                result = WorkflowRunner(WorkflowConfig.from_mapping(mapping)).run()

            self.assertEqual(result.executed_operations, ("export_csv",))
            self.assertEqual(len(result.comparison_csv_paths), 1)
            self.assertEqual(result.reused_artifacts[0]["kind"], "comparison_result")
            self.assertFalse(result.provenance["execution"]["comparison_executed"])

    def test_comparison_result_artifact_visualizes_without_recomputing_comparison(self) -> None:
        if not optional_dependency_available("matplotlib"):
            self.skipTest("Matplotlib is not installed.")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            comparison = compare_analysis_collections(
                (
                    ComparisonSource(
                        "run-a",
                        AnalysisResultCollection.from_records([
                            _analysis_result("candidate-a", expressibility=2.0, trainability=0.6, cost=0.2),
                        ]),
                    ),
                    ComparisonSource(
                        "run-b",
                        AnalysisResultCollection.from_records([
                            _analysis_result("candidate-b", expressibility=1.5, trainability=0.9, cost=0.3),
                        ]),
                    ),
                ),
                config=ComparisonConfig(comparison_id="viz-ab"),
            )
            artifact = write_comparison_json(
                comparison,
                output_root=root / "inputs",
                run_id="persisted",
                input_roots=(root / "source",),
            )
            mapping = _workflow_mapping(
                root / "outputs",
                run_id="comparison-json-to-viz",
                postprocessing=("visualization",),
                artifacts={"comparison_results": [str(artifact.path)]},
            )

            with mock.patch("verfeinert.workflow.runner.compare_analysis_collections", side_effect=AssertionError("comparison must not rerun")):
                with mock.patch.object(AnalysisPipeline, "run_and_write", side_effect=AssertionError("analyzer must not run")):
                    result = WorkflowRunner(WorkflowConfig.from_mapping(mapping)).run()

            self.assertEqual(result.executed_operations, ("visualization",))
            self.assertEqual(len(result.visualization_paths), 1)
            self.assertTrue(result.visualization_paths[0].is_file())
            self.assertTrue(result.provenance["execution"]["visualization_executed"])

    def test_analysis_results_pareto_ranking_visualization_only_runs_requested_postprocessing(self) -> None:
        if not optional_dependency_available("matplotlib"):
            self.skipTest("Matplotlib is not installed.")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            a_path = _write(root / "inputs" / "a.json", _analysis_result("candidate-a", expressibility=2.0, trainability=0.6, cost=0.2))
            b_path = _write(root / "inputs" / "b.json", _analysis_result("candidate-b", expressibility=1.5, trainability=0.9, cost=0.3))
            mapping = _workflow_mapping(
                root / "outputs",
                run_id="analysis-to-derived-viz",
                postprocessing=("pareto", "ranking", "visualization"),
                artifacts={"analysis_results": [str(a_path), str(b_path)]},
            )

            with mock.patch.object(AnalysisPipeline, "run_and_write", side_effect=AssertionError("analyzer must not run")):
                result = WorkflowRunner(WorkflowConfig.from_mapping(mapping)).run()

            self.assertEqual(result.executed_operations, ("ranking", "pareto", "visualization"))
            self.assertTrue(result.ranking_json_path.is_file())
            self.assertTrue(result.pareto_json_path.is_file())
            self.assertEqual(len(result.visualization_paths), 2)
            self.assertFalse(result.provenance["execution"]["candidate_generation_executed"])
            self.assertFalse(result.provenance["execution"]["analysis_executed"])

    def test_evolution_run_lineage_visualization_does_not_rerun_evolution(self) -> None:
        if not optional_dependency_available("matplotlib"):
            self.skipTest("Matplotlib is not installed.")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            evolution_path = _write(root / "inputs" / "evolution_run.json", _evolution_run())
            mapping = _workflow_mapping(
                root / "outputs",
                run_id="evolution-to-lineage-viz",
                postprocessing=("visualization",),
                artifacts={"evolution_run": str(evolution_path)},
            )

            with mock.patch.object(WorkflowRunner, "_run_evolution", side_effect=AssertionError("evolution must not rerun")):
                result = WorkflowRunner(WorkflowConfig.from_mapping(mapping)).run()

            self.assertEqual(result.executed_operations, ("visualization",))
            self.assertEqual(len(result.visualization_paths), 1)
            self.assertTrue(result.visualization_paths[0].is_file())
            self.assertFalse(result.provenance["execution"]["evolution_exported"])

    def test_multiple_named_comparisons_produce_separate_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            a_path = _write(root / "inputs" / "a.json", _analysis_result("candidate-a", expressibility=2.0, trainability=0.6, cost=0.2))
            b_path = _write(root / "inputs" / "b.json", _analysis_result("candidate-b", expressibility=1.5, trainability=0.9, cost=0.3))
            c_path = _write(root / "inputs" / "c.json", _analysis_result("candidate-c", expressibility=2.5, trainability=0.4, cost=0.1))
            mapping = _workflow_mapping(
                root / "outputs",
                run_id="two-comparisons",
                postprocessing=("comparison", "csv"),
                comparisons=[
                    {
                        "comparison_id": "comparison-a-b",
                        "sources": [
                            {"source_id": "run-a", "analysis_results": [str(a_path)]},
                            {"source_id": "run-b", "analysis_results": [str(b_path)]},
                        ],
                    },
                    {
                        "comparison_id": "comparison-b-c",
                        "sources": [
                            {"source_id": "run-b", "analysis_results": [str(b_path)]},
                            {"source_id": "run-c", "analysis_results": [str(c_path)]},
                        ],
                    },
                ],
            )

            result = WorkflowRunner(WorkflowConfig.from_mapping(mapping)).run()

            self.assertEqual(len(result.comparison_json_paths), 2)
            self.assertEqual(len(result.comparison_csv_paths), 2)
            ids = {
                read_json(path)["comparison_id"]
                for path in result.comparison_json_paths
            }
            self.assertEqual(ids, {"comparison-a-b", "comparison-b-c"})


if __name__ == "__main__":
    unittest.main()
