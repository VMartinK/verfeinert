# Visualization

## Overview

`verfeinert.ansatz_analyzer.visualization` is the optional publication
visualization endpoint for analyzer-derived artifacts and prepared semantic
plot data. Matplotlib is loaded lazily by renderers and export helpers, so
non-visual imports remain available without the visualization extra.

The publication data flow is:

```text
persisted/prepared scientific results
    ->
semantic visualization data
    ->
renderers
    ->
publication export
```

The package supports legacy plot-data adapters for analyzer artifacts and the
v0.3.x publication renderers for prepared semantic data. Public figure APIs use
descriptive names such as `plot_individual_classification` and
`plot_global_pareto`; notebook-local figure labels are not public API concepts.

## Scientific Boundary

Visualization consumes scientific results that have already been computed,
classified, ranked, selected, or otherwise prepared by upstream code. It does
not compute or infer:

- Trainability;
- Expressibility;
- structural cost;
- Pareto membership;
- dominance;
- combined scientific score;
- ranking;
- selection;
- evolution;
- top-lineage selection.

Allowed visual-only work includes artist ordering, axis and layout calculation,
bar offsets, legend composition, deterministic color assignment, dynamic table
height from prepared row count, and colormap normalization of an already
computed scalar such as a prepared `ObjectivePoint.score` or
`ObjectiveSeries.score`.

Visualization modules must not depend on notebooks, `Thesis_Data_Processing`,
QNode execution, generated local packages, or repository-local scientific
outputs.

## Semantic Visualization Models

Semantic models live in `verfeinert.ansatz_analyzer.visualization.models`.
They are frozen lightweight records used by renderers. They preserve input
coordinates and ordering; they do not classify or compute scientific values.

```python
ObjectivePoint(
    candidate_id: str,
    x: float,
    y: float,
    display_label: str | None = None,
    role: str = "candidate",
    layer: int | None = None,
    lineage_id: str | None = None,
    generation: int | None = None,
    score: float | None = None,
    structural_cost: float | None = None,
    metadata: Mapping[str, Any] = ...,
)

ObjectiveSeries(
    points: tuple[ObjectivePoint, ...] = (),
    role: str = "series",
    label: str | None = None,
    threshold: float | None = None,
    generation: int | None = None,
    source_id: str | None = None,
    *,
    score: float | None = None,
)

MetricSeries(
    x: tuple[Any, ...],
    y: tuple[float | None, ...],
    role: str = "metric",
    label: str | None = None,
    threshold: float | None = None,
)

BarSeries(
    categories: tuple[str, ...],
    values: tuple[float | None, ...],
    role: str = "bar",
    label: str | None = None,
)

TableSpec(
    columns: tuple[str, ...],
    rows: tuple[Mapping[str, Any] | tuple[Any, ...], ...],
)
```

## Publication Style And Layouts

`DEFAULT_STYLE` is the normal publication style. There is no special thesis
mode. It is an instance of:

```python
SemanticRoleStyle(
    color: str,
    marker: str = "o",
    size: float = 36.0,
    alpha: float = 1.0,
    linewidth: float = 1.0,
    linestyle: str = "-",
)

VisualizationStyle(
    font_family: str = "DejaVu Sans",
    font_size: int = 11,
    title_size: int = 13,
    label_size: int = 12,
    legend_size: int = 10,
    figure_size: tuple[float, float] = (8.0, 4.5),
    compact_figure_size: tuple[float, float] = (6.0, 4.0),
    wide_figure_size: tuple[float, float] = (13.6, 7.65),
    dpi: int = 600,
    score_colormap: str = "plasma",
    frontier_colors: tuple[str, ...] = ("#C62828", "#1565C0", "#1B5E20"),
    reference_frontier_colors: tuple[str, ...] = ("#111111", "#666666", "#AAAAAA"),
    layer_colors: tuple[str, ...] = ("#E69F00", "#0072B2", "#009E73"),
    extra_layer_colors: tuple[str, ...] = ("#CC79A7", "#999999", "#D55E00", "#00796B"),
    point_marker: str = "o",
    grid_alpha: float = 0.18,
    legend_frame: bool = True,
    legend_location: str = "upper right",
    legend_edgecolor: str = "#B0B0B0",
    legend_framealpha: float = 0.95,
    legend_fancybox: bool = False,
    annotation_text_color: str = "0.15",
    export_format: str = "png",
    export_formats: tuple[str, ...] = ("png", "pdf", "svg"),
    publication_export_formats: tuple[str, ...] = ("png", "pdf", "svg"),
    bbox_inches: str = "tight",
    transparent: bool = False,
    facecolor: str = "white",
)
```

