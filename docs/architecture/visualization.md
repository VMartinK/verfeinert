# Visualization Architecture

Full plotting API coverage is intentionally staged. Visualization will live
outside `verfeinert.core` under the analyzer package:

```text
verfeinert/ansatz_analyzer/visualization/
```

This keeps visualization optional and prevents plotting dependencies from
becoming required for the scientific core, generator, or default evolver
workflows.

## Style Contract

The default plotting style is a regular, update-friendly configuration object.
Verfeinert centralizes fonts, palettes, markers, legend rules, figure sizes,
score colormap, and export settings instead of distributing them across
individual plotting functions.

The visualization layer supports:

- a default publication-oriented style;
- Python style configuration objects;
- explicit style objects passed to plotting functions;
- centralized export parameters for reproducible figure generation.

The public default is neutral `DEFAULT_STYLE`. There is no special thesis mode
and no automatic campaign label, threshold color, or display-name rewriting.
The default score colormap is `plasma` for scalar score encodings where a
caller requests score-colored plots.

## Boundaries

Visualization code may depend on plotting libraries inside the analyzer
visualization package. It must not be imported by `verfeinert.core`, and
scientific metric execution must not require plotting to be installed.

Research notebooks may remain outside the package, but reusable plotting logic
should be exposed through public analyzer visualization APIs during a later
development phase.

Visualization consumes persisted or derived objects such as
`AnalysisResultCollection`, `ParetoResult`, `RankingResult`, `ComparisonResult`,
and EvolutionRun JSON mappings. Plotting-only markers, references, and legend
handles never enter canonical scientific tables or comparison membership.
