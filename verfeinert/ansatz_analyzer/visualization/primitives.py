"""Reusable low-level publication visualization primitives."""

from __future__ import annotations

from collections.abc import Sequence
import colorsys
import hashlib
import math
from typing import Any

from .labels import PUBLICATION_EXPRESSIBILITY_LABEL, PUBLICATION_TRAINABILITY_LABEL
from .models import BarSeries, ObjectiveSeries, TableSpec, VisualizationModelError
from .styles import DEFAULT_STYLE, SemanticRoleStyle, VisualizationStyle

PUBLICATION_LEGEND_ZORDER = 1000
BAR_HEADROOM_FACTOR = 1.18
OBJECTIVE_VERTICAL_HEADROOM_FRACTION = 0.22
PUBLICATION_OBJECTIVE_VERTICAL_HEADROOM_FRACTION = 0.45
OBJECTIVE_LEGEND_CLEARANCE_AXES_FRACTION = 0.04


def setup_publication_objective_axis(
    axis,
    *,
    xlabel: str | None = None,
    ylabel: str | None = None,
    style: VisualizationStyle = DEFAULT_STYLE,
    grid: bool = True,
):
    """Apply shared publication objective-axis styling to an existing axis."""
    if xlabel is None:
        xlabel = PUBLICATION_TRAINABILITY_LABEL
    if ylabel is None:
        ylabel = PUBLICATION_EXPRESSIBILITY_LABEL
    if xlabel is not None:
        axis.set_xlabel(xlabel, fontsize=style.label_size)
    if ylabel is not None:
        axis.set_ylabel(ylabel, fontsize=style.label_size)
    axis.tick_params(labelsize=style.font_size)
    axis.set_axisbelow(True)
    if grid:
        axis.grid(True, alpha=style.grid_alpha)
    if hasattr(axis, "set_facecolor"):
        axis.set_facecolor(style.facecolor)
    return axis


def scatter_objective_series(
    axis,
    series: ObjectiveSeries,
    *,
    style: VisualizationStyle = DEFAULT_STYLE,
    label: str | None = None,
    **scatter_kwargs,
) -> tuple[Any, ...]:
    """Render semantic objective points grouped by their supplied visual role."""
    groups: dict[str, list] = {}
    for point in series.points:
        groups.setdefault(point.role or series.role, []).append(point)
    artists = []
    for role, points in groups.items():
        role_style = resolve_role_style(role, style=style)
        options = {
            "color": role_style.color,
            "marker": role_style.marker,
            "s": role_style.size,
            "alpha": role_style.alpha,
            "linewidths": role_style.linewidth,
        }
        options.update(scatter_kwargs)
        resolved_label = label if label is not None else (series.label if len(groups) == 1 else role)
        artists.append(
            axis.scatter(
                [point.x for point in points],
                [point.y for point in points],
                label=resolved_label,
                **options,
            ),
        )
    return tuple(artists)


def plot_frontier_line_series(
    axis,
    series: ObjectiveSeries,
    *,
    style: VisualizationStyle = DEFAULT_STYLE,
    label: str | None = None,
    **plot_kwargs,
) -> tuple[Any, ...]:
    """Render a frontier line using caller-supplied point order."""
    role_style = resolve_role_style(series.role, style=style)
    options = {
        "color": role_style.color,
        "marker": role_style.marker,
        "alpha": role_style.alpha,
        "linewidth": role_style.linewidth,
        "linestyle": role_style.linestyle,
    }
    options.update(plot_kwargs)
    return tuple(
        axis.plot(
            [point.x for point in series.points],
            [point.y for point in series.points],
            label=label if label is not None else series.label,
            **options,
        ),
    )


def resolve_lineage_color(
    lineage_id: str | None,
    *,
    style: VisualizationStyle = DEFAULT_STYLE,
) -> str:
    """Return a deterministic publication color for an already-supplied lineage ID."""
    palette = tuple(style.layer_colors) + tuple(style.extra_layer_colors)
    if not palette:
        raise VisualizationModelError("lineage color palette must not be empty.")
    if lineage_id is None:
        return palette[0]
    digest = hashlib.sha256(str(lineage_id).encode("utf-8")).hexdigest()
    return palette[int(digest[:8], 16) % len(palette)]


def ordered_lineage_color_map(lineage_order: Sequence[str]) -> dict[str, str]:
    """Return deterministic HSV colors for an explicit prepared lineage order."""
    order = tuple(str(item) for item in lineage_order)
    if len(set(order)) != len(order):
        raise VisualizationModelError("lineage_order must not contain duplicates.")
    count = len(order)
    if count == 0:
        return {}
    colors: dict[str, str] = {}
    for index, lineage_id in enumerate(order):
        red, green, blue = colorsys.hsv_to_rgb(index / count, 0.78, 0.85)
        colors[lineage_id] = _rgb_hex(red, green, blue)
    return colors


