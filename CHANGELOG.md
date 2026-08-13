# Changelog

All notable changes to Verfeinert will be documented in this file.

## 0.2.0 - Pending release

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
