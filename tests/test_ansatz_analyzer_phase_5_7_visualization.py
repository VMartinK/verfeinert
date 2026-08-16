"""Phase 5.7 tests for optional visualization boundaries."""

from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from verfeinert.ansatz_analyzer import AnalysisResultCollection
from verfeinert.ansatz_analyzer.ranking import rank_analysis_results
from verfeinert.ansatz_analyzer.visualization import (
    BarSeries,
    DEFAULT_STYLE,
    FigureExportConfig,
    MetricSeries,
    ObjectivePoint,
    ObjectiveSeries,
    TableSpec,
    VisualizationDependencyError,
    VisualizationModelError,
    comparison_plot_data,
    pareto_plot_data,
    plot_comparison_objective_space,
    plot_lineage_summary,
    plot_pareto_front,
    plot_ranking_scores,
    ranking_plot_data,
    save_figure,
    save_publication_figure,
)
from verfeinert.ansatz_analyzer.visualization.evolution import evolution_plot_data
from verfeinert.ansatz_analyzer.visualization.lineage import lineage_plot_data
from verfeinert.ansatz_analyzer.comparison import ComparisonConfig, ComparisonSource, compare_analysis_collections
from verfeinert.ansatz_analyzer.metrics.runtime import optional_dependency_available
from verfeinert.core.io import PathValidationError


