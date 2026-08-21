"""Structural golden tests for individual publication visualizations."""

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
    ObjectivePoint,
    ObjectiveSeries,
    PUBLICATION_LEGEND_ZORDER,
    ordered_lineage_color_map,
    plot_individual_by_layer,
    plot_individual_by_lineage,
    plot_individual_classification,
    plot_individual_frontier_comparison,
    plot_individual_joint_frontiers,
    plot_individual_pareto_by_lineage,
)


def _point(
    candidate_id: str,
    x: float,
    y: float,
    *,
    role: str = "candidate",
    layer: int | None = None,
    lineage_id: str | None = None,
) -> ObjectivePoint:
    return ObjectivePoint(
        candidate_id=candidate_id,
        x=x,
        y=y,
        role=role,
        layer=layer,
        lineage_id=lineage_id,
    )


def _series(label: str, points: tuple[ObjectivePoint, ...], *, role: str = "series") -> ObjectiveSeries:
    return ObjectiveSeries(points=points, role=role, label=label)


def _coords(collection) -> list[tuple[float, float]]:
    return [(float(x), float(y)) for x, y in collection.get_offsets()]


def _legend_labels(axis) -> list[str]:
    legend = axis.get_legend()
    return [text.get_text() for text in legend.get_texts()]


def _assert_size(figure, expected: tuple[float, float]) -> None:
    width, height = figure.get_size_inches()
    assert (round(float(width), 2), round(float(height), 2)) == expected


def _assert_publication_legend(legend) -> None:
    assert legend.get_zorder() >= PUBLICATION_LEGEND_ZORDER
    frame = legend.get_frame()
    assert frame.get_alpha() == 1.0


def test_i1_individual_classification_structural_contract() -> None:
    reference = _series("eligible reference", (_point("r1", 0.1, 1.0), _point("r2", 0.2, 1.2)))
    reference_frontier = _series("reference frontier", (_point("rf1", 0.1, 1.0), _point("rf2", 0.3, 1.4)))
    candidates = _series(
        "classified",
        (
            _point("d", 0.05, 0.8, role="discarded"),
            _point("e", 0.15, 1.5, role="expressibility_improvement"),
            _point("t", 0.35, 1.1, role="trainability_improvement"),
            _point("p", 0.45, 1.7, role="new_pareto"),
        ),
    )

    figure = plot_individual_classification(reference, reference_frontier, candidates, 0.2)
    axis = figure.axes[0]

    _assert_size(figure, (8.0, 4.5))
    assert len(figure.axes) == 1
    assert len(axis.collections) == 6
    assert len(axis.lines) == 1
    assert _coords(axis.collections[0]) == [(0.1, 1.0), (0.2, 1.2)]
    assert axis.collections[-1].get_sizes()[0] == 78
    assert to_hex(axis.collections[-1].get_facecolors()[0]) == "#f1c40f"
    assert _legend_labels(axis) == [
        "reference frontier",
        "discard",
        "eligible reference",
        "expressibility improvement",
        "trainability improvement",
        "new Pareto optimal",
    ]
    _assert_publication_legend(axis.get_legend())
    assert axis.get_title() == ""
    pyplot.close(figure)


def test_i2_individual_joint_frontiers_preserves_frontier_order_and_limits() -> None:
    frontiers = (
        _series("t0", (_point("a", 0.1, 1.0), _point("b", 0.2, 1.4))),
        _series("t1", (_point("c", 0.3, 1.1), _point("d", 0.4, 1.8))),
        _series("t2", (_point("e", 0.5, 1.3), _point("f", 0.6, 2.0))),
    )

    figure = plot_individual_joint_frontiers(frontiers, xlim=(0.0, 1.0), ylim=(0.5, 2.5))
    axis = figure.axes[0]

    _assert_size(figure, (8.0, 4.5))
    assert len(axis.lines) == 3
    assert list(axis.lines[1].get_xdata()) == [0.3, 0.4]
    assert list(axis.lines[1].get_ydata()) == [1.1, 1.8]
    assert axis.lines[0].get_marker() == "o"
    assert axis.lines[0].get_markersize() == 5.0
    assert axis.lines[0].get_linewidth() == 1.9
    assert axis.get_xlim() == (0.0, 1.0)
    assert axis.get_ylim() == (0.5, 2.5)
    assert _legend_labels(axis) == ["t0", "t1", "t2"]
    _assert_publication_legend(axis.get_legend())
    assert axis.get_title() == ""
    pyplot.close(figure)