`PublicationLayouts` provides named figure sizes:

```python
PublicationLayouts(
    standard=(8.0, 4.5),
    generation_counts=(13.0, 5.2),
    global_standard=(12.8, 7.2),
    global_wide=(13.6, 7.65),
    global_contribution=(16.0, 9.0),
    global_lineage=(18.0, 9.5),
    table_width=12.8,
    table_min_height=1.2,
    table_header_height=0.45,
    table_row_height=0.32,
)
```

Style carries visual roles and palettes only. Numeric scientific thresholds are
explicit data, not keys in `DEFAULT_STYLE`.

Objective-space publication renderers use canonical visualization-only labels
when callers do not pass explicit `x_label` or `y_label` values:

```python
PUBLICATION_TRAINABILITY_LABEL
PUBLICATION_EXPRESSIBILITY_LABEL
publication_objective_label(metric_name)
```

The default trainability label is Hamiltonian-agnostic and uses generic `T(H)`.
Explicit caller labels still override the defaults. Publication legends are
styled above plotted data with an opaque frame using the publication facecolor.

## Individual Campaign Renderers

Individual campaign renderers consume prepared objective-space points,
frontiers, layer labels, lineage labels, and count series.

```python
plot_individual_classification(
    reference_eligible: ObjectiveSeries,
    reference_frontier: ObjectiveSeries,
    classified_candidates: ObjectiveSeries,
    threshold: float,
    *,
    x_label: str | None = None,
    y_label: str | None = None,
    style: VisualizationStyle = DEFAULT_STYLE,
)

plot_individual_joint_frontiers(
    frontiers: Sequence[ObjectiveSeries],
    *,
    x_label: str | None = None,
    y_label: str | None = None,
    xlim: tuple[float, float] | None = None,
    ylim: tuple[float, float] | None = None,
    style: VisualizationStyle = DEFAULT_STYLE,
)

plot_individual_frontier_comparison(
    reference_frontiers: Sequence[ObjectiveSeries],
    primary_frontiers: Sequence[ObjectiveSeries],
    *,
    x_label: str | None = None,
    y_label: str | None = None,
    style: VisualizationStyle = DEFAULT_STYLE,
)

plot_individual_by_layer(
    candidates: ObjectiveSeries,
    reference_frontiers: Sequence[ObjectiveSeries],
    *,
    layer_order: Sequence[int] | None = None,
    x_label: str | None = None,
    y_label: str | None = None,
    style: VisualizationStyle = DEFAULT_STYLE,
)

plot_individual_by_lineage(
    candidates: ObjectiveSeries,
    reference_frontiers: Sequence[ObjectiveSeries],
    lineage_order: Sequence[str],
    *,
    x_label: str | None = None,
    y_label: str | None = None,
    xlim: tuple[float, float] | None = None,
    ylim: tuple[float, float] | None = None,
    style: VisualizationStyle = DEFAULT_STYLE,
)

plot_individual_pareto_by_lineage(
    counts: BarSeries,
    *,
    lineage_order: Sequence[str] | None = None,
    style: VisualizationStyle = DEFAULT_STYLE,
)
```

Lineage colors use `ordered_lineage_color_map(lineage_order)`. The order is
caller-supplied and is not inferred from candidate IDs.

## Evolution Renderers

Evolution renderers consume prepared generation counts, prepared metric series,
prepared frontiers, prepared improvement roles, and prepared lineage count
panels. They do not run evolution or infer frontier membership.

