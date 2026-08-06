"""Lineage visualization data adapters."""

from __future__ import annotations

from typing import Any

from ..collections import AnalysisResultCollection


def lineage_plot_data(collection: AnalysisResultCollection) -> list[dict[str, Any]]:
    """Return lineage-oriented records from result metadata when available."""
    if not isinstance(collection, AnalysisResultCollection):
        raise TypeError("collection must be an AnalysisResultCollection.")
    rows = []
    for document in collection:
        metadata = document.get("metadata", {})
        lineage = metadata.get("lineage", {}) if isinstance(metadata, dict) else {}
        rows.append(
            {
                "candidate_id": document["candidate_ref"]["candidate_id"],
                "parent_candidate_id": lineage.get("parent_candidate_id"),
                "root_candidate_id": lineage.get("root_candidate_id"),
                "generation": lineage.get("generation"),
            },
        )
    return rows


__all__ = ["lineage_plot_data"]
