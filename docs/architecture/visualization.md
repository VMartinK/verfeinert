# Visualization Architecture

Visualization lives outside `verfeinert.core` under the analyzer package:

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

The public default is campaign-neutral publication-grade `DEFAULT_STYLE`. There is no special thesis mode
and no automatic campaign label, threshold color, or display-name rewriting.
The default score colormap is `plasma` for scalar score encodings where a
caller requests score-colored plots.

Objective-space publication labels are centralized in the visualization layer.
The default trainability label uses generic `T(H)` notation, while callers can
still pass explicit axis labels. Publication legends are rendered above data
with opaque frames using the publication facecolor.

## Boundaries

Visualization code may depend on plotting libraries inside the analyzer
visualization package. It must not be imported by `verfeinert.core`, and
scientific metric execution must not require plotting to be installed.

Research notebooks and raw reference exports remain outside the package and are
development material. Reusable plotting logic belongs in public analyzer
visualization APIs.

Visualization consumes persisted or derived objects such as
`AnalysisResultCollection`, `ParetoResult`, `RankingResult`, `ComparisonResult`,
and EvolutionRun JSON mappings. Plotting-only markers, references, and legend
handles never enter canonical scientific tables or comparison membership.