```python
MetricPanelSpec(title: str, y_label: str, series: tuple[MetricSeries, ...])
LineageBarPanelSpec(title: str, counts: BarSeries)

plot_generation_candidate_counts(
    generated_counts: Sequence[MetricSeries],
    selected_counts: Sequence[MetricSeries],
    *,
    x_label: str = "Generation",
    style: VisualizationStyle = DEFAULT_STYLE,
)

plot_generation_metric_grid(
    panels: Sequence[MetricPanelSpec],
    *,
    x_label: str = "Generation",
    style: VisualizationStyle = DEFAULT_STYLE,
)

plot_frontier_evolution(
    frontiers: Sequence[ObjectiveSeries],
    threshold: float,
    *,
    x_label: str | None = None,
    y_label: str | None = None,
    threshold_color: str | None = None,
    style: VisualizationStyle = DEFAULT_STYLE,
)

plot_frontier_generation_comparison(
    previous_frontier: ObjectiveSeries,
    current_frontier: ObjectiveSeries,
    improvement_points: ObjectiveSeries,
    *,
    reference_frontier: ObjectiveSeries | None = None,
    threshold: float | None = None,
    generation: int | None = None,
    x_label: str | None = None,
    y_label: str | None = None,
    style: VisualizationStyle = DEFAULT_STYLE,
)

plot_final_frontier_vs_eligible(
    eligible_candidates: ObjectiveSeries,
    final_frontier: ObjectiveSeries,
    threshold: float,
    *,
    x_label: str | None = None,
    y_label: str | None = None,
    style: VisualizationStyle = DEFAULT_STYLE,
)

plot_evolution_by_layer(
    candidates: ObjectiveSeries,
    final_frontiers: Sequence[ObjectiveSeries],
    *,
    layer_order: Sequence[int] | None = None,
    x_label: str | None = None,
    y_label: str | None = None,
    style: VisualizationStyle = DEFAULT_STYLE,
)

plot_lineage_evolution(
    panels: Sequence[LineageBarPanelSpec],
    lineage_order: Sequence[str],
    threshold: float,
    *,
    style: VisualizationStyle = DEFAULT_STYLE,
)

plot_evolution_ranking_table(
    table: TableSpec,
    *,
    style: VisualizationStyle = DEFAULT_STYLE,
)
```

`plot_generation_metric_grid` is reusable for total-population metrics,
generation-local frontier metrics, and optimized-frontier metrics as long as
the four prepared panels are supplied explicitly.
Publication grids draw no per-axis titles; prepare `MetricPanelSpec.y_label`
values such as `Mean combined score`, `Mean expressibility`,
`Mean trainability`, and `Mean structural cost` upstream.

`plot_frontier_evolution` keeps all generation frontiers in one call on the
same cost-threshold color. Prepared generation order is rendered through
monotonically increasing alpha, with the final prepared frontier fully opaque.
Use `threshold_color` when the publication preparation layer has assigned a
specific cost-threshold color.

## Global Analysis Renderers

Global renderers consume prepared campaign/source bars, prepared eligible
points, prepared campaign and global frontiers, prepared scores, prepared
lineage counts, and prepared table rows.

```python
plot_global_cost_eligibility(
    eligibility: Sequence[BarSeries],
    *,
    style: VisualizationStyle = DEFAULT_STYLE,
)

plot_global_pareto(
    eligible_by_layer: ObjectiveSeries,
    global_frontiers: Sequence[ObjectiveSeries],
    *,
    layer_order: Sequence[int] | None = None,
    x_label: str | None = None,
    y_label: str | None = None,
    style: VisualizationStyle = DEFAULT_STYLE,
)

plot_campaign_frontiers(
    campaign_frontiers: Sequence[ObjectiveSeries],
    global_frontier: ObjectiveSeries,
    threshold: float,
    *,
    score_points: ObjectiveSeries | None = None,
    x_label: str | None = None,
    y_label: str | None = None,
    style: VisualizationStyle = DEFAULT_STYLE,
)

plot_global_pareto_score_map(
    background: ObjectiveSeries,
    campaign_pareto: ObjectiveSeries,
    global_frontier: ObjectiveSeries,
    global_frontier_members: ObjectiveSeries,
    *,
    threshold: float,
    reference_frontier: ObjectiveSeries | None = None,
    x_label: str | None = None,
    y_label: str | None = None,
    style: VisualizationStyle = DEFAULT_STYLE,
)

plot_global_aggregate_metric(
    metric_bars: Sequence[BarSeries],
    *,
    y_label: str,
    style: VisualizationStyle = DEFAULT_STYLE,
)

plot_global_contributions(
    campaign_frontier_members: Sequence[BarSeries],
    global_frontier_members: Sequence[BarSeries],
    *,
    campaign_y_label: str = "Campaign frontier members",
    global_y_label: str = "Global optimized frontier members",
    style: VisualizationStyle = DEFAULT_STYLE,
)

plot_global_lineages(
    lineage_order: Sequence[str],
    eligible_counts: BarSeries,
    campaign_frontier_counts: BarSeries,
    global_frontier_member_counts: BarSeries,
    selected_lineage_points: ObjectiveSeries,
    global_frontier: ObjectiveSeries,
    *,
    threshold: float,
    x_label: str | None = None,
    y_label: str | None = None,
    style: VisualizationStyle = DEFAULT_STYLE,
)

plot_global_ranking_table(
    table: TableSpec,
    *,
    style: VisualizationStyle = DEFAULT_STYLE,
)
```

