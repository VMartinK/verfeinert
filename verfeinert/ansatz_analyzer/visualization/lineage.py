"""Lineage visualization data adapters."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from typing import Any

from ..collections import AnalysisResultCollection
from .export import require_pyplot
from .styles import DEFAULT_STYLE, VisualizationStyle


def lineage_plot_data(source: AnalysisResultCollection | Mapping[str, Any]) -> list[dict[str, Any]]:
    """Return lineage-oriented records from structured result or evolution data."""
    if isinstance(source, Mapping):
        return _lineage_rows_from_evolution_run(source)
    if not isinstance(source, AnalysisResultCollection):
        raise TypeError("source must be an AnalysisResultCollection or EvolutionRun mapping.")
    rows = []
    for document in source:
        metadata = document.get("metadata", {})
        semantics = metadata.get("candidate_semantics", {}) if isinstance(metadata, dict) else {}
        lineage = semantics.get("lineage", {}) if isinstance(semantics, dict) else {}
        source_context = semantics.get("source_context", {}) if isinstance(semantics, dict) else {}
        rows.append(
            {
                "candidate_id": document["candidate_ref"]["candidate_id"],
                "parent_candidate_id": lineage.get("parent_candidate_id"),
                "root_candidate_id": lineage.get("root_candidate_id"),
                "generation": lineage.get("generation"),
                "layer": source_context.get("layer") if isinstance(source_context, dict) else None,
                "source": "analysis_result",
            },
        )
    return rows


def plot_lineage_summary(
    source: AnalysisResultCollection | Mapping[str, Any],
    *,
    style: VisualizationStyle = DEFAULT_STYLE,
):
    """Plot candidate counts per generation from structured lineage records."""
    pyplot = require_pyplot()
    data = lineage_plot_data(source)
    counts = Counter(row.get("generation") for row in data if row.get("generation") is not None)
    generations = sorted(counts)
    figure, axis = pyplot.subplots(figsize=style.compact_figure_size, dpi=style.dpi)
    axis.bar(
        generations,
        [counts[generation] for generation in generations],
        color=style.palette.get("lineage"),
    )
    axis.set_xlabel("Generation")
    axis.set_ylabel("Candidates")
    return figure


def _lineage_rows_from_evolution_run(document: Mapping[str, Any]) -> list[dict[str, Any]]:
    if document.get("schema_version") != "verfeinert.evolution_run.v1":
        raise TypeError("EvolutionRun mapping must use schema_version 'verfeinert.evolution_run.v1'.")
    rows: list[dict[str, Any]] = []
    for generation in document.get("generations", []):
        generation_index = generation.get("generation_index")
        parent_ids = tuple(
            ref.get("candidate_id")
            for ref in generation.get("parent_refs", [])
            if ref.get("candidate_id") is not None
        )
        survivor_ids = {
            ref.get("candidate_id")
            for ref in generation.get("survivor_refs", [])
        }
        archive_ids = {
            ref.get("candidate_id")
            for ref in generation.get("archive_refs", [])
        }
        rejected_ids = {
            ref.get("candidate_id")
            for ref in generation.get("rejected_refs", [])
        }
        for ref in generation.get("candidate_refs", []):
            candidate_id = ref.get("candidate_id")
            rows.append(
                {
                    "candidate_id": candidate_id,
                    "parent_candidate_id": parent_ids[0] if len(parent_ids) == 1 else None,
                    "parent_candidate_ids": list(parent_ids),
                    "root_candidate_id": None,
                    "generation": generation_index,
                    "layer": None,
                    "is_survivor": candidate_id in survivor_ids,
                    "is_archive": candidate_id in archive_ids,
                    "is_rejected": candidate_id in rejected_ids,
                    "source": "evolution_run",
                },
            )
    return rows


__all__ = [
    "lineage_plot_data",
    "plot_lineage_summary",
]
