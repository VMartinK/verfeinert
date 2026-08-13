# Evolver Foundation

## Scope

`verfeinert.ansatz_evolver` is a JSON-first orchestration layer. It consumes
canonical Candidate JSON and AnalysisResult JSON, stores reference-only
population state, and exports canonical EvolutionRun JSON.

The evolver does not compute scientific metrics, execute QNodes, import
analyzer internals, import visualization modules, or use pandas.

## Implemented Modules

`models.py`
: Defines `CandidateRef`, `AnalysisResultRef`, `EvolutionEvent`,
  `GenerationRecord`, and `EvolutionRunState`.

`validation.py`
: Loads packaged JSON schemas and validates Candidate, StagedPackage,
  AnalysisResult, and EvolutionRun documents without analyzer imports.

`io.py`
: Provides read helpers for validated canonical JSON documents.

`config.py`
: Defines `EvolverConfig` and `EvolverExecutionPermissions`. Metric execution,
  QNode execution, and visualization permissions are rejected because the
  evolver is not an execution backend.

`population/`
: Provides reference-only population snapshots and structural deduplication
  reports.

`mutation/`
: Provides mutation recipes, policies, schedules, and request records. Requests
  are intentions only; the evolver does not edit circuits.

`candidate_factory.py`
: Defines the public factory protocol for caller-provided candidate generation.
  Factories return canonical Candidate JSON.

`evaluation/`
: Defines analysis request records and AnalysisResult ingestion/linking.

`selection/`
: Provides fitness, threshold, Pareto, strict-Pareto, and multithreshold
  policies over AnalysisResult JSON.

`policies/stopping.py`
: Defines stopping policies and terminal-state decisions.

`pipeline.py`
: Provides a small append-only state wrapper that builds `EvolutionRunState`.

`exporters/evolution_run_json.py`
: Exports and writes schema-validated EvolutionRun JSON under caller-owned
  output roots.

## Data Flow

```text
Candidate JSON refs
    -> mutation request records
    -> external candidate factory
    -> child Candidate JSON refs
    -> analysis request
    -> external analyzer execution
    -> AnalysisResult JSON refs
    -> selection policy
    -> GenerationRecord
    -> EvolutionRun JSON
```

Candidate JSON remains the source of truth for circuits and lineage.
AnalysisResult JSON remains the source of truth for metrics, costs, and
classifications. EvolutionRun JSON records orchestration state and references.

## Boundaries

Allowed dependencies are Python stdlib, `jsonschema`, `verfeinert.core`, and
canonical JSON documents. The public generator boundary is represented as a
callable protocol; production evolver code does not import generator internals.

Forbidden dependencies include analyzer internals, pandas, Matplotlib,
PennyLane, notebooks, external research-notebook folders, generated callables, and
campaign-specific branches.

## Extension Points

- richer event subtype schemas;
- archive summary models;
- derived CSV/Parquet run tables;
- additional production workflow integrations;
- richer stochastic mutation schedules.
