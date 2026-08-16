"""Structural golden tests for evolution publication visualizations."""

from __future__ import annotations

import importlib.util

import pytest


_HAS_MATPLOTLIB = importlib.util.find_spec("matplotlib") is not None

pytestmark = pytest.mark.skipif(
    not _HAS_MATPLOTLIB,
    reason="matplotlib is not installed",
)

if _HAS_MATPLOTLIB:
    import matplotlib

    matplotlib.use("Agg")
    from matplotlib import pyplot
    from matplotlib.colors import to_hex
else:
    pyplot = None
    to_hex = None

from verfeinert.ansatz_analyzer.visualization import (
    BarSeries,
    LineageBarPanelSpec,
    MetricPanelSpec,
    MetricSeries,
    ObjectivePoint,
    ObjectiveSeries,
    TableSpec,
    plot_evolution_by_layer,
    plot_evolution_ranking_table,
    plot_final_frontier_vs_eligible,
    plot_frontier_evolution,
    plot_frontier_generation_comparison,
    plot_generation_candidate_counts,
    plot_generation_metric_grid,
    plot_lineage_evolution,
)


def _point(
    candidate_id: str,
    x: float,
    y: float,
    *,
    role: str = "candidate",
    layer: int | None = None,
) -> ObjectivePoint:
    return ObjectivePoint(candidate_id=candidate_id, x=x, y=y, role=role, layer=layer)


def _series(label: str, points: tuple[ObjectivePoint, ...], *, role: str = "series") -> ObjectiveSeries:
    return ObjectiveSeries(points=points, role=role, label=label)


def _metric(label: str, y: tuple[float, ...]) -> MetricSeries:
    return MetricSeries(x=(0, 1, 2), y=y, label=label, role="threshold")


def _assert_size(figure, expected: tuple[float, float]) -> None:
    width, height = figure.get_size_inches()
    assert (round(float(width), 2), round(float(height), 2)) == expected


def _coords(collection) -> list[tuple[float, float]]:
    return [(float(x), float(y)) for x, y in collection.get_offsets()]


def _metric_panels(suffix: str) -> tuple[MetricPanelSpec, ...]:
    return (
        MetricPanelSpec(f"Combined score {suffix}", "Combined score", (_metric("0.1", (1.0, 1.1, 1.2)), _metric("0.2", (1.3, 1.4, 1.5)))),
        MetricPanelSpec(f"Expressibility {suffix}", "Expressibility", (_metric("0.1", (2.0, 2.1, 2.2)), _metric("0.2", (2.3, 2.4, 2.5)))),
        MetricPanelSpec(f"Trainability {suffix}", "Trainability", (_metric("0.1", (3.0, 3.1, 3.2)), _metric("0.2", (3.3, 3.4, 3.5)))),
        MetricPanelSpec(f"Structural cost {suffix}", "Structural cost", (_metric("0.1", (4.0, 4.1, 4.2)), _metric("0.2", (4.3, 4.4, 4.5)))),
    )


def test_e1_generation_candidate_counts_uses_two_panel_layout_and_shared_legend() -> None:
    figure = plot_generation_candidate_counts(
        (_metric("0.1", (3, 5, 8)), _metric("0.2", (2, 4, 7))),
        (_metric("0.1", (1, 2, 3)), _metric("0.2", (1, 1, 2))),
    )

    _assert_size(figure, (13.0, 5.2))
    assert len(figure.axes) == 2
    assert [axis.get_title() for axis in figure.axes] == ["Generated candidates", "Selected candidates"]
    assert list(figure.axes[0].lines[0].get_xdata()) == [0, 1, 2]
    assert list(figure.axes[0].lines[0].get_ydata()) == [3.0, 5.0, 8.0]
    assert [text.get_text() for text in figure.legends[0].get_texts()] == ["0.1", "0.2"]
    pyplot.close(figure)


def test_e2_generation_metric_grid_total_population_contract() -> None:
    figure = plot_generation_metric_grid(_metric_panels("total"))

    _assert_size(figure, (8.0, 4.5))
    assert len(figure.axes) == 4
    assert [axis.get_title() for axis in figure.axes] == [
        "Combined score total",
        "Expressibility total",
        "Trainability total",
        "Structural cost total",
    ]
    assert list(figure.axes[0].lines[1].get_ydata()) == [1.3, 1.4, 1.5]
    assert [text.get_text() for text in figure.legends[0].get_texts()] == ["0.1", "0.2"]
    pyplot.close(figure)


def test_e3_generation_metric_grid_generation_local_pareto_contract() -> None:
    figure = plot_generation_metric_grid(_metric_panels("local Pareto"))

    assert len(figure.axes) == 4
    assert figure.axes[1].get_ylabel() == "Expressibility"
    assert list(figure.axes[2].lines[0].get_xdata()) == [0, 1, 2]
    assert list(figure.axes[2].lines[0].get_ydata()) == [3.0, 3.1, 3.2]
    pyplot.close(figure)


def test_e4_generation_metric_grid_optimized_frontier_contract() -> None:
    figure = plot_generation_metric_grid(_metric_panels("optimized frontier"))

    assert len(figure.axes) == 4
    assert figure.axes[3].get_ylabel() == "Structural cost"
    assert list(figure.axes[3].lines[1].get_ydata()) == [4.3, 4.4, 4.5]
    pyplot.close(figure)