def grouped_categorical_bars(
    axis,
    serieses: tuple[BarSeries, ...] | list[BarSeries],
    *,
    style: VisualizationStyle = DEFAULT_STYLE,
    width: float = 0.8,
    **bar_kwargs,
) -> tuple[Any, ...]:
    """Render grouped categorical bars for aligned caller-supplied categories."""
    resolved = tuple(serieses)
    if not resolved:
        return ()
    categories = resolved[0].categories
    if any(series.categories != categories for series in resolved):
        raise VisualizationModelError("grouped bar series must share categories in the same order.")
    group_count = len(resolved)
    slot_width = float(width) / group_count
    base_positions = list(range(len(categories)))
    artists = []
    for series_index, series in enumerate(resolved):
        if any(value is None for value in series.values):
            raise VisualizationModelError("bar values must be available for rendering.")
        role_style = resolve_role_style(series.role, style=style)
        offset = (series_index - (group_count - 1) / 2.0) * slot_width
        options = {
            "color": role_style.color,
            "alpha": role_style.alpha,
            "label": series.label,
        }
        options.update(bar_kwargs)
        artists.append(
            axis.bar(
                [position + offset for position in base_positions],
                [float(value) for value in series.values if value is not None],
                width=slot_width,
                **options,
            ),
        )
    axis.set_xticks(base_positions)
    axis.set_xticklabels(categories, fontsize=style.font_size)
    return tuple(artists)


def apply_publication_legend(
    axis,
    *,
    style: VisualizationStyle = DEFAULT_STYLE,
    **legend_kwargs,
):
    """Apply the shared publication legend contract when labelled artists exist."""
    handles, labels = axis.get_legend_handles_labels()
    if not handles:
        return None
    options = {
        "frameon": style.legend_frame,
        "fontsize": style.legend_size,
        "loc": style.legend_location,
        "edgecolor": style.legend_edgecolor,
        "framealpha": style.legend_framealpha,
        "fancybox": style.legend_fancybox,
    }
    options.update(legend_kwargs)
    legend = axis.legend(handles, labels, **options)
    return style_publication_legend(legend, style=style)


def style_publication_legend(
    legend,
    *,
    style: VisualizationStyle = DEFAULT_STYLE,
    zorder: int = PUBLICATION_LEGEND_ZORDER,
):
    """Apply opaque/high-zorder publication legend styling to an existing legend."""
    if legend is None:
        return None
    legend.set_zorder(zorder)
    frame = legend.get_frame()
    frame.set_edgecolor(style.legend_edgecolor)
    frame.set_alpha(1.0)
    frame.set_facecolor(style.facecolor)
    return legend


def apply_bar_headroom(
    axis,
    values: Sequence[float],
    *,
    factor: float = BAR_HEADROOM_FACTOR,
) -> None:
    """Reserve deterministic y-axis headroom above prepared bar values."""
    finite_values = [float(value) for value in values if value is not None]
    maximum = max(finite_values, default=0.0)
    top = 1.0 if maximum <= 0.0 else maximum * float(factor)
    axis.set_ylim(0.0, top)


def apply_objective_vertical_headroom(
    axis,
    *,
    fraction: float = OBJECTIVE_VERTICAL_HEADROOM_FRACTION,
) -> None:
    """Reserve upper data-space margin for objective-space publication legends."""
    bottom, top = axis.get_ylim()
    span = top - bottom
    if span <= 0:
        return
    axis.set_ylim(bottom, top + span * float(fraction))


def reserve_objective_legend_clearance(
    axis,
    legend,
    data_y_values: Sequence[float] | None = None,
    *,
    axes_padding: float = OBJECTIVE_LEGEND_CLEARANCE_AXES_FRACTION,
) -> None:
    """Expand only the y-axis top until objective data clears an in-axis legend."""
    if legend is None:
        return
    finite_y = _finite_objective_y_values(axis, data_y_values)
    if not finite_y:
        return

    figure = axis.figure
    canvas = getattr(figure, "canvas", None)
    if canvas is None:
        return
    canvas.draw()
    renderer = canvas.get_renderer()
    legend_bbox = legend.get_window_extent(renderer=renderer)
    legend_axes_bbox = legend_bbox.transformed(axis.transAxes.inverted())
    legend_lower_axes = float(legend_axes_bbox.y0)
    if not math.isfinite(legend_lower_axes) or legend_lower_axes >= 1.0:
        return

    target_axes_y = legend_lower_axes - float(axes_padding)
    if target_axes_y <= 0.0:
        target_axes_y = max(legend_lower_axes * 0.5, 0.01)

    data_max = max(finite_y)
    data_axes_y = _data_y_to_axes_fraction(axis, data_max)
    if data_axes_y is None or data_axes_y <= target_axes_y:
        return

    bottom, top = axis.get_ylim()
    span = top - bottom
    if span <= 0 or data_max <= bottom:
        return

    required_top = bottom + (data_max - bottom) / target_axes_y
    if required_top > top:
        axis.set_ylim(bottom, required_top)
        canvas.draw()