`plot_campaign_frontiers` colors non-reference campaign frontiers by the
prepared aggregate `ObjectiveSeries.score` value using the configured score
colormap and a `Mean combined score` colorbar. Reference/baseline frontiers stay
dashed reference lines, and the global optimized frontier remains black.
The legacy `score_points` keyword is still accepted for patch-release
compatibility but is deprecated for G_C and no longer draws auxiliary score
points.

Other score-colored renderers use `ObjectivePoint.score` values supplied by the
caller. Renderers may visually normalize prepared scalars for a Matplotlib
colormap, but they do not compute scores.

Global aggregate and contribution bar renderers reserve deterministic vertical
headroom above the maximum prepared bar. `plot_global_lineages` explains bold
left-panel numeric annotations as global-frontier member counts and adds a
compact right-panel legend for rendered lineages plus the global frontier.

## save_figure And save_publication_figure

`save_figure` preserves the legacy single-file export behavior:

```python
save_figure(
    figure,
    path: str | Path,
    *,
    config: FigureExportConfig | None = None,
    input_roots=(),
    **savefig_kwargs,
) -> Path
```

`save_publication_figure` writes one semantic basename to one or more
publication formats:

```python
save_publication_figure(
    figure,
    basename: str | Path,
    *,
    formats: Iterable[str] = ("png", "pdf", "svg"),
    config: FigureExportConfig | None = None,
    input_roots=(),
    overwrite: bool = False,
    **savefig_kwargs,
) -> dict[str, Path]
```

The basename is supplied without an extension. Formats are normalized to lower
case and must be selected from `png`, `pdf`, and `svg`. Duplicate or malformed
formats are rejected before any file is written. Existing destination files
also fail closed when `overwrite=False`. Both helpers use the same guarded
caller-owned path policy.

`FigureExportConfig(dpi=600, bbox_inches="tight", transparent=False,
facecolor="white")` is JSON-safe via `to_dict()`.

## Prepared-Data Example

```python
from pathlib import Path

import matplotlib
matplotlib.use("Agg")

from verfeinert.ansatz_analyzer.visualization import (
    BarSeries,
    MetricSeries,
    ObjectivePoint,
    ObjectiveSeries,
    plot_global_aggregate_metric,
    plot_individual_classification,
    plot_generation_candidate_counts,
    save_publication_figure,
)

reference = ObjectiveSeries(
    points=(
        ObjectivePoint("ref-a", 0.10, 1.00),
        ObjectivePoint("ref-b", 0.20, 1.25),
    ),
    label="eligible reference",
)
frontier = ObjectiveSeries(
    points=(
        ObjectivePoint("front-a", 0.10, 1.00),
        ObjectivePoint("front-b", 0.30, 1.55),
    ),
    label="reference frontier",
)
candidates = ObjectiveSeries(
    points=(
        ObjectivePoint("cand-a", 0.24, 1.35, role="expressibility_improvement"),
        ObjectivePoint("cand-b", 0.36, 1.70, role="new_pareto"),
    ),
    label="classified candidates",
)

figure = plot_individual_classification(
    reference,
    frontier,
    candidates,
    threshold=0.2,
    x_label="Prepared objective X",
    y_label="Prepared objective Y",
)
save_publication_figure(figure, Path("figures") / "individual-classification")
```

See `examples/publication_visualization.py` for a compact executable example
that renders one Individual, one Evolution, and one Global figure from
synthetic prepared data.

## Safe Extension Guidance

When adding visualization behavior:

- accept prepared semantic data or already-computed public analyzer artifacts;
- keep renderer calls explicit and composable;
- keep Matplotlib imports lazy;
- preserve canonical candidate IDs, prepared coordinates, labels, thresholds,
  lineage order, and row order;
- keep scientific thresholds in input data, not in style mappings;
- add structural tests for figure size, axes, artists, coordinates, legends,
  and table rows;
- add scientific-boundary tests when a renderer could accidentally recompute
  metrics, Pareto membership, ranking, selection, or evolution state.

Do not introduce notebook runtime dependencies, hard-code campaign IDs,
infer semantics from candidate-name string parsing, or hide multiplicity inside
generic primitives.