def test_i3_individual_frontier_comparison_uses_reference_and_primary_styles() -> None:
    reference_frontiers = (
        _series("reference 0.1", (_point("r1", 0.1, 1.0), _point("r2", 0.2, 1.1))),
        _series("reference 0.2", (_point("r3", 0.1, 1.2), _point("r4", 0.25, 1.4))),
    )
    primary_frontiers = (
        _series("optimized 0.1", (_point("p1", 0.3, 1.5), _point("p2", 0.4, 1.7))),
        _series("optimized 0.2", (_point("p3", 0.35, 1.6), _point("p4", 0.5, 2.0))),
    )

    figure = plot_individual_frontier_comparison(reference_frontiers, primary_frontiers)
    axis = figure.axes[0]

    _assert_size(figure, (8.0, 4.5))
    assert len(axis.lines) == 4
    assert axis.lines[0].get_linestyle() == "--"
    assert axis.lines[0].get_linewidth() == 1.45
    assert axis.lines[2].get_linestyle() == "-"
    assert axis.lines[2].get_linewidth() == 2.05
    assert axis.get_legend()._ncols == 2
    assert _legend_labels(axis) == ["reference 0.1", "reference 0.2", "optimized 0.1", "optimized 0.2"]
    _assert_publication_legend(axis.get_legend())
    assert axis.get_title() == ""
    pyplot.close(figure)


def test_i4_individual_by_layer_preserves_prepared_layer_order() -> None:
    candidates = _series(
        "layers",
        (
            _point("l2a", 0.2, 1.0, layer=2),
            _point("l1a", 0.1, 1.1, layer=1),
            _point("l2b", 0.3, 1.3, layer=2),
        ),
    )
    reference_frontier = _series("reference frontier", (_point("r1", 0.0, 0.8), _point("r2", 0.4, 1.5)))

    figure = plot_individual_by_layer(candidates, (reference_frontier,), layer_order=(2, 1))
    axis = figure.axes[0]

    _assert_size(figure, (8.0, 4.5))
    assert len(axis.collections) == 2
    assert _coords(axis.collections[0]) == [(0.2, 1.0), (0.3, 1.3)]
    assert _coords(axis.collections[1]) == [(0.1, 1.1)]
    assert len(axis.lines) == 1
    assert axis.lines[0].get_linewidth() == 1.55
    _assert_publication_legend(axis.get_legend())
    assert axis.get_legend()._ncols == 2
    assert axis.get_title() == ""
    pyplot.close(figure)


def test_i5_individual_by_lineage_uses_prepared_order_and_reserves_legend_strip() -> None:
    lineage_order = tuple(f"lineage-{index}" for index in range(9))
    points = tuple(
        _point(f"candidate-{index}", index / 10.0, 1.0 + index / 10.0, lineage_id=lineage_id)
        for index, lineage_id in enumerate(lineage_order)
    )
    reference_frontier = _series("reference frontier", (_point("r1", 0.0, 0.8), _point("r2", 0.8, 1.9)))
    expected_colors = ordered_lineage_color_map(lineage_order)

    figure = plot_individual_by_lineage(_series("lineages", points), (reference_frontier,), lineage_order)
    axis = figure.axes[0]

    _assert_size(figure, (8.0, 4.5))
    assert len(axis.collections) == 9
    assert to_hex(axis.collections[0].get_facecolors()[0]) == expected_colors["lineage-0"].lower()
    assert axis.get_xlim()[1] > 0.8
    assert axis.get_legend()._ncols == 2
    assert [text.get_text() for text in axis.get_legend().get_texts()] == list(lineage_order)
    assert axis.artists
    assert [text.get_text() for text in axis.artists[0].get_texts()] == ["reference frontier"]
    _assert_publication_legend(axis.get_legend())
    _assert_publication_legend(axis.artists[0])
    assert axis.get_title() == ""
    pyplot.close(figure)


def test_i6_individual_pareto_by_lineage_uses_i5_lineage_colors_and_annotations() -> None:
    lineage_order = ("lineage-a", "lineage-b", "lineage-c")
    counts = BarSeries(categories=lineage_order, values=(2, 0, 4), label="Pareto")
    expected_colors = ordered_lineage_color_map(lineage_order)

    figure = plot_individual_pareto_by_lineage(counts, lineage_order=lineage_order)
    axis = figure.axes[0]

    _assert_size(figure, (8.0, 4.5))
    assert [bar.get_height() for bar in axis.patches] == [2.0, 0.0, 4.0]
    assert [tick.get_text() for tick in axis.get_xticklabels()] == list(lineage_order)
    assert axis.get_xlabel() == "Lineage ID"
    assert axis.get_ylabel() == "Number of Pareto-optimal candidates"
    assert axis.get_ylim() == (0.0, 4.75)
    assert [text.get_text() for text in axis.texts] == ["2", "0", "4"]
    assert [to_hex(bar.get_facecolor()) for bar in axis.patches] == [
        expected_colors["lineage-a"].lower(),
        expected_colors["lineage-b"].lower(),
        expected_colors["lineage-c"].lower(),
    ]
    assert axis.get_title() == ""
    assert axis.get_legend() is None
    pyplot.close(figure)
