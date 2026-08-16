"""Reusable low-level publication visualization primitives."""

from __future__ import annotations

from collections.abc import Sequence
import colorsys
import hashlib
from typing import Any

from .models import BarSeries, ObjectiveSeries, TableSpec, VisualizationModelError
from .styles import DEFAULT_STYLE, SemanticRoleStyle, VisualizationStyle


def setup_publication_objective_axis(
    axis,
    *,
    xlabel: str | None = None,
    ylabel: str | None = None,
    style: VisualizationStyle = DEFAULT_STYLE,
    grid: bool = True,
):
    """Apply shared publication objective-axis styling to an existing axis."""
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
    frame = legend.get_frame()
    frame.set_edgecolor(style.legend_edgecolor)
    frame.set_alpha(style.legend_framealpha)
    return legend


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


__all__ = [
    "apply_publication_legend",
    "grouped_categorical_bars",
    "ordered_lineage_color_map",
    "plot_frontier_line_series",
    "plot_publication_table",
    "publication_table_figure_size",
    "render_publication_table",
    "resolve_lineage_color",
    "resolve_role_style",
    "scatter_objective_series",
    "setup_publication_objective_axis",
]
