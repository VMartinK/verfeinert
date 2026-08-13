"""Phase 5.7 tests for optional visualization boundaries."""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest import mock

from verfeinert.ansatz_analyzer import AnalysisResultCollection
from verfeinert.ansatz_analyzer.ranking import rank_analysis_results
from verfeinert.ansatz_analyzer.visualization import (
    DEFAULT_STYLE,
    FigureExportConfig,
    VisualizationDependencyError,
    comparison_plot_data,
    pareto_plot_data,
    plot_comparison_objective_space,
    plot_lineage_summary,
    plot_pareto_front,
    plot_ranking_scores,
    ranking_plot_data,
    save_figure,
)
from verfeinert.ansatz_analyzer.visualization.evolution import evolution_plot_data
from verfeinert.ansatz_analyzer.visualization.lineage import lineage_plot_data
from verfeinert.ansatz_analyzer.comparison import ComparisonConfig, ComparisonSource, compare_analysis_collections
from verfeinert.ansatz_analyzer.metrics.runtime import optional_dependency_available


def _result(candidate_id: str, *, frontier: bool, generation: int) -> dict:
    return {
        "schema_version": "verfeinert.analysis_result.v1",
        "analysis_result_id": f"analysis-{candidate_id}",
        "candidate_ref": {"candidate_id": candidate_id},
        "metrics": [
            {
                "metric_id": f"metric-expressibility-{candidate_id}",
                "name": "expressibility",
                "status": "computed",
                "value": 2.0 if frontier else 1.0,
                "metadata": {
                    "configuration": {
                        "n_qubits": 4,
                        "n_pairs": 3,
                        "n_bins": 4,
                        "rng_seed": 42,
                        "rng_policy": "per_circuit",
                    },
                },
            },
            {
                "metric_id": f"metric-trainability-{candidate_id}",
                "name": "trainability",
                "status": "computed",
                "value": 0.8 if frontier else 0.4,
                "metadata": {
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
            },
        ],
        "cost": {"structural_cost": 0.2 if frontier else 0.7},
        "classifications": [
            {
                "classification_id": f"pareto-front-{candidate_id}",
                "name": "pareto_front",
                "label": "frontier" if frontier else "dominated",
                "metadata": {"pareto_rank": 1 if frontier else 2},
            },
        ],
        "provenance": {
            "created_at": "2026-08-06T00:00:00Z",
            "analyzer": "phase-5-7-test",
        },
        "metadata": {
            "candidate_semantics": {
                "lineage": {
                    "generation": generation,
                    "root_candidate_id": "candidate-root",
                    "parent_candidate_id": None if generation == 0 else "candidate-root",
                },
                "source_context": {"layer": generation + 1},
            },
        },
    }


class _DummyFigure:
    def savefig(self, path, **_kwargs):
        Path(path).write_text("figure", encoding="utf-8")


class AnalyzerPhase57VisualizationTests(unittest.TestCase):
    def test_default_style_is_centralized_neutral_and_json_safe(self) -> None:
        payload = DEFAULT_STYLE.to_dict()

        self.assertIn("palette", payload)
        self.assertIn("frontier", payload["palette"])
        self.assertEqual(payload["export_format"], "png")
        self.assertEqual(payload["score_colormap"], "plasma")
        self.assertNotIn("thesis", repr(payload).lower())

    def test_pareto_plot_data_consumes_analysis_results(self) -> None:
        collection = AnalysisResultCollection.from_records(
            [
                _result("candidate-a", frontier=False, generation=0),
                _result("candidate-b", frontier=True, generation=1),
            ],
        )

        rows = pareto_plot_data(collection)

        self.assertEqual(rows[0]["candidate_id"], "candidate-a")
        self.assertFalse(rows[0]["is_frontier"])
        self.assertTrue(rows[1]["is_frontier"])
        self.assertEqual(rows[1]["pareto_rank"], 1)

    def test_ranking_plot_data_consumes_ranking_result(self) -> None:
        collection = AnalysisResultCollection.from_records(
            [
                _result("candidate-a", frontier=False, generation=0),
                _result("candidate-b", frontier=True, generation=1),
            ],
        )
        ranking = rank_analysis_results(collection)

        rows = ranking_plot_data(ranking)

        self.assertEqual(rows[0]["candidate_id"], "candidate-b")
        self.assertEqual(rows[0]["rank"], 1)

    def test_lineage_and_evolution_adapters_are_analysis_output_only(self) -> None:
        collection = AnalysisResultCollection.from_records(
            [
                _result("candidate-a", frontier=False, generation=0),
                _result("candidate-b", frontier=True, generation=1),
            ],
        )

        self.assertEqual(lineage_plot_data(collection)[1]["parent_candidate_id"], "candidate-root")
        self.assertEqual(evolution_plot_data(collection)[1]["generation"], 1)

    def test_lineage_adapter_consumes_evolution_run_refs_without_name_parsing(self) -> None:
        evolution = {
            "schema_version": "verfeinert.evolution_run.v1",
            "evolution_run_id": "viz-evolution",
            "generations": [
                {
                    "generation_index": 0,
                    "candidate_refs": [{"candidate_id": "user-root"}],
                    "survivor_refs": [{"candidate_id": "user-root"}],
                    "archive_refs": [{"candidate_id": "user-root"}],
                },
                {
                    "generation_index": 1,
                    "parent_refs": [{"candidate_id": "user-root"}],
                    "candidate_refs": [{"candidate_id": "user-child"}],
                    "survivor_refs": [{"candidate_id": "user-child"}],
                    "archive_refs": [{"candidate_id": "user-child"}],
                },
            ],
        }

        rows = lineage_plot_data(evolution)

        self.assertEqual(rows[1]["candidate_id"], "user-child")
        self.assertEqual(rows[1]["parent_candidate_id"], "user-root")
        self.assertEqual(rows[1]["generation"], 1)

    def test_comparison_plot_data_consumes_comparison_result_with_display_alias(self) -> None:
        collection_a = AnalysisResultCollection.from_records([_result("candidate-a", frontier=False, generation=0)])
        collection_b = AnalysisResultCollection.from_records([_result("candidate-b", frontier=True, generation=1)])
        comparison = compare_analysis_collections(
            (
                ComparisonSource("source-a", collection_a),
                ComparisonSource("source-b", collection_b),
            ),
            config=ComparisonConfig(
                comparison_id="viz-comparison",
                display_aliases={"candidate-b": "Candidate B"},
                validate_cost=False,
            ),
        )

        rows = comparison_plot_data(comparison)

        self.assertEqual(rows[1]["candidate_id"], "candidate-b")
        self.assertEqual(rows[1]["display_label"], "Candidate B")
        self.assertTrue(rows[1]["is_global_pareto"])

    def test_plot_functions_raise_clear_error_when_matplotlib_missing(self) -> None:
        collection = AnalysisResultCollection.from_records(
            [_result("candidate-a", frontier=True, generation=0)],
        )
        ranking = rank_analysis_results(collection)

        with mock.patch("importlib.util.find_spec", return_value=None):
            with self.assertRaises(VisualizationDependencyError):
                plot_pareto_front(collection)
            with self.assertRaises(VisualizationDependencyError):
                plot_ranking_scores(ranking)

    def test_plot_functions_and_export_work_when_matplotlib_available(self) -> None:
        if not optional_dependency_available("matplotlib"):
            self.skipTest("Matplotlib is not installed.")
        collection_a = AnalysisResultCollection.from_records([_result("candidate-a", frontier=False, generation=0)])
        collection_b = AnalysisResultCollection.from_records([_result("candidate-b", frontier=True, generation=1)])
        comparison = compare_analysis_collections(
            (
                ComparisonSource("source-a", collection_a),
                ComparisonSource("source-b", collection_b),
            ),
            config=ComparisonConfig(comparison_id="viz-comparison", validate_cost=False),
        )
        evolution = {
            "schema_version": "verfeinert.evolution_run.v1",
            "evolution_run_id": "viz-evolution",
            "generations": [
                {
                    "generation_index": 0,
                    "candidate_refs": [{"candidate_id": "candidate-a"}],
                    "survivor_refs": [{"candidate_id": "candidate-a"}],
                    "archive_refs": [{"candidate_id": "candidate-a"}],
                },
            ],
        }

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            figure = plot_comparison_objective_space(comparison)
            saved = save_figure(
                figure,
                tmp_path / "figures" / "comparison.png",
                config=FigureExportConfig(dpi=120),
            )
            lineage_figure = plot_lineage_summary(evolution)
            lineage_saved = save_figure(lineage_figure, tmp_path / "figures" / "lineage.png")

            self.assertTrue(saved.is_file())
            self.assertTrue(lineage_saved.is_file())
            self.assertEqual(figure.axes[0].get_xlabel().splitlines()[0], "Trainability")
            self.assertEqual(figure.axes[0].get_ylabel().splitlines()[0], "Expressibility")

    def test_save_figure_uses_guarded_caller_output_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_root = tmp_path / "inputs"
            input_root.mkdir()
            target = tmp_path / "outputs" / "plot.png"

            written = save_figure(_DummyFigure(), target, input_roots=(input_root,))

            self.assertEqual(written.name, "plot.png")
            self.assertTrue(written.is_file())


if __name__ == "__main__":
    unittest.main()
