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

The default plotting style should be treated as a regular, update-friendly
configuration object. Verfeinert should centralize fonts, palettes, markers,
legend rules, annotation rules, figure sizes, and export settings instead of
distributing them across individual plotting functions.

The future visualization layer should support:

- a default publication-oriented style;
- Python style configuration objects;
- YAML style overrides;
- explicit style objects passed to plotting functions;
- centralized export parameters for reproducible figure generation.

## Boundaries

Visualization code may depend on plotting libraries inside the analyzer
visualization package. It must not be imported by `verfeinert.core`, and
scientific metric execution must not require plotting to be installed.

Research notebooks may remain outside the package, but reusable plotting logic
should be exposed through public analyzer visualization APIs during a later
development phase.
