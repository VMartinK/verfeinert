"""Workflow-level orchestration for publication visualization profiles."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from verfeinert.ansatz_analyzer import AnalysisResultCollection, validate_analysis_result_document
from verfeinert.ansatz_analyzer.collections import cost_value, metric_value
from verfeinert.ansatz_evolver import read_evolution_run_json
from verfeinert.core.io import read_json

from .config import WorkflowConfig, WorkflowConfigError, WorkflowVisualizationConfig


_INDIVIDUAL_PUBLICATION_FIGURES = (
    "individual_by_layer",
    "individual_by_lineage",
    "individual_pareto_by_lineage",
)
_EVOLUTION_PUBLICATION_FIGURES = (
    "evolution_candidate_counts",
    "evolution_by_layer",
)


def write_workflow_publication_visualizations(
    *,
    config: WorkflowConfig,
    derived_root: Path,
    analysis_collection: AnalysisResultCollection | None,
    pareto_result: Any | None,
    evolution_source: str | Path | Mapping[str, Any] | None,
    input_roots: Sequence[str | Path],
) -> tuple[Path, ...]:
    """Write configured workflow publication figures from canonical artifacts."""
    if config.visualization.profile != "publication":
        return ()
    figures = _publication_figures(
        config.visualization,
        campaign_type=config.campaign_type,
        evolution_source=evolution_source,
    )
    if not figures:
        raise WorkflowConfigError(
            "publication visualization figure_set='global' requires explicit "
            "prepared global artifacts outside one run-scoped WorkflowRunner.",
        )

    analysis_documents = _analysis_documents_for_visualization(
        analysis_collection=analysis_collection,
        evolution_source=evolution_source,
    )
    objective_series = _objective_series(analysis_documents)
    evolution_document, _base = _evolution_document_with_base(evolution_source)

    paths: list[Path] = []
    for figure_name in figures:
        figure = _publication_figure(
            figure_name,
            objective_series=objective_series,
            pareto_result=pareto_result,
            evolution_document=evolution_document,
        )
        if figure is None:
            continue
        try:
            paths.extend(
                _save_publication_figure(
                    figure,
                    config=config,
                    derived_root=derived_root,
                    figure_name=figure_name,
                    input_roots=input_roots,
                ),
            )
        finally:
            _close_figure(figure)
    return tuple(paths)


def _publication_figures(
    visualization: WorkflowVisualizationConfig,
    *,
    campaign_type: str,
    evolution_source: str | Path | Mapping[str, Any] | None,
) -> tuple[str, ...]:
    if visualization.figures:
        return visualization.figures
    if visualization.figure_set == "individual":
        return _INDIVIDUAL_PUBLICATION_FIGURES
    if visualization.figure_set == "evolution":
        return _EVOLUTION_PUBLICATION_FIGURES
    if visualization.figure_set == "global":
        return ()
    if evolution_source is not None or campaign_type == "evolutionary":
        return _EVOLUTION_PUBLICATION_FIGURES
    return _INDIVIDUAL_PUBLICATION_FIGURES


def _publication_figure(
    figure_name: str,
    *,
    objective_series,
    pareto_result: Any | None,
    evolution_document: Mapping[str, Any] | None,
):
    from verfeinert.ansatz_analyzer.visualization import (
        BarSeries,
        MetricSeries,
        plot_evolution_by_layer,
        plot_generation_candidate_counts,
        plot_individual_by_layer,
        plot_individual_by_lineage,
        plot_individual_pareto_by_lineage,
    )

    if figure_name == "individual_by_layer":
        if not objective_series.points:
            return None
        return plot_individual_by_layer(objective_series, ())
    if figure_name == "individual_by_lineage":
        if not objective_series.points:
            return None
        lineage_order = _lineage_order(objective_series.points)
        if not lineage_order:
            return None
        return plot_individual_by_lineage(objective_series, (), lineage_order)
    if figure_name == "individual_pareto_by_lineage":
        counts = _pareto_lineage_counts(
            objective_series=objective_series,
            pareto_result=pareto_result,
            bar_series_type=BarSeries,
        )
        if counts is None:
            return None
        return plot_individual_pareto_by_lineage(counts, lineage_order=counts.categories)
    if figure_name == "evolution_candidate_counts":
        if evolution_document is None:
            return None
        generated, selected = _generation_count_series(
            evolution_document,
            metric_series_type=MetricSeries,
        )
        if not generated or not selected:
            return None
        return plot_generation_candidate_counts(generated, selected)
    if figure_name == "evolution_by_layer":
        if not objective_series.points:
            return None
        return plot_evolution_by_layer(objective_series, ())
    raise WorkflowConfigError(f"unsupported publication visualization figure: {figure_name}")


def _analysis_documents_for_visualization(
    *,
    analysis_collection: AnalysisResultCollection | None,
    evolution_source: str | Path | Mapping[str, Any] | None,
) -> tuple[dict[str, Any], ...]:
    documents: list[dict[str, Any]] = []
    seen_candidates: set[str] = set()

    def append(document: Mapping[str, Any]) -> None:
        validated = validate_analysis_result_document(document)
        candidate_id = validated["candidate_ref"]["candidate_id"]
        if candidate_id in seen_candidates:
            return
        seen_candidates.add(candidate_id)
        documents.append(validated)

    if analysis_collection is not None:
        for document in analysis_collection.documents:
            append(document)

    evolution_document, base = _evolution_document_with_base(evolution_source)
    if evolution_document is not None:
        for generation in evolution_document.get("generations", ()):
            for ref in generation.get("analysis_result_refs", ()):
                uri = ref.get("analysis_result_uri")
                if not isinstance(uri, str) or not uri:
                    continue
                path = Path(uri).expanduser()
                if not path.is_absolute() and base is not None:
                    path = base / path
                if path.is_file():
                    append(read_json(path))
    return tuple(documents)


def _objective_series(documents: Sequence[Mapping[str, Any]]):
    from verfeinert.ansatz_analyzer.visualization import ObjectivePoint, ObjectiveSeries

    points = []
    for document in documents:
        trainability = metric_value(document, "trainability")
        expressibility = metric_value(document, "expressibility")
        if trainability is None or expressibility is None:
            continue
        candidate_id = document["candidate_ref"]["candidate_id"]
        semantics = _candidate_semantics(document)
        lineage = dict(semantics.get("lineage", {}))
        source_context = dict(semantics.get("source_context", {}))
        lineage_id = (
            lineage.get("root_candidate_id")
            or lineage.get("parent_candidate_id")
            or candidate_id
        )
        points.append(
            ObjectivePoint(
                candidate_id=candidate_id,
                x=float(trainability),
                y=float(expressibility),
                layer=_int_or_none(
                    source_context.get(
                        "layer",
                        source_context.get("layer_count", lineage.get("generation")),
                    ),
                ),
                lineage_id=str(lineage_id),
                generation=_int_or_none(lineage.get("generation")),
                structural_cost=cost_value(document, "structural_cost"),
            ),
        )
    return ObjectiveSeries(points=tuple(points), label="Analyzed candidates")


def _pareto_lineage_counts(
    *,
    objective_series,
    pareto_result: Any | None,
    bar_series_type,
):
    if pareto_result is None:
        return None
    frontier_ids = set(getattr(pareto_result, "frontier_candidate_ids", ()))
    if not frontier_ids:
        return None
    lineage_order = _lineage_order(objective_series.points)
    if not lineage_order:
        return None
    counts = {lineage_id: 0 for lineage_id in lineage_order}
    for point in objective_series.points:
        if point.candidate_id in frontier_ids and point.lineage_id in counts:
            counts[point.lineage_id] += 1
    if not any(counts.values()):
        return None
    return bar_series_type(
        categories=lineage_order,
        values=tuple(counts[lineage_id] for lineage_id in lineage_order),
        label="Pareto-optimal candidates",
    )


def _generation_count_series(
    evolution_document: Mapping[str, Any],
    *,
    metric_series_type,
) -> tuple[tuple[Any, ...], tuple[Any, ...]]:
    generations = tuple(evolution_document.get("generations", ()))
    if not generations:
        return (), ()
    x_values = tuple(generation.get("generation_index") for generation in generations)
    generated = metric_series_type(
        x=x_values,
        y=tuple(len(generation.get("candidate_refs", ())) for generation in generations),
        label="generated",
    )
    selected = metric_series_type(
        x=x_values,
        y=tuple(len(generation.get("survivor_refs", ())) for generation in generations),
        label="selected",
    )
    return (generated,), (selected,)


def _save_publication_figure(
    figure,
    *,
    config: WorkflowConfig,
    derived_root: Path,
    figure_name: str,
    input_roots: Sequence[str | Path],
) -> tuple[Path, ...]:
    from verfeinert.ansatz_analyzer.visualization import save_publication_figure

    base = derived_root / config.run_id / "figures" / "publication" / figure_name
    base.parent.mkdir(parents=True, exist_ok=True)
    exported = save_publication_figure(
        figure,
        base,
        formats=config.visualization.formats,
        overwrite=config.visualization.overwrite,
        input_roots=input_roots,
    )
    return tuple(exported[fmt] for fmt in config.visualization.formats)


def _evolution_document_with_base(
    evolution_source: str | Path | Mapping[str, Any] | None,
) -> tuple[dict[str, Any] | None, Path | None]:
    if evolution_source is None:
        return None, None
    if isinstance(evolution_source, Mapping):
        return dict(evolution_source), None
    path = Path(evolution_source).expanduser()
    return read_evolution_run_json(path), path.parent


def _candidate_semantics(document: Mapping[str, Any]) -> dict[str, Any]:
    metadata = document.get("metadata", {})
    if not isinstance(metadata, Mapping):
        return {}
    semantics = metadata.get("candidate_semantics", {})
    return dict(semantics) if isinstance(semantics, Mapping) else {}


def _lineage_order(points: Sequence[Any]) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            str(point.lineage_id)
            for point in points
            if point.lineage_id is not None
        ),
    )


def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _close_figure(figure) -> None:
    clear = getattr(figure, "clear", None)
    if callable(clear):
        clear()


__all__ = ["write_workflow_publication_visualizations"]
