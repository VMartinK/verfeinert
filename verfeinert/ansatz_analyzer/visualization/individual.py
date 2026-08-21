"""Publication renderers for prepared individual-campaign visualization data."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from .export import require_pyplot
from .models import BarSeries, ObjectivePoint, ObjectiveSeries, VisualizationModelError
from .primitives import ordered_lineage_color_map, setup_publication_objective_axis, style_publication_legend
from .styles import DEFAULT_STYLE, VisualizationStyle


_INDIVIDUAL_ROLE_LABELS = {
    "discarded": "discard",
    "expressibility_improvement": "expressibility improvement",
    "trainability_improvement": "trainability improvement",
    "new_pareto": "new Pareto optimal",
}
_INDIVIDUAL_ROLE_ZORDER = {
    "discarded": 3,
    "expressibility_improvement": 5,
    "trainability_improvement": 5,
    "new_pareto": 8,
}


def plot_individual_classification(
    reference_eligible: ObjectiveSeries,
    reference_frontier: ObjectiveSeries,
    classified_candidates: ObjectiveSeries,
    threshold: float,
    *,
    x_label: str | None = None,
    y_label: str | None = None,
    style: VisualizationStyle = DEFAULT_STYLE,
):
    """Render one prepared individual-campaign classification figure for one threshold."""
    del threshold
    pyplot = require_pyplot()
    figure, axis = pyplot.subplots(figsize=style.layouts.standard, dpi=style.dpi)
    legend_handles: dict[str, Any] = {}

    if reference_eligible.points:
        legend_handles["eligible reference"] = axis.scatter(
            _x(reference_eligible),
            _y(reference_eligible),
            marker="o",
            s=30,
            facecolors="#E0E0E0",
            edgecolors="#8A8A8A",
            linewidths=0.65,
            alpha=0.62,
            zorder=1,
            label="eligible reference",
        )
        axis.scatter(
            _x(reference_eligible),
            _y(reference_eligible),
            marker="x",
            s=20,
            color="#8A8A8A",
            linewidths=0.60,
            alpha=0.62,
            zorder=2,
            label="_nolegend_",
        )

    if reference_frontier.points:
        legend_handles["reference frontier"] = axis.plot(
            _x(reference_frontier),
            _y(reference_frontier),
            marker="o",
            markersize=4.8,
            color=_cycle(style.frontier_colors, 0),
            linewidth=1.7,
            zorder=7,
            label="reference frontier",
        )[0]

    for role in ("discarded", "expressibility_improvement", "trainability_improvement", "new_pareto"):
        points = _points_by_role(classified_candidates, role)
        if not points:
            continue
        role_style = style.role_styles[role]
        scatter_kwargs = {
            "marker": role_style.marker,
            "s": role_style.size,
            "color": role_style.color,
            "alpha": role_style.alpha,
            "zorder": _INDIVIDUAL_ROLE_ZORDER[role],
            "label": _INDIVIDUAL_ROLE_LABELS[role],
        }
        if role == "new_pareto":
            scatter_kwargs.update(edgecolors="#202020", linewidths=0.75)
        else:
            scatter_kwargs.update(edgecolors="none")
        legend_handles[_INDIVIDUAL_ROLE_LABELS[role]] = axis.scatter(
            [point.x for point in points],
            [point.y for point in points],
            **scatter_kwargs,
        )

    setup_publication_objective_axis(axis, xlabel=x_label, ylabel=y_label, style=style)
    _apply_legend(
        axis,
        legend_handles,
        (
            "reference frontier",
            "discard",
            "eligible reference",
            "expressibility improvement",
            "trainability improvement",
            "new Pareto optimal",
        ),
        style=style,
        bbox_to_anchor=(0.985, 0.985),
        ncol=1,
        columnspacing=1.2,
        handletextpad=0.6,
    )
    return figure


def plot_individual_joint_frontiers(
    frontiers: Sequence[ObjectiveSeries],
    *,
    x_label: str | None = None,
    y_label: str | None = None,
    xlim: tuple[float, float] | None = None,
    ylim: tuple[float, float] | None = None,
    style: VisualizationStyle = DEFAULT_STYLE,
):
    """Render prepared optimized/joint frontier series for ordered thresholds."""
    pyplot = require_pyplot()
    figure, axis = pyplot.subplots(figsize=style.layouts.standard, dpi=style.dpi)
    for index, frontier in enumerate(frontiers):
        axis.plot(
            _x(frontier),
            _y(frontier),
            marker="o",
            markersize=5.0,
            color=_cycle(style.frontier_colors, index),
            linewidth=1.9,
            zorder=6,
            label=frontier.label,
        )
    _finish_objective_axis(axis, x_label=x_label, y_label=y_label, xlim=xlim, ylim=ylim, style=style)
    _legend_from_axis(axis, style=style, bbox_to_anchor=(0.985, 0.985))
    return figure


def plot_individual_frontier_comparison(
    reference_frontiers: Sequence[ObjectiveSeries],
    primary_frontiers: Sequence[ObjectiveSeries],
    *,
    x_label: str | None = None,
    y_label: str | None = None,
    style: VisualizationStyle = DEFAULT_STYLE,
):
    """Render prepared reference and optimized frontier series together."""
    pyplot = require_pyplot()
    figure, axis = pyplot.subplots(figsize=style.layouts.standard, dpi=style.dpi)
    for index, frontier in enumerate(reference_frontiers):
        axis.plot(
            _x(frontier),
            _y(frontier),
            marker="o",
            markersize=4.5,
            color=_cycle(style.reference_frontier_colors, index),
            linewidth=1.45,
            linestyle="--",
            alpha=0.92,
            zorder=4,
            label=frontier.label,
        )
    for index, frontier in enumerate(primary_frontiers):
        axis.plot(
            _x(frontier),
            _y(frontier),
            marker="o",
            markersize=5.2,
            color=_cycle(style.frontier_colors, index),
            linewidth=2.05,
            linestyle="-",
            zorder=7,
            label=frontier.label,
        )
    setup_publication_objective_axis(axis, xlabel=x_label, ylabel=y_label, style=style)
    _legend_from_axis(
        axis,
        style=style,
        bbox_to_anchor=(0.985, 0.985),
        ncol=2,
        columnspacing=2.8,
        handletextpad=0.8,
    )
    return figure


def plot_individual_by_layer(
    candidates: ObjectiveSeries,
    reference_frontiers: Sequence[ObjectiveSeries],
    *,
    layer_order: Sequence[int] | None = None,
    x_label: str | None = None,
    y_label: str | None = None,
    style: VisualizationStyle = DEFAULT_STYLE,
):
    """Render prepared candidate points grouped by their supplied layer."""
    pyplot = require_pyplot()
    figure, axis = pyplot.subplots(figsize=style.layouts.standard, dpi=style.dpi)
    for index, layer in enumerate(_prepared_layer_order(candidates.points, layer_order)):
        points = [point for point in candidates.points if point.layer == layer]
        axis.scatter(
            [point.x for point in points],
            [point.y for point in points],
            marker="o",
            s=30,
            color=_cycle((*style.layer_colors, *style.extra_layer_colors), index),
            edgecolors="none",
            alpha=0.58,
            zorder=3,
            label=f"Layer {layer}",
        )
    for index, frontier in enumerate(reference_frontiers):
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
    _legend_from_axis(axis, style=style, ncol=2)
    return figure


def plot_individual_by_lineage(
    candidates: ObjectiveSeries,
    reference_frontiers: Sequence[ObjectiveSeries],
    lineage_order: Sequence[str],
    *,
    x_label: str | None = None,
    y_label: str | None = None,
    xlim: tuple[float, float] | None = None,
    ylim: tuple[float, float] | None = None,
    style: VisualizationStyle = DEFAULT_STYLE,
):
    """Render prepared candidate points grouped by supplied lineage IDs."""
    pyplot = require_pyplot()
    figure, axis = pyplot.subplots(figsize=style.layouts.standard, dpi=style.dpi)
    colors = ordered_lineage_color_map(lineage_order)
    lineage_handles = []
    lineage_labels = []
    for lineage_id in lineage_order:
        points = [point for point in candidates.points if point.lineage_id == lineage_id]
        if not points:
            continue
        lineage_handles.append(
            axis.scatter(
                [point.x for point in points],
                [point.y for point in points],
                marker="o",
                s=30,
                color=colors[lineage_id],
                edgecolors="none",
                alpha=0.58,
                zorder=3,
                label=lineage_id,
            ),
        )
        lineage_labels.append(lineage_id)

    reference_handles = []
    reference_labels = []
    for index, frontier in enumerate(reference_frontiers):
        reference_handles.append(
            axis.plot(
                _x(frontier),
                _y(frontier),
                marker="o",
                markersize=4.5,
                color=_cycle(style.frontier_colors, index),
                linewidth=1.55,
                zorder=7,
                label=frontier.label,
            )[0],
        )
        reference_labels.append(frontier.label or f"Reference {index + 1}")

    _finish_objective_axis(axis, x_label=x_label, y_label=y_label, xlim=xlim, ylim=ylim, style=style)
    _reserve_x_legend_strip(axis, 0.34)
    if reference_handles:
        reference_legend = axis.legend(
            reference_handles,
            reference_labels,
            loc="upper right",
            bbox_to_anchor=(0.985, 0.985),
            fontsize=6.8,
            frameon=True,
            handletextpad=0.45,
            labelspacing=0.28,
            markerscale=0.9,
            borderpad=0.45,
            framealpha=style.legend_framealpha,
            edgecolor=style.legend_edgecolor,
            fancybox=style.legend_fancybox,
        )
        style_publication_legend(reference_legend, style=style)
        axis.add_artist(reference_legend)
    if lineage_handles:
        lineage_legend = axis.legend(
            lineage_handles,
            lineage_labels,
            loc="upper right",
            bbox_to_anchor=(0.985, 0.8),
            fontsize=6.4,
            frameon=True,
            handletextpad=0.3,
            columnspacing=0.65,
            labelspacing=0.25,
            markerscale=0.85,
            borderpad=0.42,
            framealpha=style.legend_framealpha,
            edgecolor=style.legend_edgecolor,
            fancybox=style.legend_fancybox,
            ncol=2 if len(lineage_labels) > 8 else 1,
        )
        style_publication_legend(lineage_legend, style=style)
    return figure


def plot_individual_pareto_by_lineage(
    counts: BarSeries,
    *,
    lineage_order: Sequence[str] | None = None,
    style: VisualizationStyle = DEFAULT_STYLE,
):
    """Render prepared Pareto-optimal counts by prepared lineage category."""
    pyplot = require_pyplot()
    figure, axis = pyplot.subplots(figsize=style.layouts.standard, dpi=style.dpi)
    order = tuple(lineage_order or counts.categories)
    colors = ordered_lineage_color_map(order)
    values = _required_values(counts)
    positions = list(range(len(counts.categories)))
    bars = axis.bar(
        positions,
        values,
        color=[colors[category] for category in counts.categories],
        edgecolor="black",
        linewidth=0.75,
        alpha=0.9,
        zorder=3,
    )
    axis.set_xticks(positions)
    axis.set_xticklabels(counts.categories, rotation=45, ha="right")
    axis.set_xlabel("Lineage ID")
    axis.set_ylabel("Number of Pareto-optimal candidates")
    axis.set_axisbelow(True)
    axis.grid(axis="y", alpha=style.grid_alpha)
    y_max = max(values, default=0.0)
    axis.set_ylim(0, max(1.0, y_max) + 0.75)
    for bar, value in zip(bars, values):
        axis.text(
            bar.get_x() + bar.get_width() / 2.0,
            value + 0.05,
            f"{value:g}",
            ha="center",
            va="bottom",
            fontsize=8,
            color=style.annotation_text_color,
        )
    return figure


def _x(series: ObjectiveSeries) -> list[float]:
    return [point.x for point in series.points]


def _y(series: ObjectiveSeries) -> list[float]:
    return [point.y for point in series.points]


def _points_by_role(series: ObjectiveSeries, role: str) -> list[ObjectivePoint]:
    return [point for point in series.points if point.role == role]


def _cycle(values: Sequence[str], index: int) -> str:
    if not values:
        raise VisualizationModelError("visual palette must not be empty.")
    return values[index % len(values)]


def _finish_objective_axis(
    axis,
    *,
    x_label: str | None,
    y_label: str | None,
    xlim: tuple[float, float] | None,
    ylim: tuple[float, float] | None,
    style: VisualizationStyle,
) -> None:
    setup_publication_objective_axis(axis, xlabel=x_label, ylabel=y_label, style=style)
    if xlim is not None:
        axis.set_xlim(*xlim)
    if ylim is not None:
        axis.set_ylim(*ylim)


def _prepared_layer_order(points: Sequence[ObjectivePoint], layer_order: Sequence[int] | None) -> tuple[int, ...]:
    if layer_order is not None:
        return tuple(int(layer) for layer in layer_order)
    seen = []
    for point in points:
        if point.layer is not None and point.layer not in seen:
            seen.append(point.layer)
    return tuple(seen)


def _reserve_x_legend_strip(axis, fraction: float) -> None:
    xmin, xmax = axis.get_xlim()
    span = xmax - xmin
    if span > 0:
        axis.set_xlim(xmin, xmax + fraction * span)


def _apply_legend(
    axis,
    handles: dict[str, Any],
    labels: Sequence[str],
    *,
    style: VisualizationStyle,
    **kwargs,
) -> None:
    ordered_labels = [label for label in labels if label in handles]
    if not ordered_labels:
        return
    legend = axis.legend(
        [handles[label] for label in ordered_labels],
        ordered_labels,
        loc=style.legend_location,
        frameon=style.legend_frame,
        framealpha=style.legend_framealpha,
        edgecolor=style.legend_edgecolor,
        fancybox=style.legend_fancybox,
        fontsize=style.legend_size,
        **kwargs,
    )
    style_publication_legend(legend, style=style)


def _legend_from_axis(axis, *, style: VisualizationStyle, **kwargs) -> None:
    handles, labels = axis.get_legend_handles_labels()
    handles_and_labels = [(handle, label) for handle, label in zip(handles, labels) if label]
    if not handles_and_labels:
        return
    legend = axis.legend(
        [item[0] for item in handles_and_labels],
        [item[1] for item in handles_and_labels],
        loc=style.legend_location,
        frameon=style.legend_frame,
        framealpha=style.legend_framealpha,
        edgecolor=style.legend_edgecolor,
        fancybox=style.legend_fancybox,
        fontsize=style.legend_size,
        **kwargs,
    )
    style_publication_legend(legend, style=style)


def _required_values(series: BarSeries) -> list[float]:
    if any(value is None for value in series.values):
        raise VisualizationModelError("bar values must be available for rendering.")
    return [float(value) for value in series.values if value is not None]


__all__ = [
    "plot_individual_by_layer",
    "plot_individual_by_lineage",
    "plot_individual_classification",
    "plot_individual_frontier_comparison",
    "plot_individual_joint_frontiers",
    "plot_individual_pareto_by_lineage",
]
