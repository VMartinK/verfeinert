"""Publication renderers for prepared global visualization data."""

from __future__ import annotations

from collections.abc import Sequence
import warnings
from typing import Any

from .export import require_pyplot
from .models import BarSeries, ObjectivePoint, ObjectiveSeries, TableSpec, VisualizationModelError
from .primitives import (
    PUBLICATION_OBJECTIVE_VERTICAL_HEADROOM_FRACTION,
    apply_bar_headroom,
    apply_objective_vertical_headroom,
    ordered_lineage_color_map,
    plot_publication_table,
    setup_publication_objective_axis,
    style_publication_legend,
)
from .styles import DEFAULT_STYLE, VisualizationStyle


def plot_global_cost_eligibility(
    eligibility: Sequence[BarSeries],
    *,
    style: VisualizationStyle = DEFAULT_STYLE,
):
    """Render prepared global cost-eligibility counts by campaign/source and threshold."""
    pyplot = require_pyplot()
    figure, axis = pyplot.subplots(figsize=style.layouts.global_standard, dpi=style.dpi)
    _plot_grouped_bars(axis, eligibility, style=style, rotation=45, ha="right")
    axis.set_ylabel("Eligible circuits")
    axis.set_axisbelow(True)
    axis.grid(axis="y", alpha=style.grid_alpha)
    _axis_legend(axis, style=style)
    return figure


def plot_global_pareto(
    eligible_by_layer: ObjectiveSeries,
    global_frontiers: Sequence[ObjectiveSeries],
    *,
    layer_order: Sequence[int] | None = None,
    x_label: str | None = None,
    y_label: str | None = None,
    style: VisualizationStyle = DEFAULT_STYLE,
):
    """Render prepared global Pareto overview from supplied layer points and frontiers."""
    pyplot = require_pyplot()
    figure, axis = pyplot.subplots(figsize=style.layouts.global_standard, dpi=style.dpi)
    palette = (*style.layer_colors, *style.extra_layer_colors)
    for index, layer in enumerate(_prepared_layer_order(eligible_by_layer.points, layer_order)):
        points = [point for point in eligible_by_layer.points if point.layer == layer]
        axis.scatter(
            [point.x for point in points],
            [point.y for point in points],
            marker="o",
            s=19,
            color=_cycle(palette, index),
            alpha=0.34,
            edgecolors="none",
            zorder=2,
            label=f"Layer {layer}",
        )
    for index, frontier in enumerate(global_frontiers):
        axis.plot(
            _x(frontier),
            _y(frontier),
            marker="o",
            markersize=4.2,
            color=_cycle(style.frontier_colors, index),
            linewidth=2.0,
            zorder=7,
            label=frontier.label,
        )
    setup_publication_objective_axis(axis, xlabel=x_label, ylabel=y_label, style=style)
    apply_objective_vertical_headroom(axis, fraction=PUBLICATION_OBJECTIVE_VERTICAL_HEADROOM_FRACTION)
    _axis_legend(axis, style=style)
    return figure


