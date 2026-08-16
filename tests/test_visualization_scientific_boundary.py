"""Scientific-boundary tests for publication visualization renderers."""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from verfeinert.ansatz_analyzer.visualization import (
    DEFAULT_STYLE,
    ObjectivePoint,
    ObjectiveSeries,
    TableSpec,
    plot_final_frontier_vs_eligible,
    plot_global_lineages,
    plot_publication_table,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
VISUALIZATION_ROOT = PROJECT_ROOT / "verfeinert" / "ansatz_analyzer" / "visualization"
SUITE_MODULES = (
    VISUALIZATION_ROOT / "individual.py",
    VISUALIZATION_ROOT / "evolution.py",
    VISUALIZATION_ROOT / "global_analysis.py",
)
FORBIDDEN_IMPORTS = {
    "numpy",
    "pandas",
    "pennylane",
    "notebook",
    "nbclient",
    "nbformat",
    "verfeinert.ansatz_analyzer.metrics",
    "verfeinert.ansatz_analyzer.pareto",
    "verfeinert.ansatz_analyzer.ranking",
    "verfeinert.ansatz_evolver",
}
FORBIDDEN_SCIENTIFIC_NAMES = {
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


def _point(candidate_id: str, x: float, y: float, *, lineage_id: str | None = None) -> ObjectivePoint:
    return ObjectivePoint(candidate_id=candidate_id, x=x, y=y, lineage_id=lineage_id)


def test_publication_renderers_do_not_import_metric_or_notebook_runtime_implementations() -> None:
    violations = []
    for path in SUITE_MODULES:
        for module in _imported_modules(path):
            if any(module == forbidden or module.startswith(f"{forbidden}.") for forbidden in FORBIDDEN_IMPORTS):
                violations.append(f"{path.relative_to(PROJECT_ROOT)} imports {module}")

    assert violations == []


def test_publication_renderers_do_not_reference_pareto_ranking_or_selection_internals() -> None:
    violations = []
    for path in SUITE_MODULES:
        for name in sorted(_referenced_names(path) & FORBIDDEN_SCIENTIFIC_NAMES):
            violations.append(f"{path.relative_to(PROJECT_ROOT)} references {name}")

    assert violations == []


def test_e7_final_frontier_vs_eligible_does_not_execute_dominance_or_pareto_logic(monkeypatch) -> None:
    matplotlib = pytest.importorskip("matplotlib")
    matplotlib.use("Agg")
    from matplotlib import pyplot
    from verfeinert.ansatz_analyzer import pareto

    def fail(*_args, **_kwargs):
        raise AssertionError("scientific Pareto logic must not be called by E7")

    monkeypatch.setattr(pareto, "dominates", fail)
    monkeypatch.setattr(pareto, "compute_pareto_classifications", fail)
    eligible = ObjectiveSeries(points=(_point("eligible-a", 0.1, 1.0),), label="eligible")
    frontier = ObjectiveSeries(points=(_point("frontier-a", 0.2, 1.2),), label="frontier")

    figure = plot_final_frontier_vs_eligible(eligible, frontier, 0.2)

    assert len(figure.axes[0].collections) == 1
    assert len(figure.axes[0].lines) == 1
    pyplot.close(figure)


def test_g_h_global_lineages_does_not_sort_or_select_top_lineages() -> None:
    source = inspect.getsource(plot_global_lineages)

    assert "sorted(" not in source
    assert ".sort(" not in source
    assert "top" not in source.lower()
    assert "groupby" not in source.lower()


def test_publication_table_renderer_preserves_prepared_row_order() -> None:
    matplotlib = pytest.importorskip("matplotlib")
    matplotlib.use("Agg")
    from matplotlib import pyplot

    table = TableSpec(
        columns=("candidate_id", "score"),
        rows=(("candidate-z", 0.3), ("candidate-a", 0.1), ("candidate-m", 0.2)),
    )

    figure = plot_publication_table(table)
    cells = figure.axes[0].tables[0].get_celld()

    assert cells[(1, 0)].get_text().get_text() == "candidate-z"
    assert cells[(2, 0)].get_text().get_text() == "candidate-a"
    assert cells[(3, 0)].get_text().get_text() == "candidate-m"
    pyplot.close(figure)


def test_scientific_threshold_numbers_are_explicit_data_not_default_style_mappings() -> None:
    payload = DEFAULT_STYLE.to_dict()
    forbidden_threshold_keys = {"1.0", "0.2", "0.1"}

    assert forbidden_threshold_keys & set(DEFAULT_STYLE.palette) == set()
    assert forbidden_threshold_keys & set(DEFAULT_STYLE.role_styles) == set()
    assert forbidden_threshold_keys & set(payload) == set()
