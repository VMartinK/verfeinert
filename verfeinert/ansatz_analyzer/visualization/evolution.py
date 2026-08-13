"""Evolution visualization data adapters."""

from __future__ import annotations

from typing import Any

from ..collections import AnalysisResultCollection, cost_value, metric_value


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


__all__ = ["evolution_plot_data"]
