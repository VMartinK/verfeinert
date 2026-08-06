# Ansatz Generator Architecture

`verfeinert.ansatz_generator` owns backend-independent ansatz representation,
template construction, structural mutation primitives, candidate normalization,
metadata-only compilation, and staged package writing. It depends on
`verfeinert.core` for shared serialization, path guards, hashing support,
provenance-compatible schema ideas, and lightweight validation.

The module does not import analyzer, evolver, notebooks, external data-processing
code, plotting libraries, or quantum backends. It does not execute QNodes,
metrics, notebooks, campaigns, or generated callable modules.

## Public Responsibilities

The generator provides:

- gate and operation records;
- parameter placeholders and stable parameter maps;
- connectivity and constraint records;
- candidate and lineage records;
- Sanz19 reference-template candidate construction;
- deterministic structural and lineage identity;
- pure structural mutation primitives;
- metadata-only candidate compilation;
- staged metadata packages under caller-provided output roots;
- optional callable-source generation without import or execution.

Scientific analysis, Pareto policies, ranking, selection, final plotting, and
experiment execution belong to later analyzer/evolver layers.

## Representation Model

`GateDef` and `GateRegistry` provide the extensible gate vocabulary. The
default registry preserves the Beta gate set:

```text
rx ry rz x y z h cx cz cnot swap crx cry crz isingxx isingyy isingzz
```

`Operation` stores backend-independent gate, wire, parameter, layer, order, and
metadata fields. It validates known gate arity and parameter shape but does not
bind to PennyLane, Qiskit, or any execution backend.

`ParameterMap` preserves first-appearance ordering of symbolic trainable
parameters. Repeated symbolic names map to the same vector index. Numeric
operation parameters are treated as fixed constants and are not included in the
trainable parameter map.

`Connectivity` and `ConstraintSet` express structural rules such as allowed
gates, allowed inserted gates, and directed or undirected two-qubit edges.

`LineageRecord` and `CandidateRecord` are small provenance and representation
records suitable for later analyzer, evolver, and visualization use.

## Candidate Lifecycle

The public candidate lifecycle is:

1. A caller constructs or loads candidate-like mappings.
2. `normalize_operation_record` normalizes operation shape, gates, wires,
   parameters, and metadata.
3. `normalize_candidate_record` accepts Beta-style candidate fields, including
   `circuit_id`, `child_id`, `candidate_id`, `operations`, `metadata`, and
   `genome.operations`.
4. `compile_candidate_records` validates duplicates and invalid records,
   computes deterministic identity, and returns metadata-only records.
5. `write_candidate_staged_package` writes optional JSON, CSV, manifest, and
   callable source files under a caller-provided output root.

No stage in this lifecycle performs scientific metric evaluation.

## Hash Contract

Candidate structural and lineage hashes preserve the Beta-compatible payload
contract for equivalent normalized records.

Structural hashes use:

- normalized operations;
- layer;
- parameter count;
- operation count;
- two-qubit operation count.

Lineage hashes use:

- circuit ID;
- parent circuit ID;
- root circuit ID;
- generation index;
- variant index;
- mutation type;
- mutation gate.

The schema label is `verfeinert.generator.candidate_hash.beta_v1`. Any future
change to these payloads must introduce a new explicit hash/schema version and
document the public API impact.

## Staging Contract

Staged packages are written under:

```text
<caller_output_root>/<run_id>/
```

Supported files are:

- `metadata.json`;
- optional `metadata.csv`;
- optional `package_manifest.json`;
- optional generated callable module source.

Manifest and metadata summary flags must truthfully report:

```text
qnodes_executed = false
scientific_metrics_executed = false
```

The generator validates caller-provided output roots through `verfeinert.core`.
Package source, external inputs, and generated outputs must remain separate.

## Callable Boundary

Callable generation is source generation only. Generated source may include
PennyLane imports inside function bodies so downstream users can place the
functions inside QNodes later, but the generator package does not import
PennyLane and does not import or execute generated modules.

Generated modules include safety flags:

```text
QNODES_EXECUTED = False
SCIENTIFIC_METRICS_EXECUTED = False
```

## Extension Points

External researchers can extend the generator by:

- registering additional `GateDef` values in a custom `GateRegistry`;
- creating custom template builders that emit operation/candidate records;
- defining custom `Connectivity` or `ConstraintSet` records;
- implementing pure mutation functions that consume and return normalized
  operation records.

Extensions should remain backend-independent unless they live in a dedicated
future compiler/backend package.

## Visualization Considerations

No visualization is implemented in the generator. Operation metadata preserves
order, layer, block, role, template, and source fields where available so a
future analyzer visualization layer can draw circuits without hard-coded style
constants inside the generator.
