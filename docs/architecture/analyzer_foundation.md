# Analyzer Foundation

## Role

The first `verfeinert.ansatz_analyzer` implementation slice provides a
schema-first, structural-cost-only analysis path. It consumes canonical
Candidate JSON or canonical StagedPackage JSON and emits canonical
AnalysisResult JSON.

This layer intentionally does not migrate expressibility, trainability,
Pareto, ranking, visualization, notebooks, generated callable loading, or
legacy Beta table workflows.

## Implemented Modules

`config.py` defines analyzer configuration, execution permissions, selected
metric validation, input/output roots, random seed policy, and structural-cost
settings. The only implemented metric is `structural_cost`.

`models.py` defines internal lightweight records:

- `OperationView`;
- `CandidateView`;
- `MetricRecord`;
- `CostRecord`;
- `ClassificationRecord`;
- `AnalysisContext`;
- `AnalysisResultRecord`.

These records are helpers around canonical JSON. They are not a public
exchange format.

`validation.py` performs runtime validation against the existing schema files
under `schemas/` using JSON Schema Draft 2020-12.

`io.py` reads Candidate or StagedPackage JSON and writes AnalysisResult JSON
under caller-owned guarded output roots.

`metrics/structural_cost.py` implements record-based structural cost without
pandas, NumPy, PennyLane, Matplotlib, notebooks, generated callables, or QNodes.

`pipeline.py` wires the foundation flow:

```text
Candidate or StagedPackage JSON
    -> schema validation
    -> CandidateView records
    -> structural cost
    -> AnalysisResultRecord
    -> optional AnalysisResult JSON write
```

## Canonical JSON Boundary

Input must use:

```text
verfeinert.candidate.v1
verfeinert.staged_package.v1
```

Output uses:

```text
verfeinert.analysis_result.v1
```

The analyzer writes one AnalysisResult per candidate. Tables, summaries, plots,
and notebooks are future derived outputs, not foundation exchange contracts.

## Structural Cost

The migrated structural cost preserves the current scientific behavior while
removing the pandas-first table boundary.

Components:

- `parameter_count`: canonical circuit parameters with `kind == "trainable"`;
- `depth`: `metadata.structural.depth` when present;
- `two_qubit_operation_count`: operations with exactly two qubits.

When depth is not present, the foundation can use `operation_count` as a depth
proxy and records a warning. If no reference bounds are supplied, bounds are
derived from the selected candidates and that decision is recorded.

The AnalysisResult `cost` object stores:

- `structural_cost`;
- `operation_count`;
- `two_qubit_operation_count`;
- `parameter_count`;
- component values, normalized values, weights, bounds, reference status, and
  warnings in `cost.metadata`.

## Execution Boundary

Foundation analysis never imports or executes generated callables and never
constructs QNodes. AnalysisResult provenance records false execution flags for:

- QNode execution;
- generated callable execution;
- notebook execution;
- expensive metric execution;
- plot generation.

Expressibility and trainability remain deferred because they require explicit
scientific execution boundaries and optional heavy dependencies.

## Dependency Boundary

The foundation analyzer depends on:

- Python standard library;
- `jsonschema`;
- `verfeinert.core`.

It must not depend on:

- `verfeinert.ansatz_generator`;
- `verfeinert.ansatz_evolver`;
- notebooks;
- `external research notebooks`;
- PennyLane;
- Matplotlib;
- pandas;
- NumPy.

## Deferred Layers

Deferred analyzer work includes:

- expressibility metric runtime;
- trainability metric runtime;
- Pareto and threshold classification;
- ranking;
- derived CSV/Parquet tables;
- visualization;
- notebook/example endpoints;
- compatibility adapters for historical Beta tables.

## Open Decisions

- Whether metric-specific values need stricter sub-schemas.
- How uncertainty and diagnostic arrays should be represented.
- Whether ranking policies should use named profiles or plain JSON config.
- Whether result collections need a canonical schema separate from
  per-candidate AnalysisResult documents.