def plot_campaign_frontiers(
    campaign_frontiers: Sequence[ObjectiveSeries],
    global_frontier: ObjectiveSeries,
    threshold: float,
    *,
    score_points: ObjectiveSeries | None = None,
    x_label: str | None = None,
    y_label: str | None = None,
    style: VisualizationStyle = DEFAULT_STYLE,
):
    """Render prepared campaign frontiers and prepared global optimized frontier."""
    del threshold
    pyplot = require_pyplot()
    figure, axis = pyplot.subplots(figsize=style.layouts.global_wide, dpi=style.dpi)
    colorbar = None
    if score_points is not None:
        warnings.warn(
            "score_points is deprecated for campaign frontier coloring; "
            "supply prepared aggregate scores with ObjectiveSeries.score.",
            DeprecationWarning,
            stacklevel=2,
        )
    campaign_scores = [
        frontier.score
        for frontier in campaign_frontiers
        if not _is_reference_frontier(frontier) and frontier.score is not None
    ]
    color_mapper = _score_color_mapper(pyplot, campaign_scores, style=style) if campaign_scores else None
    normal_index = 0
    reference_index = 0
    for frontier in campaign_frontiers:
        if _is_reference_frontier(frontier):
            axis.plot(
                _x(frontier),
                _y(frontier),
                linestyle="--",
                marker="o",
                markersize=4.0,
                color=_cycle(style.reference_frontier_colors, reference_index),
                linewidth=1.8,
                alpha=0.95,
                zorder=6,
                label=frontier.label,
            )
            reference_index += 1
        else:
            frontier_color = (
                color_mapper(frontier.score)
                if color_mapper is not None and frontier.score is not None
                else _cycle(style.frontier_colors, normal_index)
            )
            axis.plot(
                _x(frontier),
                _y(frontier),
                linestyle="-",
                marker="o",
                markersize=3.6,
                color=frontier_color,
                linewidth=1.35,
                alpha=0.95,
                zorder=5,
                label=frontier.label,
            )
            normal_index += 1
    if color_mapper is not None:
        colorbar = figure.colorbar(color_mapper.mappable, ax=axis, fraction=0.022, pad=0.018)
        colorbar.set_label("Mean combined score")
    axis.plot(
        _x(global_frontier),
        _y(global_frontier),
        color="#000000",
        linewidth=2.6,
        zorder=20,
        label=global_frontier.label,
    )
    axis.scatter(
        _x(global_frontier),
        _y(global_frontier),
        s=28,
        marker="o",
        color="#000000",
        edgecolors="none",
        zorder=21,
        label="_nolegend_",
    )
    setup_publication_objective_axis(axis, xlabel=x_label, ylabel=y_label, style=style)
    apply_objective_vertical_headroom(axis)
    legend = axis.legend(
        loc="upper right",
        fontsize=7.5,
        frameon=True,
        fancybox=False,
        framealpha=1.0,
        edgecolor=style.legend_edgecolor,
        handlelength=2.5,
    )
    style_publication_legend(legend, style=style)
    figure._verfeinert_colorbar = colorbar  # type: ignore[attr-defined]
    return figure


def plot_global_pareto_score_map(
    background: ObjectiveSeries,
    campaign_pareto: ObjectiveSeries,
    global_frontier: ObjectiveSeries,
    global_frontier_members: ObjectiveSeries,
    *,
    threshold: float,
    reference_frontier: ObjectiveSeries | None = None,
    x_label: str | None = None,
    y_label: str | None = None,
    style: VisualizationStyle = DEFAULT_STYLE,
):
    """Render prepared campaign/global Pareto score map for one threshold."""
    del threshold
    pyplot = require_pyplot()
    figure, axis = pyplot.subplots(figsize=style.layouts.global_wide, dpi=style.dpi)
    axis.scatter(
        _x(background),
        _y(background),
        s=18,
        color="#BDBDBD",
        alpha=0.30,
        edgecolors="none",
        zorder=2,
        label=background.label,
    )
    scatter = axis.scatter(
        _x(campaign_pareto),
        _y(campaign_pareto),
        c=_required_scores(campaign_pareto.points),
        cmap=style.score_colormap,
        s=38,
        marker="*",
        edgecolors="#202020",
        linewidths=0.25,
        alpha=0.95,
        zorder=5,
        label=campaign_pareto.label,
    )
    colorbar = figure.colorbar(scatter, ax=axis, fraction=0.022, pad=0.018)
    colorbar.set_label(campaign_pareto.label or "Score")
    if reference_frontier is not None:
        axis.plot(
            _x(reference_frontier),
            _y(reference_frontier),
            color="#666666",
            linewidth=1.5,
            linestyle="--",
            zorder=6,
            label=reference_frontier.label,
        )
    axis.plot(
        _x(global_frontier),
        _y(global_frontier),
        color="#000000",
        linewidth=2.2,
        zorder=7,
        label=global_frontier.label,
    )
    axis.scatter(
        _x(global_frontier_members),
        _y(global_frontier_members),
        s=28,
        marker="o",
        color="#000000",
        edgecolors="none",
        zorder=8,
        label=global_frontier_members.label,
    )
    setup_publication_objective_axis(axis, xlabel=x_label, ylabel=y_label, style=style)
    apply_objective_vertical_headroom(axis)
    _axis_legend(axis, style=style)
    figure._verfeinert_colorbar = colorbar  # type: ignore[attr-defined]
    return figure


