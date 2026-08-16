"""ComparisonResult visualization adapters and optional plotting."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..comparison import ComparisonResult
from .export import require_pyplot
from .pareto import _axis_label
from .primitives import apply_publication_legend, setup_publication_objective_axis
from .styles import DEFAULT_STYLE, VisualizationStyle


def comparison_plot_data(
    result: ComparisonResult | Mapping[str, Any],
    *,
    display_aliases: Mapping[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Return objective-space plot records from a ComparisonResult."""
    comparison = _comparison_result(result)
    aliases = dict(display_aliases or {})
    rows = []
    for item in comparison.rows:
        rows.append(
            {
                "comparison_id": comparison.comparison_id,
                "source_id": item.source_id,
                "source_role": item.source_role,
                "source_label": item.source_label,
                "candidate_id": item.candidate_id,
                "display_label": aliases.get(item.candidate_id, item.display_label),
                "objective_values": dict(item.objective_values),
                "trainability": item.objective_values.get("trainability"),
                "expressibility": item.objective_values.get("expressibility"),
                "score": item.score,
                "rank": item.rank,
                "is_global_pareto": item.is_global_pareto,
                "pareto_rank": item.pareto_rank,
                "cost_value": item.cost_value,
            },
        )
    return rows


def plot_comparison_objective_space(
    result: ComparisonResult | Mapping[str, Any],
    *,
    style: VisualizationStyle = DEFAULT_STYLE,
    x_metric: str = "trainability",
    y_metric: str = "expressibility",
    display_aliases: Mapping[str, str] | None = None,
):
    """Plot a persisted comparison in objective space."""
    pyplot = require_pyplot()
    comparison = _comparison_result(result)
    data = comparison_plot_data(comparison, display_aliases=display_aliases)
    figure, axis = pyplot.subplots(figsize=style.figure_size, dpi=style.dpi)
    scored = [
        row
        for row in data
        if row.get("score") is not None
        and row["objective_values"].get(x_metric) is not None
        and row["objective_values"].get(y_metric) is not None
    ]
    values = [row["score"] for row in scored]
    colorbar = None
    if values:
        scatter = axis.scatter(
            [row["objective_values"].get(x_metric) for row in scored],
            [row["objective_values"].get(y_metric) for row in scored],
            c=values,
            cmap=style.score_colormap,
            marker=style.markers.get("dominated", "o"),
            label="ranked candidates",
        )
        colorbar = figure.colorbar(scatter, ax=axis, fraction=0.022, pad=0.018)
        colorbar.set_label("Combined score")
    unscored = [
        row
        for row in data
        if row.get("score") is None
        and row["objective_values"].get(x_metric) is not None
        and row["objective_values"].get(y_metric) is not None
    ]
    if unscored:
        axis.scatter(
            [row["objective_values"].get(x_metric) for row in unscored],
            [row["objective_values"].get(y_metric) for row in unscored],
            color=style.palette.get("dominated"),
            marker=style.markers.get("dominated", "x"),
            label="unranked candidates",
        )
    frontier = [
        row
        for row in data
        if row.get("is_global_pareto")
        and row["objective_values"].get(x_metric) is not None
        and row["objective_values"].get(y_metric) is not None
    ]
    if frontier:
        axis.scatter(
            [row["objective_values"].get(x_metric) for row in frontier],
            [row["objective_values"].get(y_metric) for row in frontier],
            facecolors="none",
            edgecolors=style.palette.get("frontier"),
            marker=style.markers.get("frontier", "o"),
            s=90,
            linewidths=1.4,
            label="global Pareto",
        )
    setup_publication_objective_axis(
        axis,
        xlabel=_axis_label(x_metric),
        ylabel=_axis_label(y_metric),
        style=style,
    )
    apply_publication_legend(axis, style=style)
    figure._verfeinert_colorbar = colorbar  # type: ignore[attr-defined]
    return figure


def _comparison_result(result: ComparisonResult | Mapping[str, Any]) -> ComparisonResult:
    if isinstance(result, ComparisonResult):
        return result
    if isinstance(result, Mapping):
        return ComparisonResult.from_dict(result)
    raise TypeError("result must be a ComparisonResult or mapping.")


__all__ = [
    "comparison_plot_data",
    "plot_comparison_objective_space",
]
