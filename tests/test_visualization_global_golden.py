"""Structural golden tests for global publication visualizations."""

from __future__ import annotations

import pytest

matplotlib = pytest.importorskip("matplotlib")
matplotlib.use("Agg")
from matplotlib import pyplot
from matplotlib.colors import to_hex

from verfeinert.ansatz_analyzer.visualization import (
    BarSeries,
    ObjectivePoint,
    ObjectiveSeries,
    TableSpec,
    ordered_lineage_color_map,
    plot_campaign_frontiers,
    plot_global_aggregate_metric,
    plot_global_contributions,
    plot_global_cost_eligibility,
    plot_global_lineages,
    plot_global_pareto,
    plot_global_pareto_score_map,
    plot_global_ranking_table,
)


def _point(
    candidate_id: str,
    x: float,
    y: float,
    *,
    role: str = "candidate",
    layer: int | None = None,
    lineage_id: str | None = None,
    score: float | None = None,
) -> ObjectivePoint:
    return ObjectivePoint(
        candidate_id=candidate_id,
        x=x,
        y=y,
        role=role,
        layer=layer,
        lineage_id=lineage_id,
        score=score,
    )


def _series(label: str, points: tuple[ObjectivePoint, ...], *, role: str = "series") -> ObjectiveSeries:
    return ObjectiveSeries(points=points, role=role, label=label)


def _assert_size(figure, expected: tuple[float, float]) -> None:
    width, height = figure.get_size_inches()
    assert (round(float(width), 2), round(float(height), 2)) == expected


def _coords(collection) -> list[tuple[float, float]]:
    return [(float(x), float(y)) for x, y in collection.get_offsets()]


def test_g_a_global_cost_eligibility_grouped_bars_preserve_campaign_order() -> None:
    categories = ("campaign-b", "campaign-a", "reference")
    bars = (
        BarSeries(categories=categories, values=(3, 5, 2), label="0.1"),
        BarSeries(categories=categories, values=(4, 6, 3), label="0.2"),
    )

    figure = plot_global_cost_eligibility(bars)
    axis = figure.axes[0]

    _assert_size(figure, (12.8, 7.2))
    assert len(axis.patches) == 6
    assert [patch.get_height() for patch in axis.patches[:3]] == [3.0, 5.0, 2.0]
    assert [tick.get_text() for tick in axis.get_xticklabels()] == list(categories)
    assert axis.get_xticklabels()[0].get_rotation() == 45
    assert axis.get_ylabel() == "Eligible circuits"
    assert [text.get_text() for text in axis.get_legend().get_texts()] == ["0.1", "0.2"]
    pyplot.close(figure)


def test_g_b_global_pareto_overview_draws_layers_and_global_frontiers_only() -> None:
    eligible = _series(
        "eligible",
        (
            _point("l2", 0.2, 1.1, layer=2),
            _point("l1", 0.1, 1.0, layer=1),
            _point("l2b", 0.3, 1.3, layer=2),
        ),
    )
    frontiers = (
        _series("global 0.1", (_point("g1", 0.4, 1.5), _point("g2", 0.5, 1.8))),
        _series("global 0.2", (_point("g3", 0.45, 1.7), _point("g4", 0.6, 2.0))),
    )

    figure = plot_global_pareto(eligible, frontiers, layer_order=(2, 1))
    axis = figure.axes[0]

    _assert_size(figure, (12.8, 7.2))
    assert len(axis.collections) == 2
    assert _coords(axis.collections[0]) == [(0.2, 1.1), (0.3, 1.3)]
    assert len(axis.lines) == 2
    assert axis.lines[0].get_marker() == "o"
    assert axis.lines[0].get_markersize() == 4.2
    assert axis.lines[0].get_linewidth() == 2.0
    pyplot.close(figure)