def plot_global_aggregate_metric(
    metric_bars: Sequence[BarSeries],
    *,
    y_label: str,
    style: VisualizationStyle = DEFAULT_STYLE,
):
    """Render one prepared global aggregate metric by campaign/source and threshold."""
    pyplot = require_pyplot()
    figure, axis = pyplot.subplots(figsize=style.layouts.global_standard, dpi=style.dpi)
    _plot_grouped_bars(axis, metric_bars, style=style, rotation=45, ha="right")
    axis.set_ylabel(y_label)
    axis.set_axisbelow(True)
    axis.grid(axis="y", alpha=style.grid_alpha)
    _axis_legend(axis, style=style)
    return figure


def plot_global_contributions(
    campaign_frontier_members: Sequence[BarSeries],
    global_frontier_members: Sequence[BarSeries],
    *,
    campaign_y_label: str = "Campaign frontier members",
    global_y_label: str = "Global optimized frontier members",
    style: VisualizationStyle = DEFAULT_STYLE,
):
    """Render prepared contribution comparison panels with independent y-axis labels."""
    pyplot = require_pyplot()
    figure, axes_array = pyplot.subplots(
        1,
        2,
        figsize=style.layouts.global_contribution,
        dpi=style.dpi,
        sharex=True,
    )
    axes = tuple(axes_array)
    _plot_grouped_bars(axes[0], campaign_frontier_members, style=style, rotation=48, ha="right")
    _plot_grouped_bars(axes[1], global_frontier_members, style=style, rotation=48, ha="right")
    axes[0].set_title("Campaign frontier members", fontsize=style.title_size)
    axes[1].set_title("Global optimized frontier members", fontsize=style.title_size)
    axes[0].set_ylabel(campaign_y_label)
    axes[1].set_ylabel(global_y_label)
    for axis in axes:
        axis.set_axisbelow(True)
        axis.grid(axis="y", alpha=style.grid_alpha)
    _axis_legend(axes[0], style=style)
    return figure


