"""Render compact publication figures from prepared semantic visualization data."""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

from matplotlib import pyplot

from verfeinert.ansatz_analyzer.visualization import (
    BarSeries,
    MetricSeries,
    ObjectivePoint,
    ObjectiveSeries,
    plot_generation_candidate_counts,
    plot_global_aggregate_metric,
    plot_individual_classification,
    save_publication_figure,
)


def _point(candidate_id: str, x: float, y: float, *, role: str = "candidate") -> ObjectivePoint:
    return ObjectivePoint(candidate_id=candidate_id, x=x, y=y, role=role)


def build_individual_figure():
    reference_eligible = ObjectiveSeries(
        points=(
            _point("reference-a", 0.08, 1.12, role="reference"),
            _point("reference-b", 0.15, 1.28, role="reference"),
            _point("reference-c", 0.25, 1.47, role="reference"),
            _point("reference-d", 0.37, 1.78, role="reference"),
        ),
        label="Prepared eligible reference",
    )
    reference_frontier = ObjectiveSeries(
        points=(
            _point("frontier-a", 0.08, 1.12, role="reference_frontier"),
            _point("frontier-b", 0.20, 1.36, role="reference_frontier"),
            _point("frontier-c", 0.37, 1.78, role="reference_frontier"),
        ),
        label="Prepared reference frontier",
    )
    classified_candidates = ObjectiveSeries(
        points=(
            _point("candidate-a", 0.12, 1.05, role="discarded"),
            _point("candidate-b", 0.22, 1.42, role="expressibility_improvement"),
            _point("candidate-c", 0.31, 1.56, role="trainability_improvement"),
            _point("candidate-d", 0.41, 1.88, role="new_pareto"),
        ),
        label="Prepared candidate classifications",
    )
    return plot_individual_classification(
        reference_eligible,
        reference_frontier,
        classified_candidates,
        threshold=0.2,
        x_label="Prepared objective X",
        y_label="Prepared objective Y",
    )


def build_evolution_figure():
    generated_counts = (
        MetricSeries(x=(0, 1, 2, 3), y=(8, 12, 15, 17), label="generated @ 0.2"),
    )
    selected_counts = (
        MetricSeries(x=(0, 1, 2, 3), y=(3, 4, 5, 5), label="selected @ 0.2"),
    )
    return plot_generation_candidate_counts(generated_counts, selected_counts)


def build_global_figure():
    metric_bars = (
        BarSeries(
            categories=("campaign-a", "campaign-b", "campaign-c"),
            values=(0.42, 0.55, 0.48),
            label="threshold 0.2",
        ),
        BarSeries(
            categories=("campaign-a", "campaign-b", "campaign-c"),
            values=(0.31, 0.44, 0.37),
            label="threshold 0.3",
        ),
    )
    return plot_global_aggregate_metric(metric_bars, y_label="Prepared aggregate score")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("/tmp/verfeinert-publication-visualization"),
        help="Directory for generated PNG/PDF/SVG publication figures.",
    )
    args = parser.parse_args(argv)

    output_root = args.output_root.expanduser().resolve(strict=False)
    figures = {
        "individual-classification": build_individual_figure(),
        "evolution-candidate-counts": build_evolution_figure(),
        "global-aggregate-metric": build_global_figure(),
    }

    written_paths: list[Path] = []
    try:
        for basename, figure in figures.items():
            exported = save_publication_figure(
                figure,
                output_root / basename,
                overwrite=True,
            )
            written_paths.extend(exported[fmt] for fmt in ("png", "pdf", "svg"))
    finally:
        for figure in figures.values():
            pyplot.close(figure)

    for path in written_paths:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