def test_g_c_campaign_frontiers_include_reference_global_overlay_and_score_colorbar() -> None:
    campaigns = (
        _series("campaign-a", (_point("a1", 0.1, 1.0), _point("a2", 0.2, 1.2)), role="campaign"),
        _series("baseline", (_point("b1", 0.1, 0.9), _point("b2", 0.25, 1.1)), role="reference"),
    )
    global_frontier = _series("global optimized", (_point("g1", 0.3, 1.5), _point("g2", 0.4, 1.8)))
    scores = _series("Prepared score", (_point("s1", 0.2, 1.4, score=0.6), _point("s2", 0.35, 1.7, score=0.9)))

    figure = plot_campaign_frontiers(campaigns, global_frontier, 0.2, score_points=scores)
    axis = figure.axes[0]

    _assert_size(figure, (13.6, 7.65))
    assert len(figure.axes) == 2
    assert figure._verfeinert_colorbar is not None
    assert len(axis.lines) == 3
    assert axis.lines[0].get_linestyle() == "-"
    assert axis.lines[1].get_linestyle() == "--"
    assert axis.lines[2].get_color() == "#000000"
    assert axis.lines[2].get_linewidth() == 2.6
    assert len(axis.collections) == 2
    assert axis.collections[-1].get_sizes()[0] == 28
    assert [text.get_text() for text in axis.get_legend().get_texts()] == [
        "Prepared score",
        "campaign-a",
        "baseline",
        "global optimized",
    ]
    pyplot.close(figure)


def test_g_d_global_pareto_score_map_uses_prepared_roles_and_score_values() -> None:
    background = _series("non-Pareto", (_point("b1", 0.1, 1.0), _point("b2", 0.2, 1.1)))
    campaign_pareto = _series("campaign Pareto", (_point("p1", 0.3, 1.5, score=0.2), _point("p2", 0.4, 1.7, score=0.8)))
    reference = _series("baseline frontier", (_point("r1", 0.1, 0.9), _point("r2", 0.25, 1.2)))
    global_frontier = _series("global optimized", (_point("g1", 0.3, 1.6), _point("g2", 0.5, 2.0)))
    global_members = _series("global members", (_point("m1", 0.3, 1.6), _point("m2", 0.5, 2.0)))

    figure = plot_global_pareto_score_map(
        background,
        campaign_pareto,
        global_frontier,
        global_members,
        threshold=0.2,
        reference_frontier=reference,
    )
    axis = figure.axes[0]

    _assert_size(figure, (13.6, 7.65))
    assert len(figure.axes) == 2
    assert len(axis.collections) == 3
    assert axis.collections[0].get_sizes()[0] == 18
    assert axis.collections[1].get_sizes()[0] == 38
    assert axis.collections[2].get_sizes()[0] == 28
    assert len(axis.lines) == 2
    assert axis.lines[0].get_linestyle() == "--"
    assert axis.lines[1].get_color() == "#000000"
    pyplot.close(figure)


def test_g_e_global_aggregate_metric_grouped_bars_preserve_threshold_order() -> None:
    categories = ("campaign-b", "campaign-a")
    bars = (
        BarSeries(categories=categories, values=(0.6, 0.8), label="0.1"),
        BarSeries(categories=categories, values=(0.7, 0.9), label="0.2"),
    )

    figure = plot_global_aggregate_metric(bars, y_label="Combined score")
    axis = figure.axes[0]

    _assert_size(figure, (12.8, 7.2))
    assert [patch.get_height() for patch in axis.patches] == [0.6, 0.8, 0.7, 0.9]
    assert [tick.get_text() for tick in axis.get_xticklabels()] == list(categories)
    assert axis.get_ylabel() == "Combined score"
    pyplot.close(figure)


def test_g_e2_global_population_aggregate_metric_uses_same_renderer_contract() -> None:
    categories = ("campaign-b", "campaign-a")
    bars = (
        BarSeries(categories=categories, values=(2.0, 3.0), label="0.1"),
        BarSeries(categories=categories, values=(4.0, 5.0), label="0.2"),
    )

    figure = plot_global_aggregate_metric(bars, y_label="Population frontier size")
    axis = figure.axes[0]

    assert [patch.get_height() for patch in axis.patches] == [2.0, 3.0, 4.0, 5.0]
    assert axis.get_ylabel() == "Population frontier size"
    assert [text.get_text() for text in axis.get_legend().get_texts()] == ["0.1", "0.2"]
    pyplot.close(figure)