def plot_global_lineages(
    lineage_order: Sequence[str],
    eligible_counts: BarSeries,
    campaign_frontier_counts: BarSeries,
    global_frontier_member_counts: BarSeries,
    selected_lineage_points: ObjectiveSeries,
    global_frontier: ObjectiveSeries,
    *,
    threshold: float,
    x_label: str | None = None,
    y_label: str | None = None,
    style: VisualizationStyle = DEFAULT_STYLE,
):
    """Render prepared lineage contribution counts and selected-lineage objective points."""
    del threshold
    pyplot = require_pyplot()
    figure, axes_array = pyplot.subplots(
        1,
        2,
        figsize=style.layouts.global_lineage,
        dpi=style.dpi,
        gridspec_kw={"width_ratios": (1.35, 2), "wspace": 0.22},
    )
    left_axis, right_axis = tuple(axes_array)
    colors = ordered_lineage_color_map(lineage_order)
    bar_categories, eligible_values, campaign_values, global_values = _lineage_bar_display_data(
        eligible_counts,
        campaign_frontier_counts,
        global_frontier_member_counts,
    )
    positions = list(range(len(bar_categories)))
    bar_colors = [colors[category] for category in bar_categories]
    left_axis.barh(
        positions,
        eligible_values,
        color=bar_colors,
        alpha=0.28,
        label="Eligible candidates",
    )
    left_axis.barh(
        positions,
        campaign_values,
        color=bar_colors,
        alpha=0.85,
        label="Campaign-frontier members",
    )
    for position, eligible, campaign, global_count in zip(positions, eligible_values, campaign_values, global_values):
        left_axis.text(
            max(eligible, campaign) + 0.05,
            position,
            f"{global_count:g}",
            fontsize=8.2,
            fontweight="bold",
            color="#202020",
            va="center",
            zorder=12,
        )
    left_axis.set_yticks(positions)
    left_axis.set_yticklabels(bar_categories)
    left_axis.invert_yaxis()
    left_axis.set_xlabel("Candidates")
    max_bar_value = max((*eligible_values, *campaign_values), default=0.0)
    left_axis.set_xlim(0.0, max(1.0, max_bar_value * 1.22))
    handles, labels = left_axis.get_legend_handles_labels()
    handles.append(
        pyplot.Line2D(
            [],
            [],
            linestyle="None",
            marker="$1$",
            markersize=9,
            color="#202020",
            label="Number = global-frontier members",
        ),
    )
    labels.append("Number = global-frontier members")
    left_legend = left_axis.legend(
        handles,
        labels,
        loc="lower right",
        fontsize=10,
        frameon=True,
        fancybox=False,
        framealpha=1.0,
        edgecolor=style.legend_edgecolor,
    )
    style_publication_legend(left_legend, style=style)

    for lineage_id in lineage_order:
        points = [point for point in selected_lineage_points.points if point.lineage_id == lineage_id]
        if not points:
            continue
        right_axis.scatter(
            [point.x for point in points],
            [point.y for point in points],
            s=23,
            alpha=0.5,
            color=colors[lineage_id],
            edgecolors="none",
            label=lineage_id,
        )
    right_axis.plot(
        _x(global_frontier),
        _y(global_frontier),
        color=_cycle(style.frontier_colors, 0),
        linewidth=2.2,
        zorder=15,
        label=global_frontier.label,
    )
    setup_publication_objective_axis(right_axis, xlabel=x_label, ylabel=y_label, style=style)
    apply_objective_vertical_headroom(right_axis)
    _axis_legend(
        right_axis,
        style=style,
        fontsize=8,
        ncol=2 if len(lineage_order) > 5 else 1,
        handletextpad=0.4,
        columnspacing=0.7,
    )
    return figure


def plot_global_ranking_table(
    table: TableSpec,
    *,
    style: VisualizationStyle = DEFAULT_STYLE,
):
    """Render a prepared global publication ranking table."""
    return plot_publication_table(table, style=style)


def _plot_grouped_bars(
    axis,
    serieses: Sequence[BarSeries],
    *,
    style: VisualizationStyle,
    rotation: float,
    ha: str,
) -> None:
    resolved = tuple(serieses)
    if not resolved:
        return
    categories = resolved[0].categories
    if any(series.categories != categories for series in resolved):
        raise VisualizationModelError("grouped bar series must share categories in the same order.")
    group_count = len(resolved)
    width = 0.8
    slot_width = width / group_count
    base_positions = list(range(len(categories)))
    all_values: list[float] = []
    for series_index, series in enumerate(resolved):
        values = _required_values(series)
        all_values.extend(values)
        offset = (series_index - (group_count - 1) / 2.0) * slot_width
        axis.bar(
            [position + offset for position in base_positions],
            values,
            width=slot_width,
            color=_cycle(style.frontier_colors, series_index),
            label=series.label,
            zorder=3,
        )
    axis.set_xticks(base_positions)
    axis.set_xticklabels(categories, rotation=rotation, ha=ha)
    apply_bar_headroom(axis, all_values)