def test_e5_frontier_evolution_preserves_prepared_generation_order() -> None:
    frontiers = (
        _series("generation 0", (_point("g0a", 0.1, 1.0), _point("g0b", 0.2, 1.1))),
        _series("generation 1", (_point("g1a", 0.3, 1.4), _point("g1b", 0.5, 1.8))),
    )

    figure = plot_frontier_evolution(frontiers, 0.2)
    axis = figure.axes[0]

    _assert_size(figure, (8.0, 4.5))
    assert len(axis.lines) == 2
    assert list(axis.lines[1].get_xdata()) == [0.3, 0.5]
    assert list(axis.lines[1].get_ydata()) == [1.4, 1.8]
    assert axis.get_title() == ""
    pyplot.close(figure)


def test_e6_frontier_generation_comparison_uses_preclassified_improvement_points() -> None:
    previous = _series("previous", (_point("p1", 0.1, 1.0), _point("p2", 0.2, 1.1)))
    current = _series("current", (_point("c1", 0.3, 1.3), _point("c2", 0.4, 1.6)))
    reference = _series("reference", (_point("r1", 0.0, 0.9), _point("r2", 0.25, 1.2)))
    improvements = _series(
        "improvements",
        (
            _point("e", 0.35, 1.5, role="expressibility_improvement"),
            _point("n", 0.45, 1.8, role="new_pareto"),
        ),
    )

    figure = plot_frontier_generation_comparison(previous, current, improvements, reference_frontier=reference, generation=2)

    _assert_size(figure, (8.0, 4.5))
    assert len(figure.axes) == 2
    assert [axis.get_title() for axis in figure.axes] == ["Previous frontier", "Generation 2"]
    assert len(figure.axes[0].lines) == 2
    assert len(figure.axes[1].collections) == 2
    assert _coords(figure.axes[1].collections[0]) == [(0.35, 1.5)]
    assert _coords(figure.axes[1].collections[1]) == [(0.45, 1.8)]
    assert figure.axes[1].collections[1].get_sizes()[0] == 78
    pyplot.close(figure)


def test_e7_final_frontier_vs_eligible_draws_only_prepared_background_and_frontier() -> None:
    eligible = _series("eligible", (_point("e1", 0.1, 1.0), _point("e2", 0.2, 1.2)))
    frontier = _series("final frontier", (_point("f1", 0.3, 1.5), _point("f2", 0.4, 1.7)))

    figure = plot_final_frontier_vs_eligible(eligible, frontier, 0.2)
    axis = figure.axes[0]

    _assert_size(figure, (8.0, 4.5))
    assert len(axis.collections) == 1
    assert _coords(axis.collections[0]) == [(0.1, 1.0), (0.2, 1.2)]
    assert len(axis.lines) == 1
    assert list(axis.lines[0].get_xdata()) == [0.3, 0.4]
    assert axis.get_title() == ""
    pyplot.close(figure)


def test_e8_evolution_by_layer_preserves_layer_semantics_and_final_frontiers() -> None:
    candidates = _series(
        "layers",
        (
            _point("l1", 0.1, 1.0, layer=1),
            _point("l2", 0.2, 1.2, layer=2),
            _point("l1b", 0.3, 1.4, layer=1),
        ),
    )
    frontier = _series("final 0.2", (_point("f1", 0.4, 1.5), _point("f2", 0.5, 1.8)))

    figure = plot_evolution_by_layer(candidates, (frontier,), layer_order=(2, 1))
    axis = figure.axes[0]

    _assert_size(figure, (8.0, 4.5))
    assert _coords(axis.collections[0]) == [(0.2, 1.2)]
    assert _coords(axis.collections[1]) == [(0.1, 1.0), (0.3, 1.4)]
    assert len(axis.lines) == 1
    assert axis.lines[0].get_linewidth() == 1.55
    pyplot.close(figure)


def test_e9_lineage_evolution_uses_three_prepared_panels_without_reordering() -> None:
    lineage_order = ("l-b", "l-a")
    panels = (
        LineageBarPanelSpec("Children", BarSeries(categories=lineage_order, values=(3, 2), label="Children")),
        LineageBarPanelSpec("Generation Pareto", BarSeries(categories=lineage_order, values=(1, 4), label="Generation Pareto")),
        LineageBarPanelSpec("New Pareto", BarSeries(categories=lineage_order, values=(0, 2), label="New Pareto")),
    )

    figure = plot_lineage_evolution(panels, lineage_order, 0.2)

    _assert_size(figure, (17.0, 5.8))
    assert len(figure.axes) == 3
    assert [axis.get_title() for axis in figure.axes] == ["Children", "Generation Pareto", "New Pareto"]
    assert [tick.get_text() for tick in figure.axes[0].get_xticklabels()] == list(lineage_order)
    assert [bar.get_height() for bar in figure.axes[1].patches] == [1.0, 4.0]
    pyplot.close(figure)


def test_e10_evolution_publication_table_uses_dynamic_geometry_and_row_order() -> None:
    table = TableSpec(
        columns=("candidate_id", "score"),
        rows=(("candidate-b", 0.2), ("candidate-a", 0.1), ("candidate-c", 0.3)),
    )

    figure = plot_evolution_ranking_table(table)
    axis = figure.axes[0]
    table_artist = axis.tables[0]

    _assert_size(figure, (15.5, 4.0))
    assert axis.axison is False
    assert table_artist.get_celld()[(1, 0)].get_text().get_text() == "candidate-b"
    assert table_artist.get_celld()[(2, 0)].get_text().get_text() == "candidate-a"
    assert table_artist.get_celld()[(3, 0)].get_text().get_text() == "candidate-c"
    pyplot.close(figure)
