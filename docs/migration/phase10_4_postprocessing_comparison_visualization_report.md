# Phase 10.4 Postprocessing, Comparison, And Visualization Report

Phase 10.4 matured persisted-artifact postprocessing without starting final
release cleanup.

## Implemented

- Added generic analyzer comparison/global analysis over explicitly selected
  `AnalysisResultCollection` sources.
- Added `ComparisonResult` JSON payloads with source refs, compatibility
  provenance, objective definitions, static global Pareto membership, optional
  ranking fields, cost eligibility, canonical candidate refs, and structured
  lineage/source metadata.
- Added deterministic comparison JSON and CSV writers through the existing
  derived table/export surface.
- Extended workflow postprocessing with `comparison` and `visualization` while
  keeping scientific execution as `generate`, `analyze`, and `evolve`.
- Added persisted `ComparisonResult -> CSV` and `ComparisonResult ->
  visualization` paths without recomputing comparison.
- Replaced the thesis-named visualization style surface with neutral
  `DEFAULT_STYLE`.
- Added comparison plotting and EvolutionRun lineage plotting adapters with
  lazy Matplotlib imports.

## Compatibility Model

Comparison compatibility uses structured provenance/configuration rather than
campaign names. It checks metric definitions required by objectives/ranking,
trainability Hamiltonian provenance, expressibility configuration,
structural-cost model/reference/bounds/weights/depth semantics, objectives,
directions, cost thresholds, and ranking score configuration.

Output paths, filenames, visualization settings, CLI invocation, and display
labels are intentionally ignored. Missing comparison-critical provenance fails
closed.

## Visualization Reference Handling

The files under `visualization_reference_notebooks/` were inspected as
scientific and visual references only. The current global notebook was treated
as source of truth. The obsolete exploratory F/F2 material was not
reconstructed or encoded. Generic principles extracted were restrained
publication-quality defaults, trainability/expressibility objective-space
conventions, scalar `plasma` score encoding, explicit semantic lineage fields,
and separation of plotting-only synthetic entities from scientific tables.

## Boundaries

Postprocessing consumes persisted artifacts and does not execute QNodes,
generated callables, notebooks, generator logic, analyzer metric pipelines, or
evolution loops unless those scientific operations are explicitly requested by
the workflow. Arbitrary external CSV ingestion remains deferred.
