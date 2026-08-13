"""Pareto visualization adapters and optional plotting."""

from __future__ import annotations

from typing import Any

from ..collections import AnalysisResultCollection, cost_value, metric_value
from ..pareto import ParetoResult
from .export import require_pyplot
from .styles import DEFAULT_STYLE, VisualizationStyle


def pareto_plot_data(
    source: AnalysisResultCollection | ParetoResult,
    *,
    x_metric: str = "trainability",
    y_metric: str = "expressibility",
    display_aliases: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Return objective-space plot records from analyzer outputs."""
    aliases = dict(display_aliases or {})
    if isinstance(source, ParetoResult):
        return [
            {
                "candidate_id": item.candidate_id,
                "display_label": aliases.get(item.candidate_id, item.candidate_id),
                x_metric: item.objective_values.get(x_metric),
                y_metric: item.objective_values.get(y_metric),
                "structural_cost": item.cost_value,
                "is_frontier": item.is_frontier,
                "pareto_rank": item.pareto_rank,
            }
            for item in source.candidates
        ]
    if isinstance(source, AnalysisResultCollection):
        return [
            {
                "candidate_id": document["candidate_ref"]["candidate_id"],
                "display_label": aliases.get(
                    document["candidate_ref"]["candidate_id"],
                    document["candidate_ref"]["candidate_id"],
                ),
                x_metric: metric_value(document, x_metric),
                y_metric: metric_value(document, y_metric),
                "structural_cost": cost_value(document, "structural_cost"),
                "is_frontier": any(
                    item.get("name") == "pareto_front" and item.get("label") == "frontier"
                    for item in document.get("classifications", [])
                ),
                "pareto_rank": _pareto_rank(document),
            }
            for document in source
        ]
    raise TypeError("source must be an AnalysisResultCollection or ParetoResult.")


def plot_pareto_front(
    source: AnalysisResultCollection | ParetoResult,
    *,
    style: VisualizationStyle = DEFAULT_STYLE,
    x_metric: str = "trainability",
    y_metric: str = "expressibility",
    display_aliases: dict[str, str] | None = None,
):
    """Plot trainability versus expressibility from analyzer-derived records."""
    pyplot = require_pyplot()
    data = pareto_plot_data(
        source,
        x_metric=x_metric,
        y_metric=y_metric,
        display_aliases=display_aliases,
    )
    figure, axis = pyplot.subplots(figsize=style.figure_size, dpi=style.dpi)
    for is_frontier, label in ((False, "dominated"), (True, "frontier")):
        rows = [
            row
            for row in data
            if bool(row["is_frontier"]) is is_frontier
            and row.get(x_metric) is not None
            and row.get(y_metric) is not None
        ]
        if not rows:
            continue
        axis.scatter(
            [row[x_metric] for row in rows],
            [row[y_metric] for row in rows],
            label=label,
            marker=style.markers.get(label, "o"),
            color=style.palette.get(label),
        )
    axis.set_xlabel(_axis_label(x_metric))
    axis.set_ylabel(_axis_label(y_metric))
    axis.legend(
        frameon=style.legend_frame,
        fontsize=style.legend_size,
        loc=style.legend_location,
    )
    return figure


def _pareto_rank(document: dict[str, Any]) -> int | None:
    for classification in document.get("classifications", []):
        if classification.get("name") == "pareto_front":
            rank = classification.get("metadata", {}).get("pareto_rank")
            return int(rank) if rank is not None else None
    return None


def _axis_label(metric_name: str) -> str:
    if metric_name == "trainability":
        return "Trainability\nT = (1/|P|) sum Var[d<H>/dtheta]"
    if metric_name == "expressibility":
        return "Expressibility\nE = -log10(D_KL)"
    return metric_name.replace("_", " ").title()


__all__ = [
    "pareto_plot_data",
    "plot_pareto_front",
]
