"""Ranking visualization adapters and optional plotting."""

from __future__ import annotations

from typing import Any

from ..ranking import RankingResult
from .export import require_pyplot
from .primitives import setup_publication_objective_axis
from .styles import DEFAULT_STYLE, VisualizationStyle


def ranking_plot_data(result: RankingResult) -> list[dict[str, Any]]:
    """Return ranking plot records from a RankingResult."""
    if not isinstance(result, RankingResult):
        raise TypeError("result must be a RankingResult.")
    return [
        {
            "rank": item.rank,
            "candidate_id": item.candidate_id,
            "score": item.score,
            "status": item.status,
        }
        for item in result.ranked_candidates
        if item.rank is not None
    ]


def plot_ranking_scores(
    result: RankingResult,
    *,
    style: VisualizationStyle = DEFAULT_STYLE,
):
    """Plot ranking score by rank from derived analyzer output."""
    pyplot = require_pyplot()
    data = ranking_plot_data(result)
    figure, axis = pyplot.subplots(figsize=style.figure_size, dpi=style.dpi)
    axis.plot(
        [row["rank"] for row in data],
        [row["score"] for row in data],
        marker=style.markers.get("ranking", "o"),
        color=style.palette.get("ranking"),
    )
    setup_publication_objective_axis(axis, xlabel="Rank", ylabel="Score", style=style)
    return figure


__all__ = [
    "plot_ranking_scores",
    "ranking_plot_data",
]
