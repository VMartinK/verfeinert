# Canonical Data Model

Verfeinert uses hierarchical JSON as its canonical exchange format. CSV tables,
figures, examples, and notebooks are derived views over versioned records; they
are not the source of truth between framework modules.

## Design Principles

- Keep scientific records hierarchical, explicit, and self-describing.
- Preserve canonical identity in one owner and propagate refs downstream.
- Avoid campaign-specific fields, local paths, and publication-specific naming
  in framework defaults.
- Treat generated outputs as artifacts, not source code.
- Record enough provenance to reproduce and compare science without requiring
  total configuration equality when differences are irrelevant.

## First-Class Persistent Artifacts

### Candidate

Owned by `verfeinert.ansatz_generator`.

A Candidate is a backend-independent ansatz description. It contains:

- `candidate_id`, the canonical scientific identity;
- structural and lineage hashes;
- circuit qubit count, wire order, parameters, and ordered operations;
- lineage root/parent/generation/mutation metadata;
- non-canonical annotations in `metadata`;
- source and software provenance.

Operations identify gates, wires, parameter references, and literal fixed
values without binding to PennyLane, Qiskit, notebooks, or generated modules.
Repeated symbolic parameters preserve identity through the circuit parameter
map.

### StagedPackage

Owned by `verfeinert.ansatz_generator`.

A StagedPackage groups ordered Candidate documents and export metadata for
analysis or workflow entry. It may also point at generated callable source, but
generated source is not imported or executed by the generator.

### AnalysisResult

Owned by `verfeinert.ansatz_analyzer`.

An AnalysisResult references one Candidate through `candidate_ref` and stores:

- metric records with status, values, errors, units, and metadata;
- cost records such as structural cost and component counts;
- classifications such as Pareto or threshold labels;
- analyzer provenance including metric configuration, permissions,
  materialization/QNode truth flags, seeds, software version, and config
  snapshot;
- structured `candidate_semantics` when lineage/source context needs to be
  propagated.

Metrics are not written back onto Candidate JSON. One Candidate can have
multiple AnalysisResult records from different runs, methods, or configurations.

### EvolutionRun

Owned by `verfeinert.ansatz_evolver`.

An EvolutionRun records:

- evolution run identity and configuration snapshot;
- ordered generations;
- parent, candidate, survivor, rejected, and archive refs;
- analysis-result refs;
- mutation and selection events;
- continuation or branch metadata;
- evolver/workflow provenance.

Evolution records reference Candidate and AnalysisResult artifacts rather than
duplicating complete scientific documents.

### ComparisonResult

Owned by `verfeinert.ansatz_analyzer.comparison`.

A ComparisonResult records an explicit postprocessing transform over selected
AnalysisResult collections:

- comparison ID and transform version;
- explicit source refs and roles;
- compatibility report and fingerprints;
- candidate rows with canonical candidate and analysis refs;
- global Pareto membership;
- optional ranking data;
- cost eligibility and threshold views;
- comparison provenance.

ComparisonResult is independent of plotting. Visualization and CSV are derived
views over it.

## Derived Artifacts

Ranking JSON/CSV, Pareto JSON/CSV, AnalysisResult CSV, comparison CSV, and
figures are derived artifacts. They preserve source refs, transform names, and
transform versions, but they do not replace the first-class JSON contracts.

Broad arbitrary external CSV import is outside the current contract. CSV export
from canonical and derived Verfeinert artifacts is supported where the result
is naturally tabular.

## Schema Resources

Root schemas under `schemas/` mirror packaged schemas under
`verfeinert/schemas/`. The package exposes schema resources through
`verfeinert.core.schema_resources`, so installed validation does not depend on
repository-relative files.

The first-class schema versions are:

- `verfeinert.candidate.v1`;
- `verfeinert.staged_package.v1`;
- `verfeinert.analysis_result.v1`;
- `verfeinert.evolution_run.v1`;
- `verfeinert.comparison_result.v1`.

Experiment schemas remain shared configuration/provenance support.

## Identity Model

Candidate JSON owns canonical candidate identity. Downstream records propagate
it through `candidate_ref.candidate_id`, derived rows, and structured semantic
fields. They do not introduce another independent canonical candidate ID.

Lineage/root/parent/generation/layer/run/campaign/mutation fields are
structured context with defined owners:

- Candidate owns scientific lineage and mutation provenance.
- AnalysisResult propagates candidate semantics needed for analysis and
  postprocessing.
- EvolutionRun owns generation state and evolution relationships.
- ComparisonResult owns source selection and comparison rows.
- Visualization owns presentation labels only.

Display aliases are optional presentation metadata. They fall back to canonical
candidate IDs and never mutate scientific identity.

## Provenance Model

Analyzer provenance owns metric execution facts, metric configuration,
materialization backend/settings, QNode execution flags, seeds, and software
version.

Evolver provenance owns selection, mutation, generation state, resume/branch
relationships, and evolution configuration.

Workflow provenance owns orchestration: requested/executed operations, artifact
reuse, campaign type, config snapshot, output roots, and truth flags such as
notebook execution.

Comparison provenance owns explicit source selection, compatibility decisions,
metric/cost fingerprints, objectives, directions, thresholds, and score
definitions.

## Scientific Comparison Data

Compatibility uses structured provenance instead of campaign names. Depending
on the requested analysis, comparison checks trainability Hamiltonian,
trainability config, expressibility config, structural-cost model and
normalization reference, component bounds, weights, score configuration,
Pareto objectives and directions, and thresholds.

Output paths, filenames, visualization settings, CLI invocation, and display
labels are not scientific compatibility dimensions.

## Table Derivation Policy

Derived tables must be reproducible from canonical JSON or explicitly record
their source artifact refs and transform versions. They should preserve
canonical candidate IDs and analysis-result IDs, use deterministic column
ordering, and avoid implicit scientific assumptions about units, metrics,
normalization, or cost definitions.
