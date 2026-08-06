# Ansatz Analyzer Design

## Role

`verfeinert.ansatz_analyzer` owns scientific evaluation, structural cost,
classification, ranking, and derived analytical views for ansatz candidates.
It consumes canonical Candidate JSON and produces canonical AnalysisResult
JSON. It must not depend on notebook structure, local or project-specific paths, generated output
folders, or campaign-name code branches.

The analyzer is the first module allowed to run scientific metric execution,
but execution must be explicit, bounded, and truthfully recorded.

## Target Package Layout

```text
verfeinert/ansatz_analyzer/
    __init__.py
    config.py
    models.py
    validation.py
    io.py
    pipeline.py
    results.py
    metrics/
        __init__.py
        structural_cost.py
        expressibility.py
        trainability.py
        runtime.py
    classification/
        __init__.py
        pareto.py
        thresholds.py
    ranking.py
    tables/
        __init__.py
        scoring.py
        exports.py
        summaries.py
        matrices.py
    visualization/
        __init__.py
        style.py
        objective_space.py
        evolution.py
```

The `visualization` package is a planned layer, not part of the first analyzer
implementation slice.

## Module Responsibilities

`config.py` defines analyzer configuration, metric selection, execution
permissions, cost model settings, ranking policies, and caller-owned output
roots. It should build on `verfeinert.core` config and path primitives.

`models.py` defines internal records such as `CandidateView`,
`OperationView`, `MetricRecord`, `CostRecord`, `ClassificationRecord`,
`AnalysisResultRecord`, and `AnalysisContext`. These records are internal
helpers around canonical JSON, not a competing data model.

`validation.py` validates canonical Candidate and AnalysisResult documents and
module-level invariants that JSON Schema cannot express conveniently.

`io.py` reads Candidate/StagedPackage JSON, writes AnalysisResult JSON, and
writes derived artifacts through guarded output roots. It must not create
implicit experiment roots.

`pipeline.py` coordinates analysis steps. The default safe pipeline should
support metadata-only structural cost and derived classification/ranking from
already available metrics. Expensive metric execution requires explicit
configuration.

`results.py` assembles canonical AnalysisResult records and provenance,
including metric execution flags, software version, Git commit when available,
input hashes, and configuration snapshot.

`metrics.structural_cost` computes structural cost from candidate operations.
It is the first metric to migrate because it is pure and no-QNode.

`metrics.expressibility` and `metrics.trainability` own the scientific metric
definitions, but backend/QNode calls flow through `metrics.runtime` and require
explicit execution permission.

`classification.pareto` classifies result collections using objective
directions and optional cost constraints. Cost is an external filter, not a
Pareto objective.

`classification.thresholds` holds generic threshold-based labels such as cost
eligibility. Threshold values are configuration data.

`ranking.py` ranks AnalysisResult collections by metric, cost, classification,
or derived score. Ranking produces derived records/tables and does not mutate
canonical AnalysisResult JSON.

`tables.*` builds analytical CSV/JSON/Parquet-ready views from canonical JSON.
Tables must carry source AnalysisResult IDs and transform version.

`visualization.*` will turn derived tables into plots using centralized style.
Metric code must never import Matplotlib or notebook APIs.

## Data Flow

```text
Candidate JSON
    -> CandidateView validation
    -> metric computation or skipped metric record
    -> cost records
    -> classification records
    -> AnalysisResult JSON
    -> derived tables
    -> optional visualization
```

For staged packages:

```text
StagedPackage JSON
    -> ordered candidate selection
    -> one AnalysisResult JSON per selected candidate
    -> optional result collection summary
```

For evolution workflows, the analyzer should accept prior AnalysisResult
collections as reference sets for Pareto and ranking. It should not import
evolver internals.

## Dependency Rules

- Allowed shared dependency: `verfeinert.core`.
- Candidate inputs are canonical JSON. Analyzer should not require generator
  construction APIs for normal operation.
- Metric runtime may use scientific dependencies in the analyzer package or
  optional extras, but `core` remains dependency-light.
- No analyzer module may import notebooks, external research-notebook folders, local
  paths, generated output packages, or evolver internals.
- Visualization may import Matplotlib, but metrics, classification, ranking,
  and I/O must not depend on visualization.

## Canonical JSON Contracts

Input Candidate fields used by analyzer:

- `candidate_id`;
- `identity.structural_hash`;
- `circuit.n_qubits`;
- `circuit.parameters`;
- `circuit.operations`;
- `lineage` for parent/root/generation context;
- `metadata` only for optional annotations;
- `provenance` for traceability.

Output AnalysisResult fields written by analyzer:

- `analysis_result_id`;
- `candidate_ref`;
- `metrics`;
- `cost`;
- `classifications`;
- `provenance`;
- optional `metadata` and `extensions`.

Metric execution status must use the canonical schema values:

```text
computed
skipped
failed
```

Legacy statuses such as `configured_not_started` are internal workflow state
only and should not be written into AnalysisResult JSON.

## Scientific Boundaries

Structural cost is metadata-only. It may run in the default analyzer path.

Expressibility and trainability execute scientific callables and may construct
QNodes through a backend adapter. They must require explicit permission and
must record estimated and measured work, RNG seed policy, backend label, and
failure state.

Pareto classification and ranking require existing metric/cost values. They
must not trigger metric execution.

## Table Policy

Tables are derived analytical views. They may flatten candidate IDs, metric
values, cost fields, lineage, Pareto labels, rankings, generation summaries,
or visualization-ready coordinates. Every table export must record:

- source AnalysisResult IDs;
- transform name and version;
- created timestamp;
- configuration snapshot;
- output artifact hash where practical.

CSV remains useful for external research workflows and external inspection, but it is not
the framework exchange format.

## Visualization Policy

Visualization is separate from science. Plotting code consumes derived tables
or lightweight plot-data records and never calls metric functions directly.
Style lives in one place so research figure styles can be updated without
editing every plot function.

External research notebooks may serve as visual references for:

- objective-axis convention;
- cost-threshold frontier plots;
- global and per-campaign comparisons;
- annotation placement;
- figure/table export naming;
- publication styling.

They are not dependencies and should not be copied into package structure.

## First Implementation Slice

The first analyzer slice should implement:

- Candidate JSON ingestion;
- AnalysisResult model and writer;
- structural cost;
- schema validation tests;
- no-QNode dependency boundary tests.

This creates a useful analyzer core before migrating expensive metrics or
visual outputs.

## Deferred Design Work

- full backend adapter API for QNode execution;
- expressibility/trainability runtime extras;
- Parquet table writer;
- visualization style schema;
- notebook endpoint templates;
- cross-candidate or analysis-run collection schema.

## Open Decisions

- whether metric-specific result values need stricter sub-schemas;
- how to represent uncertainty, sample distributions, and diagnostic arrays;
- whether ranking policy configuration should use named profiles;
- how much generator package dependency is acceptable for analyzer examples;
- whether result collections need a canonical `analysis_run` schema separate
  from per-candidate AnalysisResult.