PROJECT_ROOT = Path(__file__).resolve().parents[1]
VISUALIZATION_ROOT = PROJECT_ROOT / "verfeinert" / "ansatz_analyzer" / "visualization"
FOUNDATION_VISUALIZATION_MODULES = (
    VISUALIZATION_ROOT / "models.py",
    VISUALIZATION_ROOT / "primitives.py",
    VISUALIZATION_ROOT / "export.py",
    VISUALIZATION_ROOT / "styles" / "default.py",
)
FORBIDDEN_FOUNDATION_IMPORTS = {
    "matplotlib",
    "notebook",
    "nbclient",
    "nbformat",
    "pennylane",
    "verfeinert.ansatz_analyzer.metrics",
    "verfeinert.ansatz_evolver",
}
FORBIDDEN_SCIENTIFIC_SYMBOLS = {
    "compute_pareto_classifications",
    "dominates",
    "non_dominated_ranks",
    "rank_analysis_results",
    "ranks_for_entries",
    "select_by_fitness",
    "select_by_thresholds",
    "select_multithreshold",
    "select_pareto_front",
    "select_strict_pareto",
    "select_strict_pareto_feedback",
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


def _referenced_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
    return names


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
    def __init__(self) -> None:
        self.calls: list[tuple[Path, dict]] = []

    def savefig(self, path, **kwargs):
        self.calls.append((Path(path), dict(kwargs)))
        Path(path).write_text("figure", encoding="utf-8")


class AnalyzerPhase57VisualizationTests(unittest.TestCase):
    def test_semantic_models_are_immutable_ordered_and_json_safe(self) -> None:
        point = ObjectivePoint(
            candidate_id="candidate-b",
            x=0.4,
            y=2.0,
            display_label="Candidate B",
            role="new_pareto",
            layer=2,
            lineage_id="lineage-user-supplied",
            generation=1,
            metadata={"nested": {"values": [1, 2]}},
        )
        series = ObjectiveSeries(points=(point,), role="observed", label="Observed")
        metric = MetricSeries(x=("g1", "g0"), y=(2.0, 1.0), role="input", threshold=0.5)
        bars = BarSeries(categories=("b", "a"), values=(3, 2), role="counts")
        table = TableSpec(
            columns=("candidate_id", "score"),
            rows=({"candidate_id": "candidate-b", "score": None}, ("candidate-a", 1.2)),
        )

        self.assertEqual(series.points[0].candidate_id, "candidate-b")
        self.assertEqual((series.points[0].x, series.points[0].y), (0.4, 2.0))
        self.assertEqual(metric.x, ("g1", "g0"))
        self.assertEqual(metric.y, (2.0, 1.0))
        self.assertEqual(bars.categories, ("b", "a"))
        self.assertEqual(table.columns, ("candidate_id", "score"))
        self.assertIsNone(point.score)
        self.assertIsNone(point.structural_cost)
        self.assertEqual(point.metadata["nested"]["values"], (1, 2))
        json.dumps(series.to_dict(), sort_keys=True)

        with self.assertRaises(FrozenInstanceError):
            point.x = 0.9  # type: ignore[misc]
        with self.assertRaises(TypeError):
            point.metadata["new"] = "value"  # type: ignore[index]
        with self.assertRaises(TypeError):
            point.metadata["nested"]["values"] = (3,)  # type: ignore[index]
        with self.assertRaises(VisualizationModelError):
            MetricSeries(x=(1,), y=(1.0, 2.0))

    def test_default_style_is_publication_grade_and_json_safe(self) -> None:
        payload = DEFAULT_STYLE.to_dict()

        self.assertEqual(DEFAULT_STYLE.figure_size, (8.0, 4.5))
        self.assertEqual(DEFAULT_STYLE.dpi, 600)
        self.assertEqual(DEFAULT_STYLE.frontier_colors, ("#C62828", "#1565C0", "#1B5E20"))
        self.assertEqual(DEFAULT_STYLE.reference_frontier_colors, ("#111111", "#666666", "#AAAAAA"))
        self.assertEqual(DEFAULT_STYLE.layer_colors, ("#E69F00", "#0072B2", "#009E73"))
        self.assertEqual(DEFAULT_STYLE.extra_layer_colors, ("#CC79A7", "#999999", "#D55E00", "#00796B"))
        self.assertEqual(DEFAULT_STYLE.point_marker, "o")
        self.assertEqual(DEFAULT_STYLE.grid_alpha, 0.18)
        self.assertEqual(DEFAULT_STYLE.legend_location, "upper right")
        self.assertTrue(DEFAULT_STYLE.legend_frame)
        self.assertEqual(DEFAULT_STYLE.legend_edgecolor, "#B0B0B0")
        self.assertEqual(DEFAULT_STYLE.legend_framealpha, 0.95)
        self.assertFalse(DEFAULT_STYLE.legend_fancybox)
        self.assertEqual(DEFAULT_STYLE.annotation_text_color, "0.15")
        self.assertEqual(DEFAULT_STYLE.bbox_inches, "tight")
        self.assertEqual(DEFAULT_STYLE.facecolor, "white")
        self.assertFalse(DEFAULT_STYLE.transparent)
        self.assertEqual(DEFAULT_STYLE.export_formats, ("png", "pdf", "svg"))
        self.assertEqual(DEFAULT_STYLE.publication_export_formats, ("png", "pdf", "svg"))
        self.assertEqual(DEFAULT_STYLE.layouts.standard, (8.0, 4.5))
        self.assertEqual(DEFAULT_STYLE.layouts.generation_counts, (13.0, 5.2))
        self.assertEqual(DEFAULT_STYLE.layouts.global_standard, (12.8, 7.2))
        self.assertEqual(DEFAULT_STYLE.layouts.global_wide, (13.6, 7.65))
        self.assertEqual(DEFAULT_STYLE.layouts.global_contribution, (16.0, 9.0))
        self.assertEqual(DEFAULT_STYLE.layouts.global_lineage, (18.0, 9.5))
        self.assertGreater(DEFAULT_STYLE.layouts.table_figure_size(12)[1], DEFAULT_STYLE.layouts.table_figure_size(2)[1])
        self.assertEqual(DEFAULT_STYLE.role_styles["discarded"].color, "#BDBDBD")
        self.assertEqual(DEFAULT_STYLE.role_styles["discarded"].marker, "o")
        self.assertEqual(DEFAULT_STYLE.role_styles["discarded"].size, 24)
        self.assertEqual(DEFAULT_STYLE.role_styles["discarded"].alpha, 0.32)
        self.assertEqual(DEFAULT_STYLE.role_styles["expressibility_improvement"].color, "#CC79A7")
        self.assertEqual(DEFAULT_STYLE.role_styles["trainability_improvement"].color, "#56B4E9")
        self.assertEqual(DEFAULT_STYLE.role_styles["frontier_improvement"].marker, "*")
        self.assertEqual(DEFAULT_STYLE.role_styles["frontier_improvement"].size, 78)
        self.assertEqual(DEFAULT_STYLE.role_styles["new_pareto"].color, "#F1C40F")
        self.assertIn("palette", payload)
        self.assertIn("frontier", payload["palette"])
        self.assertEqual(payload["export_formats"], ["png", "pdf", "svg"])
        self.assertEqual(payload["publication_export_formats"], ["png", "pdf", "svg"])
        self.assertEqual(payload["score_colormap"], "plasma")
        self.assertEqual(payload["export_format"], "png")
        self.assertEqual({"1.0", "0.2", "0.1"} & set(DEFAULT_STYLE.palette), set())
        self.assertEqual({"1.0", "0.2", "0.1"} & set(DEFAULT_STYLE.role_styles), set())
        json.dumps(payload, sort_keys=True)
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
            figure = _DummyFigure()

            written = save_figure(
                figure,
                target,
                config=FigureExportConfig(dpi=120),
                input_roots=(input_root,),
                transparent=True,
            )

            self.assertEqual(written.name, "plot.png")
            self.assertTrue(written.is_file())
            self.assertEqual(figure.calls[0][0], written)
            self.assertEqual(figure.calls[0][1]["dpi"], 120)
            self.assertTrue(figure.calls[0][1]["transparent"])

    def test_save_publication_figure_writes_default_formats_with_publication_options(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            figure = _DummyFigure()

            written = save_publication_figure(figure, tmp_path / "figures" / "foundation")

            self.assertEqual(tuple(written), ("png", "pdf", "svg"))
            self.assertEqual([path.name for path in written.values()], ["foundation.png", "foundation.pdf", "foundation.svg"])
            self.assertTrue(all(path.is_file() for path in written.values()))
            self.assertEqual([call[0] for call in figure.calls], list(written.values()))
            self.assertEqual([call[1]["format"] for call in figure.calls], ["png", "pdf", "svg"])
            for _path, options in figure.calls:
                self.assertEqual(options["dpi"], 600)
                self.assertEqual(options["bbox_inches"], "tight")
                self.assertEqual(options["facecolor"], "white")
                self.assertFalse(options["transparent"])

    def test_save_publication_figure_accepts_subset_and_normalizes_case(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            figure = _DummyFigure()

            written = save_publication_figure(
                figure,
                tmp_path / "figures" / "foundation",
                formats=("PDF", "svg"),
            )

            self.assertEqual(tuple(written), ("pdf", "svg"))
            self.assertEqual([path.name for path in written.values()], ["foundation.pdf", "foundation.svg"])
            self.assertFalse((tmp_path / "figures" / "foundation.png").exists())
            self.assertEqual([call[1]["format"] for call in figure.calls], ["pdf", "svg"])

    def test_save_publication_figure_uses_guarded_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_root = tmp_path / "inputs"
            input_root.mkdir()

            with self.assertRaises(PathValidationError):
                save_publication_figure(
                    _DummyFigure(),
                    input_root / "nested" / "foundation",
                    input_roots=(input_root,),
                )

    def test_save_publication_figure_fails_closed_on_collision_before_writing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            output_root = tmp_path / "figures"
            output_root.mkdir()
            existing = output_root / "foundation.png"
            existing.write_text("existing", encoding="utf-8")
            figure = _DummyFigure()

            with self.assertRaises(FileExistsError):
                save_publication_figure(figure, output_root / "foundation")

            self.assertEqual(figure.calls, [])
            self.assertEqual(existing.read_text(encoding="utf-8"), "existing")
            self.assertFalse((output_root / "foundation.pdf").exists())
            self.assertFalse((output_root / "foundation.svg").exists())

    def test_save_publication_figure_overwrite_true_replaces_existing_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            output_root = tmp_path / "figures"
            output_root.mkdir()
            existing = output_root / "foundation.png"
            existing.write_text("existing", encoding="utf-8")
            figure = _DummyFigure()

            written = save_publication_figure(figure, output_root / "foundation", overwrite=True)

            self.assertEqual(tuple(written), ("png", "pdf", "svg"))
            self.assertEqual(existing.read_text(encoding="utf-8"), "figure")
            self.assertEqual(len(figure.calls), 3)

    def test_save_publication_figure_rejects_malformed_duplicate_formats_and_extensions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            cases = (
                {"basename": tmp_path / "foundation.png"},
                {"formats": "png"},
                {"formats": ()},
                {"formats": ("png", "PNG")},
                {"formats": ("png", ".pdf")},
                {"formats": ("png", "bad format")},
                {"formats": ("png", "jpg")},
            )
            for kwargs in cases:
                figure = _DummyFigure()
                with self.subTest(kwargs=kwargs):
                    with self.assertRaises(ValueError):
                        save_publication_figure(
                            figure,
                            kwargs.get("basename", tmp_path / "foundation"),
                            formats=kwargs.get("formats", ("png", "pdf", "svg")),
                        )
                    self.assertEqual(figure.calls, [])

    def test_save_publication_figure_rejects_unsupported_formats_before_creating_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            output_root = tmp_path / "figures"
            figure = _DummyFigure()

            with self.assertRaises(ValueError):
                save_publication_figure(
                    figure,
                    output_root / "foundation",
                    formats=("png", "exe"),
                )

            self.assertEqual(figure.calls, [])
            self.assertFalse(output_root.exists())
            self.assertFalse((output_root / "foundation.png").exists())
            self.assertFalse((output_root / "foundation.exe").exists())

    def test_nonrendering_visualization_imports_work_without_matplotlib(self) -> None:
        code = r"""
import importlib.abc
import json
import sys


class BlockMatplotlib(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "matplotlib" or fullname.startswith("matplotlib."):
            raise ModuleNotFoundError(f"blocked optional dependency: {fullname}")
        return None


sys.meta_path.insert(0, BlockMatplotlib())

from verfeinert.ansatz_analyzer import AnalysisResultCollection
from verfeinert.ansatz_analyzer.visualization import ObjectivePoint, ObjectiveSeries, pareto_plot_data
from verfeinert.ansatz_analyzer.visualization.evolution import evolution_plot_data

collection = AnalysisResultCollection.from_records([])
point = ObjectivePoint(candidate_id="candidate-a", x=1.0, y=2.0, role="input")
series = ObjectiveSeries(points=(point,), role="input")
print(json.dumps({
    "candidate_id": series.points[0].candidate_id,
    "pareto_rows": pareto_plot_data(collection),
    "evolution_rows": evolution_plot_data(collection),
}, sort_keys=True))
"""
        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=PROJECT_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )

        payload = json.loads(result.stdout)
        self.assertEqual(payload["candidate_id"], "candidate-a")
        self.assertEqual(payload["pareto_rows"], [])
        self.assertEqual(payload["evolution_rows"], [])

    def test_visualization_foundation_modules_do_not_import_scientific_or_selection_internals(self) -> None:
        violations: list[str] = []
        for path in FOUNDATION_VISUALIZATION_MODULES:
            for module in _imported_modules(path):
                if any(
                    module == forbidden or module.startswith(f"{forbidden}.")
                    for forbidden in FORBIDDEN_FOUNDATION_IMPORTS
                ):
                    violations.append(f"{path.relative_to(PROJECT_ROOT)} imports {module}")
            for name in sorted(_referenced_names(path) & FORBIDDEN_SCIENTIFIC_SYMBOLS):
                violations.append(f"{path.relative_to(PROJECT_ROOT)} references {name}")

        self.assertEqual(violations, [])


if __name__ == "__main__":
    unittest.main()
