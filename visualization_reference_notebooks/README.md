# Visualization Reference Material

This directory is reserved for local development/reference material used while
designing the Verfeinert visualization system.

Raw notebooks, raw global exports, notebook outputs, and handoff scratch files
are not runtime dependencies, are not package data, and are excluded from the
public release tree by `.gitignore`.

Public visualization architecture is documented in:

- `docs/architecture/visualization.md`;
- `docs/architecture/visualization_system.md`;
- `docs/architecture/comparison.md`.

Reusable plotting behavior belongs in `verfeinert.ansatz_analyzer.visualization`
and must operate on canonical or derived Verfeinert artifacts, not on private
local reference paths.
