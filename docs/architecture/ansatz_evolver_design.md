# Ansatz Evolver Design

## Role

`verfeinert.ansatz_evolver` owns evolutionary orchestration for ansatz
candidates. It decides which candidates are parents, which mutation policies
produce children, which analyzed candidates survive, when a run stops, and how
the evolution state is recorded.

It does not own scientific metric computation. Metrics, costs,
classifications, Pareto labels, and rankings enter the evolver as canonical
AnalysisResult JSON.

## Dependency Boundary

Allowed runtime dependencies:

- `verfeinert.core`;
- canonical Candidate JSON;
- canonical StagedPackage JSON;
- canonical AnalysisResult JSON;
- canonical EvolutionRun JSON;
- public generator APIs only when explicitly producing candidate documents.

Forbidden dependencies:

- analyzer internal classes such as `AnalysisResultCollection`;
- analyzer pandas/CSV table layouts;
- analyzer visualization modules;
- notebooks and external research-notebook folders;
- generated callable modules;
- PennyLane/QNode execution;
- campaign-name code branches.

Workflow orchestration may wire the evolver to the generator and analyzer.
Those boundaries exchange JSON documents, refs, paths, and public factory
interfaces, not analyzer internals.

## Package Layout

```text
verfeinert/ansatz_evolver/
    __init__.py
    candidate_factory.py
    config.py
    models.py
    validation.py
    io.py
    pipeline.py
    population/
        __init__.py
        refs.py
        deduplication.py
        snapshots.py
    mutation/
        __init__.py
        policies.py
        schedules.py
        requests.py
        ids.py
    selection/
        __init__.py
        fitness.py
        multithreshold.py
        pareto.py
        thresholds.py
        strict_pareto.py
    evaluation/
        __init__.py
        requests.py
        results.py
    policies/
        __init__.py
        stopping.py
        random.py
    exporters/
        __init__.py
        evolution_run_json.py
```

This layout preserves a reference-based model: population, mutation,
selection, evaluation refs, and exporters are separate from analyzer metric
execution.

In v0.3.x, `EvolverConfig.execution` is sequential-only for public evolver
state construction. Core multiprocessing primitives exist, but evolver/workflow
scientific integration is deferred to v0.4.0.

## Population Representation

The canonical population model is reference-based.

Population records contain:

- `population_id`;
- `generation_index`;
- ordered candidate references;
- candidate role such as `parent`, `child`, `survivor`, or `archive`;
- optional cached identity fields such as `structural_hash` and
  `lineage_hash`;
- optional status and selection metadata;
- provenance and source artifact references.

Population records do not embed complete Candidate JSON documents. Full
candidate definitions live in Candidate JSON or StagedPackage JSON artifacts.
This avoids duplicating circuits, operations, parameters, lineage, and
provenance across modules.

## Candidate Generation

The evolver describes what child candidates should be produced. It should not
compile circuits or execute scientific workloads.

The active boundary is:

```text
parent Candidate refs
    -> mutation policy
    -> mutation request records
    -> public generator candidate factory/exporter
    -> child Candidate JSON / StagedPackage JSON
```

The generator owns operation-level construction and canonical Candidate export.
The evolver owns policy, schedule, lineage intent, candidate references, and
run state.

If a caller wants to use a custom candidate factory, the factory must accept
JSON-safe mutation requests and return validated Candidate JSON documents or a
validated StagedPackage JSON document.

## Mutation Model

A mutation policy is declarative configuration. It includes or can include:

- policy ID and version;
- operator type, such as insert, replace, remove, swap, reorder, or
  template-layer propagation;
- gate/operator parameters;
- probability or deterministic schedule;
- application scope;
- maximum children per parent/generation;
- deduplication policy;
- random seed policy;
- enabled/disabled state.

A mutation request records one requested child creation:

- parent candidate ID;
- root candidate ID;
- target generation;
- mutation type;
- target operation or insertion position when applicable;
- changed operation/gate metadata;
- policy ID and recipe ID;
- deterministic variant index;
- warnings or skipped/no-op state.

Generated child Candidate JSON must carry the resulting parent/root/generation
and mutation provenance in canonical `lineage`.

## Evaluation Boundary

The evolver does not call metric functions. Its evaluation model is:

```text
child Candidate JSON
    -> analysis request
    -> external analyzer run
    -> AnalysisResult JSON
    -> evolver selection
```

An analysis request is a lightweight record containing:

- request ID;
- candidate refs or StagedPackage ref;
- requested metrics/classifications;
- execution permissions;
- output root or expected result URI;
- provenance and config snapshot.

The request may be executed by user code, an example script, or a future
workflow runner. The evolver only ingests the resulting AnalysisResult JSON.

## Selection Interfaces

Selection policies operate over canonical AnalysisResult JSON fields.

Supported policy families:

- fitness-based selection using configurable metric/cost/classification
  expressions;
- Pareto-based selection using AnalysisResult metrics and classifications;
- strict-Pareto feedback against accumulated reference/frontier state;
- threshold filtering over costs, metrics, or classifications;
- multi-threshold trajectory selection where each threshold keeps independent
  survivor/archive state.

Selection output records:

- selected survivor candidate refs;
- rejected candidate refs;
- deterministic selection reason;
- policy ID and configuration snapshot;
- threshold used when applicable;
- source AnalysisResult IDs;
- warnings and terminal status.

No policy should hardcode CX, MIXT, Sanz19, or research campaign names.

## Evolution State

The run state is the durable orchestration record. It includes:

- evolution run ID and status;
- configuration snapshot;
- generation records;
- parent, child, survivor, and archive candidate refs;
- analysis request/result references;
- mutation events;
- selection events;
- stopping events;
- warnings/errors;
- provenance and input hashes.

The canonical exchange document is EvolutionRun JSON. Derived CSV summaries,
frontier tables, and plot data are downstream artifacts; they are not the
internal state contract.

## Stopping Conditions

Stopping conditions are policy data, not hardcoded campaign behavior. Current
and future conditions include:

- maximum generations reached;
- no candidates generated;
- no valid analysis results;
- no survivors selected;
- no strict new Pareto candidates;
- metric execution budget exhausted;
- duplicate-only generation;
- user cancellation or explicit failure state.

Each stopping decision must record whether the run completed, failed,
cancelled, or stopped by configured policy.

## Reproducibility

Evolution configuration must record:

- random seed or null seed policy;
- mutation operators and probabilities/schedules;
- selection objectives, weights, thresholds, and tie-breaking rules;
- deduplication keys and keep policy;
- generation limits and child limits;
- input Candidate/StagedPackage/AnalysisResult hashes;
- software version and Git commit when available;
- execution permissions and truthful execution flags.

The workflow runner records the effective evolution fingerprint used for
continuation compatibility. Resume preserves historical generations and
analysis refs; branch mode records the source EvolutionRun relationship.

## CX01 And MIXT-5G Support

CX01 remains an individual analysis example outside the evolver and
demonstrates the upstream generator/analyzer flow.

MIXT-5G is an evolutionary example using the public workflow/evolver boundary.
The architecture supports its scientific pattern:

- scheduled gate mutations across generations;
- independent threshold trajectories;
- strict Pareto feedback;
- no fallback when strict new Pareto candidates are absent;
- generation and frontier summaries.

Those concepts must be configurable policies. MIXT-5G names, paths, and exact
historical run artifacts must not become package branches.

## Current Implementation Boundary

The evolver validates canonical JSON inputs, builds reference-based population
state, applies generic selection and mutation request policies, records
candidate/survivor/archive/analysis refs, and writes validated EvolutionRun
JSON. It does not run analyzer jobs or QNodes.