def publication_table_figure_size(
    table: TableSpec,
    *,
    style: VisualizationStyle = DEFAULT_STYLE,
    width: float = 15.5,
    min_height: float = 4.0,
    row_height: float = 0.34,
    padding: float = 1.3,
) -> tuple[float, float]:
    """Return the publication table size with dynamic row-based height."""
    del style
    return (float(width), max(float(min_height), float(row_height) * len(table.rows) + float(padding)))


def plot_publication_table(
    table: TableSpec,
    *,
    style: VisualizationStyle = DEFAULT_STYLE,
    figure_size: tuple[float, float] | None = None,
    cellLoc: str = "left",
    colLoc: str = "left",
    loc: str = "center",
    **table_kwargs,
):
    """Create a publication table figure from a prepared table specification."""
    from .export import require_pyplot

    pyplot = require_pyplot()
    size = figure_size or publication_table_figure_size(table, style=style)
    figure, axis = pyplot.subplots(figsize=size, dpi=style.dpi)
    render_publication_table(
        axis,
        table,
        style=style,
        cellLoc=cellLoc,
        colLoc=colLoc,
        loc=loc,
        **table_kwargs,
    )
    return figure


def render_publication_table(
    axis,
    table: TableSpec,
    *,
    style: VisualizationStyle = DEFAULT_STYLE,
    **table_kwargs,
):
    """Render a generic publication table on an existing axis."""
    columns = list(table.columns)
    cell_text = []
    for row in table.rows:
        if hasattr(row, "get"):
            cell_text.append([row.get(column, "") for column in columns])
        else:
            if len(row) != len(columns):
                raise VisualizationModelError("table row lengths must match column count.")
            cell_text.append(list(row))
    axis.axis("off")
    options = {
        "cellText": cell_text,
        "colLabels": columns,
        "cellLoc": "center",
        "loc": "center",
    }
    options.update(table_kwargs)
    artist = axis.table(**options)
    artist.auto_set_font_size(False)
    artist.set_fontsize(style.font_size)
    return artist


def resolve_role_style(
    role: str,
    *,
    style: VisualizationStyle = DEFAULT_STYLE,
) -> SemanticRoleStyle:
    """Resolve a semantic role into a visual style without changing the role."""
    if role in style.role_styles:
        return style.role_styles[role]
    return SemanticRoleStyle(
        style.palette.get(role, style.palette.get("dominated", "#7A7A7A")),
        marker=style.markers.get(role, style.point_marker),
        size=36,
        alpha=0.9,
    )


def _rgb_hex(red: float, green: float, blue: float) -> str:
    return f"#{round(red * 255):02X}{round(green * 255):02X}{round(blue * 255):02X}"


def _finite_objective_y_values(axis, data_y_values: Sequence[float] | None) -> list[float]:
    raw_values: list[Any] = []
    if data_y_values is not None:
        raw_values.extend(data_y_values)
    else:
        for line in axis.lines:
            raw_values.extend(line.get_ydata())
        for collection in axis.collections:
            if hasattr(collection, "get_offsets"):
                raw_values.extend(offset[1] for offset in collection.get_offsets())

    finite_values = []
    for value in raw_values:
        try:
            resolved = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(resolved):
            finite_values.append(resolved)
    return finite_values


def _data_y_to_axes_fraction(axis, value: float) -> float | None:
    try:
        axes_point = axis.transAxes.inverted().transform(axis.transData.transform((0.0, float(value))))
    except (TypeError, ValueError):
        return None
    y_value = float(axes_point[1])
    return y_value if math.isfinite(y_value) else None


__all__ = [
    "BAR_HEADROOM_FACTOR",
    "OBJECTIVE_LEGEND_CLEARANCE_AXES_FRACTION",
    "OBJECTIVE_VERTICAL_HEADROOM_FRACTION",
    "PUBLICATION_OBJECTIVE_VERTICAL_HEADROOM_FRACTION",
    "PUBLICATION_LEGEND_ZORDER",
    "apply_bar_headroom",
    "apply_objective_vertical_headroom",
    "apply_publication_legend",
    "grouped_categorical_bars",
    "ordered_lineage_color_map",
    "plot_frontier_line_series",
    "plot_publication_table",
    "publication_table_figure_size",
    "render_publication_table",
    "reserve_objective_legend_clearance",
    "resolve_lineage_color",
    "resolve_role_style",
    "scatter_objective_series",
    "setup_publication_objective_axis",
    "style_publication_legend",
]
