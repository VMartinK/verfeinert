"""Phase 5.7 tests for optional visualization boundaries."""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from verfeinert.ansatz_analyzer import AnalysisResultCollection
from verfeinert.ansatz_analyzer.ranking import rank_analysis_results
from verfeinert.ansatz_analyzer.visualization import (
    THESIS_STYLE,
    VisualizationDependencyError,
    pareto_plot_data,
    plot_pareto_front,
    plot_ranking_scores,
    ranking_plot_data,
    save_figure,
)
from verfeinert.ansatz_analyzer.visualization.evolution import evolution_plot_data
from verfeinert.ansatz_analyzer.visualization.lineage import lineage_plot_data
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
            },
            {
                "metric_id": f"metric-trainability-{candidate_id}",
                "name": "trainability",
                "status": "computed",
                "value": 0.8 if frontier else 0.4,
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
            "generation": generation,
            "lineage": {
                "generation": generation,
                "root_candidate_id": "candidate-root",
                "parent_candidate_id": None if generation == 0 else "candidate-root",
            },
        },
    }


class _DummyFigure:
    def savefig(self, path, **_kwargs):
        Path(path).write_text("figure", encoding="utf-8")


class AnalyzerPhase57VisualizationTests(unittest.TestCase):
    def test_thesis_style_is_centralized_and_json_safe(self) -> None:
        payload = THESIS_STYLE.to_dict()

        self.assertIn("palette", payload)
        self.assertIn("frontier", payload["palette"])
        self.assertEqual(payload["export_format"], "png")

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

    def test_plot_functions_raise_clear_error_when_matplotlib_missing(self) -> None:
        if optional_dependency_available("matplotlib"):
            self.skipTest("Matplotlib is installed; missing-dependency behavior is not active.")
        collection = AnalysisResultCollection.from_records(
            [_result("candidate-a", frontier=True, generation=0)],
        )
        ranking = rank_analysis_results(collection)

        with self.assertRaises(VisualizationDependencyError):
            plot_pareto_front(collection)
        with self.assertRaises(VisualizationDependencyError):
            plot_ranking_scores(ranking)

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
