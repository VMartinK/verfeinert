# Canonical Data Model

Verfeinert uses hierarchical JSON as its canonical internal exchange format.
CSV and Parquet tables may be derived later for analytical workflows, reporting,
or notebook convenience, but tables are not the source of truth between
framework modules.

These contracts describe the public exchange model for framework modules. They
are not compatibility records for historical run artifacts.

## Design Principles

- Prefer future scientific clarity over backward compatibility.
- Preserve Verfeinert v1 concepts only when they are correct abstractions:
  candidates, operations, parameters, lineage, metrics, costs, classifications,
  staged packages, experiment configuration, and provenance.
- Keep communication records hierarchical and self-describing.
- Avoid campaign-specific fields and project-specific paths.
- Reference large or external records by ID/URI where embedding would couple
  modules unnecessarily.
- Treat generated artifacts as outputs, not source code.

## Module Boundaries

`core` owns shared validation, serialization, provenance primitives, path
guards, and lightweight schema constants. It does not own scientific semantics.

`ansatz_generator` owns candidate construction and representation. Its public
exports are canonical `Candidate` documents and `StagedPackage` documents.

`ansatz_analyzer` will consume candidate references and produce
`AnalysisResult` documents. Analysis results reference candidates rather than
embedding full candidates by default.

`ansatz_evolver` will consume candidates and analysis results, then produce
`EvolutionRun` documents recording generations, selection, archives, and
configuration.

## Candidate Model

A candidate is a complete backend-independent ansatz description. The canonical
candidate document contains:

- `candidate_id`: stable framework identifier;
- `identity`: structural and lineage hashes plus hash schema version;
- `circuit`: qubit count, optional wire order, parameters, and ordered
  operations;
- `lineage`: root/parent relationship, generation number, and mutation
  provenance;
- `metadata`: non-campaign-specific annotations;
- `provenance`: source, timestamp, software version, Git commit when available,
  and input hashes.

The circuit is the canonical representation. Derived counts such as operation
count or parameter count can be computed by consumers or written into derived
tables.

## Operation Model

Operations are backend-independent. An operation identifies:

- an `operation_id`;
- a gate by name and optional namespace/version;
- qubits as integer wire indices;
- parameters as references to circuit-level parameters or literal fixed values;
- optional layer/order/role metadata for later visualization and analysis.

The operation model deliberately avoids PennyLane, Qiskit, or generated source
fields.

## Lineage Model

Lineage records the scientific ancestry of a candidate:

- `generation`;
- `root_candidate_id`;
- `parent_candidate_id`;
- optional mutation record with mutation ID, type, source candidate, and
  parameters.

Lineage is not a historical import format. Only relationships needed for future
generation, evolution, reproducibility, and analysis are retained.

## Analysis Result Model

An analysis result references one candidate and stores:

- metric records with status, value, units, errors, and metadata;
- cost records such as structural cost or operation counts;
- classifications such as Pareto labels or threshold-based categories;
- provenance of the analysis boundary.

Metrics are not placed on the candidate itself. This lets one candidate have
multiple analysis results produced by different methods, versions, hardware, or
execution settings.

## Evolution Run Model

An evolution run records:

- run metadata and status;
- configuration snapshot or experiment reference;
- generations;
- candidate references;
- survivor and archive references;
- provenance.

Evolution records reference candidates rather than duplicating complete
candidate documents in every generation.

## Experiment Configuration Model

Experiment configuration records:

- caller-provided inputs;
- caller-provided outputs;
- execution settings;
- reproducibility options;
- module-specific configuration blocks.

No public schema field assumes local or project-specific paths, repository-relative research
outputs, or campaign-specific identifiers.

## Table Derivation Policy

CSV and Parquet tables are derived analytical views. They may flatten metrics,
costs, candidate summaries, or generation trajectories, but they must be
reproducible from canonical JSON documents or explicitly record the source JSON
documents and transform version.

## Current Generator Assessment

The current Verfeinert `ansatz_generator` APIs provide the core pieces needed
for this model:

- operations are backend-independent;
- parameter maps exist;
- lineage and candidate metadata are represented;
- Sanz19 templates are reproducible;
- staged packages are metadata-only;
- callable source generation is optional and no-QNode.

Generator records are implementation records, while canonical Candidate JSON is
the external exchange format. Public exporters provide nested `candidate_id`,
`circuit`, `identity`, `lineage`, and `provenance` documents matching
`candidate.schema.json`.

## Open Design Decisions

- Whether canonical schema validation should become a runtime dependency or
  remain a development/integration validation tool.
- Whether operation gate namespaces should use short framework labels or full
  URIs.
- How strict future cross-document URI resolution should be for packaged runs.
- Whether analysis result metric values need domain-specific sub-schemas for
  high-dimensional outputs.
- How derived table transform versions should be named once CSV/Parquet export
  APIs are implemented.