def test_g_g_global_contributions_use_two_shared_x_panels_with_independent_y_labels() -> None:
    categories = ("campaign-b", "campaign-a")
    campaign = (
        BarSeries(categories=categories, values=(2, 4), label="0.1"),
        BarSeries(categories=categories, values=(3, 5), label="0.2"),
    )
    global_members = (
        BarSeries(categories=categories, values=(1, 2), label="0.1"),
        BarSeries(categories=categories, values=(2, 3), label="0.2"),
    )

    figure = plot_global_contributions(campaign, global_members)
    axes = figure.axes

    _assert_size(figure, (16.0, 9.0))
    assert len(axes) == 2
    assert axes[0].get_shared_x_axes().joined(axes[0], axes[1])
    assert axes[0].get_ylabel() == "Campaign frontier members"
    assert axes[1].get_ylabel() == "Global optimized frontier members"
    assert axes[0].get_xticklabels()[0].get_rotation() == 48
    assert [patch.get_height() for patch in axes[1].patches] == [1.0, 2.0, 2.0, 3.0]
    pyplot.close(figure)


def test_g_h_global_lineages_preserves_lineage_order_and_prepared_counts() -> None:
    lineage_order = ("lineage-b", "lineage-a", "lineage-c")
    eligible = BarSeries(categories=lineage_order, values=(8, 5, 3), label="Eligible")
    campaign = BarSeries(categories=lineage_order, values=(3, 1, 2), label="Campaign")
    global_counts = BarSeries(categories=lineage_order, values=(1, 0, 2), label="Global")
    points = _series(
        "selected lineages",
        (
            _point("b1", 0.1, 1.0, lineage_id="lineage-b"),
            _point("a1", 0.2, 1.2, lineage_id="lineage-a"),
            _point("c1", 0.3, 1.4, lineage_id="lineage-c"),
        ),
    )
    frontier = _series("global optimized", (_point("g1", 0.2, 1.5), _point("g2", 0.5, 2.0)))
    expected_colors = ordered_lineage_color_map(lineage_order)

    figure = plot_global_lineages(lineage_order, eligible, campaign, global_counts, points, frontier, threshold=0.2)
    left_axis, right_axis = figure.axes

    _assert_size(figure, (18.0, 9.5))
    assert len(left_axis.patches) == 6
    assert [patch.get_width() for patch in left_axis.patches[:3]] == [8.0, 5.0, 3.0]
    assert [tick.get_text() for tick in left_axis.get_yticklabels()] == list(lineage_order)
    assert [text.get_text() for text in left_axis.texts] == ["1", "0", "2"]
    assert to_hex(left_axis.patches[0].get_facecolor()) == expected_colors["lineage-b"].lower()
    assert len(right_axis.collections) == 3
    assert _coords(right_axis.collections[0]) == [(0.1, 1.0)]
    assert len(right_axis.lines) == 1
    assert right_axis.lines[0].get_linewidth() == 2.2
    pyplot.close(figure)


def test_g_i_global_publication_table_uses_geometry_and_preserves_prepared_row_order() -> None:
    table = TableSpec(
        columns=("rank", "candidate_id"),
        rows=((2, "candidate-b"), (1, "candidate-a"), (3, "candidate-c")),
    )

    figure = plot_global_ranking_table(table)
    axis = figure.axes[0]
    table_artist = axis.tables[0]

    _assert_size(figure, (15.5, 4.0))
    assert table_artist.get_celld()[(1, 1)].get_text().get_text() == "candidate-b"
    assert table_artist.get_celld()[(2, 1)].get_text().get_text() == "candidate-a"
    assert table_artist.get_celld()[(3, 1)].get_text().get_text() == "candidate-c"
    pyplot.close(figure)
