"""Pareto visualization adapters and optional plotting."""

from __future__ import annotations

from typing import Any

from ..collections import AnalysisResultCollection, cost_value, metric_value
from ..pareto import ParetoResult
from .export import require_pyplot
from .styles import THESIS_STYLE, VisualizationStyle


def pareto_plot_data(source: AnalysisResultCollection | ParetoResult) -> list[dict[str, Any]]:
    """Return objective-space plot records from analyzer outputs."""
    if isinstance(source, ParetoResult):
        return [
            {
                "candidate_id": item.candidate_id,
                "expressibility": item.objective_values.get("expressibility"),
                "trainability": item.objective_values.get("trainability"),
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
                "expressibility": metric_value(document, "expressibility"),
                "trainability": metric_value(document, "trainability"),
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
    style: VisualizationStyle = THESIS_STYLE,
):
    """Plot trainability versus expressibility from analyzer-derived records."""
    pyplot = require_pyplot()
    data = pareto_plot_data(source)
    figure, axis = pyplot.subplots(figsize=style.figure_size, dpi=style.dpi)
    for is_frontier, label in ((False, "dominated"), (True, "frontier")):
        rows = [row for row in data if bool(row["is_frontier"]) is is_frontier]
        if not rows:
            continue
        axis.scatter(
            [row["trainability"] for row in rows],
            [row["expressibility"] for row in rows],
            label=label,
            marker=style.markers.get(label, "o"),
            color=style.palette.get(label),
        )
    axis.set_xlabel("Trainability")
    axis.set_ylabel("Expressibility")
    axis.legend(frameon=style.legend_frame, fontsize=style.legend_size)
    return figure


def _pareto_rank(document: dict[str, Any]) -> int | None:
    for classification in document.get("classifications", []):
        if classification.get("name") == "pareto_front":
            rank = classification.get("metadata", {}).get("pareto_rank")
            return int(rank) if rank is not None else None
    return None


__all__ = [
    "pareto_plot_data",
    "plot_pareto_front",
]
