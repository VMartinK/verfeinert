# Visualization System

## Role

`verfeinert.ansatz_analyzer.visualization` is an optional endpoint layer over
analyzer outputs. It consumes `AnalysisResultCollection`, `ParetoResult`, and
`RankingResult` records. It does not compute scientific metrics, classify
Pareto frontiers, rank candidates, execute QNodes, or read notebooks.

## Package Structure

```text
visualization/
    styles/
        __init__.py
    pareto.py
    ranking.py
    lineage.py
    evolution.py
    export.py
```

The style module centralizes fonts, figure dimensions, palettes, markers,
legend behavior, and export defaults. The current public style constant is
regular configuration, not hard-coded plot logic.

## Dependency Policy

Matplotlib is optional and loaded lazily only when a plot function is called.
Data adapter functions do not require plotting dependencies. The default
analyzer import path remains usable without installing visualization extras.

## Data Flow

```text
AnalysisResult JSON
    -> AnalysisResultCollection
    -> ParetoResult / RankingResult / plot-data adapter
    -> optional Matplotlib figure
    -> caller-provided export path
```

Plot exports use guarded caller-owned paths. Visualization modules do not
reference local paths, external data-processing folders, notebooks, or campaign-specific code
branches.

## Current Scope

The first implementation provides:

- Pareto objective-space plot data and optional scatter plot;
- ranking plot data and optional score plot;
- lineage and evolution plot-data adapters;
- guarded figure export helper.

Publication-grade visual reproduction of historical research figures remains
future work.