def _axis_legend(axis, *, style: VisualizationStyle, **legend_kwargs) -> None:
    handles, labels = axis.get_legend_handles_labels()
    if not handles:
        return
    options = {
        "loc": style.legend_location,
        "frameon": style.legend_frame,
        "framealpha": 1.0,
        "edgecolor": style.legend_edgecolor,
        "fancybox": style.legend_fancybox,
        "fontsize": style.legend_size,
    }
    options.update(legend_kwargs)
    legend = axis.legend(
        handles,
        labels,
        **options,
    )
    style_publication_legend(legend, style=style)


def _lineage_bar_display_data(
    eligible_counts: BarSeries,
    campaign_frontier_counts: BarSeries,
    global_frontier_member_counts: BarSeries,
) -> tuple[tuple[str, ...], list[float], list[float], list[float]]:
    categories = eligible_counts.categories
    if (
        campaign_frontier_counts.categories != categories
        or global_frontier_member_counts.categories != categories
    ):
        raise VisualizationModelError("G_H lineage count series must share categories in the same order.")
    eligible_values = _required_values(eligible_counts)
    campaign_values = _required_values(campaign_frontier_counts)
    global_values = _required_values(global_frontier_member_counts)
    display_indices = tuple(sorted(range(len(categories)), key=lambda index: (-eligible_values[index], index)))
    return (
        tuple(categories[index] for index in display_indices),
        [eligible_values[index] for index in display_indices],
        [campaign_values[index] for index in display_indices],
        [global_values[index] for index in display_indices],
    )


def _is_reference_frontier(frontier: ObjectiveSeries) -> bool:
    return frontier.role in {"reference", "baseline", "reference_frontier"}


def _score_color_mapper(pyplot, scores: Sequence[float], *, style: VisualizationStyle):
    minimum = min(scores)
    maximum = max(scores)
    if minimum == maximum:
        minimum -= 0.5
        maximum += 0.5
    normalizer = pyplot.Normalize(vmin=minimum, vmax=maximum)
    colormap = pyplot.get_cmap(style.score_colormap)
    mappable = pyplot.matplotlib.cm.ScalarMappable(norm=normalizer, cmap=colormap)
    mappable.set_array(list(scores))

    def color(score: float | None):
        if score is None:
            return _cycle(style.frontier_colors, 0)
        return colormap(normalizer(score))

    color.mappable = mappable  # type: ignore[attr-defined]
    return color


def _required_values(series: BarSeries) -> list[float]:
    if any(value is None for value in series.values):
        raise VisualizationModelError("bar values must be available for rendering.")
    return [float(value) for value in series.values if value is not None]


def _required_scores(points: Sequence[ObjectivePoint]) -> list[float]:
    scores = []
    for point in points:
        if point.score is None:
            raise VisualizationModelError("score-colored points must carry prepared score values.")
        scores.append(point.score)
    return scores


def _prepared_layer_order(points: Sequence[ObjectivePoint], layer_order: Sequence[int] | None) -> tuple[int, ...]:
    if layer_order is not None:
        return tuple(int(layer) for layer in layer_order)
    seen = []
    for point in points:
        if point.layer is not None and point.layer not in seen:
            seen.append(point.layer)
    return tuple(seen)


def _x(series: ObjectiveSeries) -> list[float]:
    return [point.x for point in series.points]


def _y(series: ObjectiveSeries) -> list[float]:
    return [point.y for point in series.points]


def _cycle(values: Sequence[str], index: int) -> str:
    if not values:
        raise VisualizationModelError("visual palette must not be empty.")
    return values[index % len(values)]


__all__ = [
    "plot_campaign_frontiers",
    "plot_global_aggregate_metric",
    "plot_global_contributions",
    "plot_global_cost_eligibility",
    "plot_global_lineages",
    "plot_global_pareto",
    "plot_global_pareto_score_map",
    "plot_global_ranking_table",
]
