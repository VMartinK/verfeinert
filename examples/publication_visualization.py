"""Render compact publication figures from prepared semantic visualization data."""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

from matplotlib import pyplot

from verfeinert.ansatz_analyzer.visualization import (
    ObjectivePoint,
    ObjectiveSeries,
    plot_campaign_frontiers,
    plot_frontier_evolution,
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
    )


def build_evolution_figure():
    frontiers = (
        ObjectiveSeries(
            points=(
                _point("generation-0-a", 0.10, 1.02),
                _point("generation-0-b", 0.22, 1.20),
            ),
            label="generation 0",
        ),
        ObjectiveSeries(
            points=(
                _point("generation-1-a", 0.14, 1.18),
                _point("generation-1-b", 0.30, 1.48),
            ),
            label="generation 1",
        ),
        ObjectiveSeries(
            points=(
                _point("generation-2-a", 0.18, 1.34),
                _point("generation-2-b", 0.42, 1.82),
            ),
            label="generation 2",
        ),
    )
    return plot_frontier_evolution(frontiers, threshold=0.2, threshold_color="#1565C0")


def build_global_figure():
    campaign_frontiers = (
        ObjectiveSeries(
            points=(
                _point("campaign-a-1", 0.12, 1.18),
                _point("campaign-a-2", 0.26, 1.42),
                _point("campaign-a-3", 0.44, 1.76),
            ),
            role="campaign",
            label="campaign A",
            score=0.58,
        ),
        ObjectiveSeries(
            points=(
                _point("campaign-b-1", 0.16, 1.10),
                _point("campaign-b-2", 0.32, 1.55),
                _point("campaign-b-3", 0.50, 1.92),
            ),
            role="campaign",
            label="campaign B",
            score=0.81,
        ),
        ObjectiveSeries(
            points=(
                _point("baseline-1", 0.08, 1.00),
                _point("baseline-2", 0.24, 1.26),
            ),
            role="reference",
            label="baseline",
        ),
    )
    global_frontier = ObjectiveSeries(
        points=(
            _point("global-1", 0.18, 1.34),
            _point("global-2", 0.38, 1.68),
            _point("global-3", 0.56, 2.02),
        ),
        label="global optimized",
    )
    return plot_campaign_frontiers(campaign_frontiers, global_frontier, threshold=0.2)


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
        "evolution-frontier-evolution": build_evolution_figure(),
        "global-campaign-frontiers": build_global_figure(),
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
