# Visualization System

## Role

`verfeinert.ansatz_analyzer.visualization` is an optional endpoint layer over
analyzer outputs. It consumes `AnalysisResultCollection`, `ParetoResult`,
`RankingResult`, `ComparisonResult`, and EvolutionRun JSON mappings. It does
not compute scientific metrics, compare campaigns, classify Pareto frontiers,
rank candidates, execute QNodes, rerun evolution, or read notebooks.

## Package Structure

```text
visualization/
    styles/
        default.py
    pareto.py
    ranking.py
    comparison.py
    lineage.py
    evolution.py
    export.py
```

The style module centralizes fonts, figure dimensions, palettes, markers,
legend behavior, and export defaults. The current public style constant is
`DEFAULT_STYLE`, a neutral publication-oriented default. Thesis-specific style
names and modes are not public API.

## Dependency Policy

Matplotlib is optional and loaded lazily only when a plot function is called.
Data adapter functions do not require plotting dependencies. The default
analyzer import path remains usable without installing visualization extras.

## Data Flow

```text
AnalysisResult JSON
    -> AnalysisResultCollection
    -> ParetoResult / RankingResult / ComparisonResult / plot-data adapter
    -> optional Matplotlib figure
    -> caller-provided export path
```

Plot exports use guarded caller-owned paths. Visualization modules do not
reference local paths, external data-processing folders, notebooks, or campaign-specific code
branches.

## Current Scope

The implementation provides:

- Pareto objective-space plot data and optional scatter plot;
- ranking plot data and optional score plot;
- comparison objective-space plot data and optional score-colored plot;
- lineage and evolution plot-data adapters;
- guarded figure export helper.

The default objective-space convention is X = trainability and
Y = expressibility, but plot functions accept metric selections. Optional
display aliases are presentation-only and fall back to canonical candidate IDs.
Plotting-only synthetic entities remain outside scientific tables and
ComparisonResult membership.
