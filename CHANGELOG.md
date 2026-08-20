# Changelog

All notable changes to Verfeinert will be documented in this file.

## v0.3.1 - 2026-08-20 - Correctness and Contract Hardening

### Contract corrections

- Synchronized package version metadata across `pyproject.toml`,
  `verfeinert._version`, installed metadata checks, citation metadata, and
  current installation documentation.
- Corrected workflow provenance so runner-generated visualization artifacts set
  the corresponding visualization, figure, and legacy plot-generation flags.
- Added clean CLI handling for missing visualization dependencies when
  visualization output is requested.

### Capability honesty

- Scientific metric definitions are unchanged.
- Pareto, ranking, evolution, strict Pareto feedback, CX-01, MIXT-5G, and
  multithreshold trajectory semantics are unchanged.
- Multiprocessing executor primitives remain available in `verfeinert.core`,
  but scientific workflow/analyzer multiprocessing integration remains
  deferred.
- Candidate JSON remains more expressive than the current PennyLane
  materializer; unsupported gate identities, derived parameters, and unsupported
  runtime parameter forms now fail closed with explicit materialization errors.
- Broader workflow architecture work remains deferred to v0.4.0.

### Maintenance

- Migrated production schema validation from deprecated
  `jsonschema.RefResolver` usage to a packaged-schema `referencing` registry.
- Updated current docs/docstrings that overstated analyzer and visualization
  terminology.

## 0.3.0 - 2026-08-16

### Visualization

- Added immutable semantic visualization models for prepared objective points,
  metric series, bar series, and publication tables.
- Promoted `DEFAULT_STYLE` to publication-grade defaults with
  `PublicationLayouts`, ordered palettes, semantic role styles, and canonical
  PNG/PDF/SVG export formats.
- Added Individual, Evolution, and Global analysis publication renderers over
  already-prepared semantic data.
- Added `save_publication_figure` for guarded multi-format publication export
  with deterministic PNG/PDF/SVG output.

### Validation

- Added structural golden tests for the frozen publication figure families.
- Added scientific-boundary tests ensuring visualization renderers do not
  import metric implementations or call Pareto, dominance, ranking, selection,
  evolution, or top-lineage selection internals.

Visualization consumes prepared scientific results. It does not recompute
Trainability, Expressibility, structural cost, Pareto membership, dominance,
combined scientific score, ranking, selection, evolution, or top-lineage
selection.

## 0.2.0 - 2026-08-13

### Scientific execution

- Added analyzer-owned Candidate/StagedPackage to PennyLane materialization for
  canonical circuit records.
- Added real Expressibility and Trainability execution from canonical
  candidates when QNode and expensive-metric permissions are explicitly granted.
- Preserved bounded structural-cost workflows as the default inexpensive
  validation path.

### Workflow

- Added explicit individual and evolutionary campaign semantics.
- Added artifact-oriented partial and discontinuous workflows without silent
  upstream recomputation.
- Added persisted evolution resume behavior with continuation versus branch
  semantics.

### Public reproducibility

- Migrated CX-01 to the public individual workflow example with smoke and full
  profiles.
- Migrated MIXT-5G to the generic evolutionary workflow path with smoke and
  full profiles.
- Strengthened third-campaign portability through public APIs, configuration,
  and the thin `verfeinert run` CLI.

### Postprocessing

- Added standard Pareto, ranking, structured comparison/global analysis, and
  deterministic CSV/JSON export paths.
- Added optional visualization support with neutral `DEFAULT_STYLE` semantics.

### Persistent contracts

- Added first-class `ComparisonResult` JSON/schema validation.
- Strengthened public artifact contracts for Candidate, StagedPackage,
  AnalysisResult, EvolutionRun, and comparison outputs.

### Validation and limitations

- Release validation uses bounded smoke profiles for CX-01 and MIXT-5G; full
  scientific reproductions remain explicit opt-in workflows.
- Broad arbitrary external CSV ingestion remains deferred.
- Known `jsonschema.RefResolver` deprecation debt remains deferred.

## 0.1.0 - Framework Foundation

- Established the `verfeinert` Python namespace.
- Added `core` configuration, execution, I/O, metadata, hashing, validation, and
  packaged schema-resource helpers.
- Added canonical JSON schemas and schema examples.
- Migrated generator foundations and public canonical Candidate/StagedPackage
  exporters.
- Added analyzer foundations, collections, Pareto/ranking, visualization hooks,
  and v1-aligned expressibility/trainability metrics.
- Added evolver foundations for candidate/analysis references, mutation
  requests, selection, stopping, and EvolutionRun export.
- Added workflow runner plus CX-01 and MIXT-5G smoke reproduction examples.
- Added package-hardening, CI, and external-validation preparation.
