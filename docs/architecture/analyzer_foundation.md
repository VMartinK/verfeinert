# Analyzer Foundation

## Role

`verfeinert.ansatz_analyzer` provides schema-first scientific analysis and
postprocessing over canonical Candidate, StagedPackage, and AnalysisResult
JSON. It emits canonical AnalysisResult JSON for per-candidate analysis and
derived Pareto, ranking, comparison, table, CSV, and optional visualization
artifacts for postprocessing workflows.

The analyzer owns PennyLane-backed scientific execution when explicitly
enabled. It does not depend on notebooks, generated local packages,
campaign-name branches, or private reference data.

## Implemented Modules

`config.py` defines analyzer configuration, execution permissions, selected
metric validation, input/output roots, random seed policy, structural-cost
settings, Pareto options, and ranking policies.

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

`validation.py` performs runtime validation against packaged schema resources
using JSON Schema Draft 2020-12.

`io.py` reads Candidate or StagedPackage JSON and writes AnalysisResult JSON
under caller-owned guarded output roots.

`metrics/structural_cost.py` implements record-based structural cost without
PennyLane, Matplotlib, notebooks, generated callables, or QNodes.

`metrics/expressibility.py` and `metrics/trainability.py` define explicit
scientific metric execution. Materialization through PennyLane is analyzer
owned, opt-in, and truthfully recorded in AnalysisResult provenance.

`pipeline.py` wires the foundation flow:

```text
Candidate or StagedPackage JSON
    -> schema validation
    -> CandidateView records
    -> metric computation or skipped metric records
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

The analyzer writes one AnalysisResult per candidate. Tables, summaries, CSV,
plots, and comparison views are derived outputs, not replacements for the
canonical AnalysisResult contract.

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

The default structural-cost path never imports or executes generated callables
and never constructs QNodes. AnalysisResult provenance records false execution
flags for:

- QNode execution;
- generated callable execution;
- notebook execution;
- expensive metric execution;
- plot generation.

Expressibility and trainability require explicit configuration, materialization,
and execution permissions because they can construct QNodes and run expensive
scientific workloads.

## Dependency Boundary

The analyzer depends on:

- Python standard library;
- `jsonschema`;
- `verfeinert.core`;
- declared scientific runtime dependencies for analyzer execution, including
  NumPy and PennyLane.

It must not depend on:

- `verfeinert.ansatz_generator`;
- `verfeinert.ansatz_evolver`;
- notebooks;
- `external research notebooks`;
- Matplotlib;
- pandas;
- notebooks and private reference data.

## Postprocessing

Postprocessing consumes existing AnalysisResult collections. It can compute:

- Pareto and threshold classification;
- ranking;
- comparison/global analysis over explicitly selected compatible sources;
- derived JSON and CSV tables;
- optional visualization data and Matplotlib figures.

Postprocessing must not trigger unrelated scientific execution or mutate
canonical candidate identity.

## Extension Points

- stricter metric-specific value sub-schemas;
- richer uncertainty and diagnostic array representation;
- optional named ranking profiles over the current plain JSON policy surface;
- a canonical result-collection schema separate from
  per-candidate AnalysisResult documents.
