"""Evolution visualization data adapters and publication renderers."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from ..collections import AnalysisResultCollection, cost_value, metric_value
from .export import require_pyplot
from .models import BarSeries, MetricSeries, ObjectivePoint, ObjectiveSeries, TableSpec, VisualizationModelError
from .primitives import (
    apply_objective_vertical_headroom,
    ordered_lineage_color_map,
    plot_publication_table,
    setup_publication_objective_axis,
    style_publication_legend,
)
from .styles import DEFAULT_STYLE, VisualizationStyle


@dataclass(frozen=True)
class MetricPanelSpec:
    """Prepared metric panel data for generation-metric grids."""

    title: str
    y_label: str
    series: tuple[MetricSeries, ...]


@dataclass(frozen=True)
class LineageBarPanelSpec:
    """Prepared lineage-count panel data for lineage evolution."""

    title: str
    counts: BarSeries


def evolution_plot_data(collection: AnalysisResultCollection) -> list[dict[str, Any]]:
    """Return generation-aware metric records when generation metadata exists."""
    if not isinstance(collection, AnalysisResultCollection):
        raise TypeError("collection must be an AnalysisResultCollection.")
    rows = []
    for document in collection:
        metadata = document.get("metadata", {})
        semantics = metadata.get("candidate_semantics", {}) if isinstance(metadata, dict) else {}
        lineage = semantics.get("lineage", {}) if isinstance(semantics, dict) else {}
        generation = lineage.get("generation")
        rows.append(
            {
                "candidate_id": document["candidate_ref"]["candidate_id"],
                "generation": generation,
                "expressibility": metric_value(document, "expressibility"),
                "trainability": metric_value(document, "trainability"),
                "structural_cost": cost_value(document, "structural_cost"),
            },
        )
    return rows


def plot_generation_candidate_counts(
    generated_counts: Sequence[MetricSeries],
    selected_counts: Sequence[MetricSeries],
    *,
    x_label: str = "Generation",
    style: VisualizationStyle = DEFAULT_STYLE,
):
    """Render prepared generated and selected candidate counts by generation."""
    pyplot = require_pyplot()
    figure, axes_array = pyplot.subplots(1, 2, figsize=style.layouts.generation_counts, dpi=style.dpi)
    axes = tuple(axes_array)
    _plot_metric_lines(axes[0], generated_counts, style=style)
    _plot_metric_lines(axes[1], selected_counts, style=style)
    axes[0].set_title("Generated candidates", fontsize=style.title_size)
    axes[1].set_title("Selected candidates", fontsize=style.title_size)
    for axis in axes:
        setup_publication_objective_axis(axis, xlabel=x_label, ylabel="Candidates", style=style)
    _shared_figure_legend(figure, axes[0], style=style)
    return figure


def plot_generation_metric_grid(
    panels: Sequence[MetricPanelSpec],
    *,
    x_label: str = "Generation",
    style: VisualizationStyle = DEFAULT_STYLE,
):
    """Render a 2x2 grid from four prepared generation metric panels."""
    resolved = tuple(panels)
    if len(resolved) != 4:
        raise VisualizationModelError("generation metric grid requires exactly four prepared panels.")
    pyplot = require_pyplot()
    figure, axes_array = pyplot.subplots(2, 2, figsize=style.layouts.standard, dpi=style.dpi)
    axes = tuple(axes_array.flat)
    for axis, panel in zip(axes, resolved):
        _plot_metric_lines(axis, panel.series, style=style)
        axis.set_title("")
        setup_publication_objective_axis(axis, xlabel=x_label, ylabel=panel.y_label, style=style)
    _space_metric_grid_horizontally(figure, axes)
    _shared_figure_legend(figure, axes[0], style=style)
    return figure


def plot_frontier_evolution(
    frontiers: Sequence[ObjectiveSeries],
    threshold: float,
    *,
    x_label: str | None = None,
    y_label: str | None = None,
    threshold_color: str | None = None,
    style: VisualizationStyle = DEFAULT_STYLE,
):
    """Render prepared frontier series by prepared generation order for one threshold."""
    del threshold
    pyplot = require_pyplot()
    figure, axis = pyplot.subplots(figsize=style.layouts.standard, dpi=style.dpi)
    color = threshold_color or _cycle(style.frontier_colors, 0)
    resolved = tuple(frontiers)
    count = len(resolved)
    for index, frontier in enumerate(resolved):
        axis.plot(
            _x(frontier),
            _y(frontier),
            marker="o",
            markersize=5.0,
            color=color,
            alpha=_generation_alpha(index, count),
            linewidth=1.9,
            zorder=6,
            label=frontier.label,
        )
    setup_publication_objective_axis(axis, xlabel=x_label, ylabel=y_label, style=style)
    apply_objective_vertical_headroom(axis)
    _axis_legend(axis, style=style)
    return figure


def plot_frontier_generation_comparison(
    previous_frontier: ObjectiveSeries,
    current_frontier: ObjectiveSeries,
    improvement_points: ObjectiveSeries,
    *,
    reference_frontier: ObjectiveSeries | None = None,
    threshold: float | None = None,
    generation: int | None = None,
    x_label: str | None = None,
    y_label: str | None = None,
    style: VisualizationStyle = DEFAULT_STYLE,
):
    """Render a prepared generation-to-generation frontier comparison."""
    del threshold
    pyplot = require_pyplot()
    figure, axes_array = pyplot.subplots(
        1,
        2,
        figsize=style.layouts.standard,
        dpi=style.dpi,
        gridspec_kw={"width_ratios": (1, 1), "wspace": 0.28},
    )
    figure.subplots_adjust(left=0.105, right=0.97)
    axes = tuple(axes_array)
    panel_titles = ("Previous frontier", "Current frontier" if generation is None else f"Generation {generation}")
    for axis, title in zip(axes, panel_titles):
        axis.set_title("")
        if reference_frontier is not None:
            axis.plot(
                _x(reference_frontier),
                _y(reference_frontier),
                color="#666666",
                linewidth=1.3,
                linestyle="--",
                zorder=3,
                label=reference_frontier.label,
            )
        setup_publication_objective_axis(axis, xlabel=x_label, ylabel=y_label, style=style)
        axis.set_title(title, loc="center", fontsize=style.title_size, pad=10)
    axes[0].plot(
        _x(previous_frontier),
        _y(previous_frontier),
        marker="o",
        color=_cycle(style.reference_frontier_colors, 0),
        linewidth=1.65,
        zorder=5,
        label=previous_frontier.label,
    )
    axes[1].plot(
        _x(current_frontier),
        _y(current_frontier),
        marker="o",
        color=_cycle(style.frontier_colors, 0),
        linewidth=1.9,
        zorder=6,
        label=current_frontier.label,
    )
    _scatter_improvement_points(axes[1], improvement_points, style=style)
    for axis in axes:
        apply_objective_vertical_headroom(axis)
        _axis_legend(axis, style=style)
    _add_panel_separator(figure, axes, pyplot=pyplot, style=style)
    return figure


def plot_final_frontier_vs_eligible(
    eligible_candidates: ObjectiveSeries,
    final_frontier: ObjectiveSeries,
    threshold: float,
    *,
    x_label: str | None = None,
    y_label: str | None = None,
    style: VisualizationStyle = DEFAULT_STYLE,
):
    """Render prepared final frontier against prepared eligible/background points."""
    del threshold
    pyplot = require_pyplot()
    figure, axis = pyplot.subplots(figsize=style.layouts.standard, dpi=style.dpi)
    axis.scatter(
        _x(eligible_candidates),
        _y(eligible_candidates),
        marker="o",
        s=24,
        color="#BDBDBD",
        edgecolors="none",
        alpha=0.34,
        zorder=2,
        label=eligible_candidates.label,
    )
    axis.plot(
        _x(final_frontier),
        _y(final_frontier),
        marker="o",
        markersize=5.0,
        color=_cycle(style.frontier_colors, 0),
        linewidth=2.0,
        zorder=7,
        label=final_frontier.label,
    )
    setup_publication_objective_axis(axis, xlabel=x_label, ylabel=y_label, style=style)
    apply_objective_vertical_headroom(axis)
    _axis_legend(axis, style=style)
    return figure


def plot_evolution_by_layer(
    candidates: ObjectiveSeries,
    final_frontiers: Sequence[ObjectiveSeries],
    *,
    layer_order: Sequence[int] | None = None,
    x_label: str | None = None,
    y_label: str | None = None,
    style: VisualizationStyle = DEFAULT_STYLE,
):
    """Render prepared evolution candidate points by supplied layer dimension."""
    pyplot = require_pyplot()
    figure, axis = pyplot.subplots(figsize=style.layouts.standard, dpi=style.dpi)
    palette = (*style.layer_colors, *style.extra_layer_colors)
    for index, layer in enumerate(_prepared_layer_order(candidates.points, layer_order)):
        points = [point for point in candidates.points if point.layer == layer]
        axis.scatter(
            [point.x for point in points],
            [point.y for point in points],
            marker="o",
            s=30,
            color=_cycle(palette, index),
            edgecolors="none",
            alpha=0.58,
            zorder=3,
            label=f"Layer {layer}",
        )
    for index, frontier in enumerate(final_frontiers):
        axis.plot(
            _x(frontier),
            _y(frontier),
            marker="o",
            markersize=4.5,
            color=_cycle(style.frontier_colors, index),
            linewidth=1.55,
            zorder=7,
            label=frontier.label,
        )
    setup_publication_objective_axis(axis, xlabel=x_label, ylabel=y_label, style=style)
    _axis_legend(axis, style=style)
    return figure


def plot_lineage_evolution(
    panels: Sequence[LineageBarPanelSpec],
    lineage_order: Sequence[str],
    threshold: float,
    *,
    style: VisualizationStyle = DEFAULT_STYLE,
):
    """Render prepared lineage evolution count panels for one threshold."""
    del threshold
    resolved = tuple(panels)
    if len(resolved) != 3:
        raise VisualizationModelError("lineage evolution requires exactly three prepared panels.")
    pyplot = require_pyplot()
    figure, axes_array = pyplot.subplots(1, 3, figsize=(17.0, 5.8), dpi=style.dpi)
    axes = tuple(axes_array)
    colors = ordered_lineage_color_map(lineage_order)
    for axis, panel in zip(axes, resolved):
        values = _required_values(panel.counts)
        positions = list(range(len(panel.counts.categories)))
        axis.bar(
            positions,
            values,
            color=[colors[category] for category in panel.counts.categories],
            edgecolor="black",
            linewidth=0.55,
            alpha=0.9,
            zorder=3,
        )
        axis.set_title(panel.title, fontsize=style.title_size)
        axis.set_xticks(positions)
        axis.set_xticklabels(panel.counts.categories, rotation=45, ha="right")
        axis.set_ylabel(panel.counts.label or "Count")
        axis.set_axisbelow(True)
        axis.grid(axis="y", alpha=style.grid_alpha)
    return figure


def plot_evolution_ranking_table(
    table: TableSpec,
    *,
    style: VisualizationStyle = DEFAULT_STYLE,
):
    """Render a prepared evolution publication ranking table."""
    return plot_publication_table(table, style=style)


def _plot_metric_lines(axis, serieses: Sequence[MetricSeries], *, style: VisualizationStyle) -> None:
    for index, series in enumerate(serieses):
        axis.plot(
            list(series.x),
            list(series.y),
            marker="o",
            linewidth=1.8,
            color=_cycle(style.frontier_colors, index),
            label=series.label,
        )


def _shared_figure_legend(figure, source_axis, *, style: VisualizationStyle) -> None:
    handles, labels = source_axis.get_legend_handles_labels()
    if not handles:
        return
    figure.subplots_adjust(top=0.84)
    legend = figure.legend(
        handles,
        labels,
        loc="upper right",
        bbox_to_anchor=(0.985, 0.985),
        ncol=max(1, len(labels)),
        frameon=style.legend_frame,
        framealpha=1.0,
        edgecolor=style.legend_edgecolor,
        fancybox=style.legend_fancybox,
        fontsize=style.legend_size,
    )
    style_publication_legend(legend, style=style)


def _space_metric_grid_horizontally(figure, axes: tuple[Any, ...]) -> None:
    figure.subplots_adjust(left=0.14, right=0.965, wspace=0.42)
    figure.align_ylabels(axes)


def _axis_legend(axis, *, style: VisualizationStyle) -> None:
    handles, labels = axis.get_legend_handles_labels()
    if not handles:
        return
    legend = axis.legend(
        handles,
        labels,
        loc=style.legend_location,
        frameon=style.legend_frame,
        framealpha=1.0,
        edgecolor=style.legend_edgecolor,
        fancybox=style.legend_fancybox,
        fontsize=style.legend_size,
    )
    style_publication_legend(legend, style=style)


def _generation_alpha(index: int, count: int) -> float:
    if count <= 1:
        return 1.0
    return 0.25 + (0.75 * index / (count - 1))


def _add_panel_separator(figure, axes: tuple[Any, Any], *, pyplot, style: VisualizationStyle) -> None:
    left_position = axes[0].get_position()
    right_position = axes[1].get_position()
    x = (left_position.x1 + right_position.x0) / 2.0
    y0 = min(left_position.y0, right_position.y0)
    y1 = max(left_position.y1, right_position.y1)
    separator = pyplot.Line2D(
        [x, x],
        [y0, y1],
        transform=figure.transFigure,
        color=style.legend_edgecolor,
        linewidth=0.85,
        alpha=0.75,
        zorder=4,
    )
    separator.set_gid("verfeinert-panel-separator")
    figure.add_artist(separator)


def _scatter_improvement_points(axis, series: ObjectiveSeries, *, style: VisualizationStyle) -> None:
    for role in ("expressibility_improvement", "trainability_improvement", "new_pareto", "frontier_improvement"):
        points = [point for point in series.points if point.role == role]
        if not points:
            continue
        role_style = style.role_styles[role]
        kwargs: dict[str, Any] = {
            "marker": role_style.marker,
            "s": role_style.size,
            "color": role_style.color,
            "alpha": role_style.alpha,
            "zorder": 8 if role == "new_pareto" else 5,
            "label": role.replace("_", " "),
        }
        if role == "new_pareto":
            kwargs.update(edgecolors="#202020", linewidths=0.75)
        else:
            kwargs.update(edgecolors="none")
        axis.scatter([point.x for point in points], [point.y for point in points], **kwargs)


def _x(series: ObjectiveSeries) -> list[float]:
    return [point.x for point in series.points]


def _y(series: ObjectiveSeries) -> list[float]:
    return [point.y for point in series.points]


def _cycle(values: Sequence[str], index: int) -> str:
    if not values:
        raise VisualizationModelError("visual palette must not be empty.")
    return values[index % len(values)]


def _prepared_layer_order(points: Sequence[ObjectivePoint], layer_order: Sequence[int] | None) -> tuple[int, ...]:
    if layer_order is not None:
        return tuple(int(layer) for layer in layer_order)
    seen = []
    for point in points:
        if point.layer is not None and point.layer not in seen:
            seen.append(point.layer)
    return tuple(seen)


def _required_values(series: BarSeries) -> list[float]:
    if any(value is None for value in series.values):
        raise VisualizationModelError("bar values must be available for rendering.")
    return [float(value) for value in series.values if value is not None]


__all__ = [
    "LineageBarPanelSpec",
    "MetricPanelSpec",
    "evolution_plot_data",
    "plot_evolution_by_layer",
    "plot_evolution_ranking_table",
    "plot_final_frontier_vs_eligible",
    "plot_frontier_evolution",
    "plot_frontier_generation_comparison",
    "plot_generation_candidate_counts",
    "plot_generation_metric_grid",
    "plot_lineage_evolution",
]
