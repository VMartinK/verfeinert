# Architecture Documentation

These documents define the current public architecture of Verfeinert. JSON is
the canonical exchange format between modules. CSV, plots, examples, and
notebooks are derived interfaces over versioned records.

## Module Ownership

- `core` owns shared serialization, validation helpers, schema resources,
  hashing, metadata, execution configuration, and path guards. It does not own
  scientific semantics.
- `ansatz_generator` owns backend-independent candidate construction,
  structural mutation primitives, canonical Candidate/StagedPackage export, and
  metadata-only callable source generation. It does not import or execute
  PennyLane/QNodes at runtime.
- `ansatz_analyzer` owns materialization, PennyLane-backed scientific
  execution, metrics, AnalysisResult records, structural cost, Pareto, ranking,
  comparison, table exports, and optional visualization adapters.
- `ansatz_evolver` owns candidate refs, selection, mutation requests,
  generations, lineage, EvolutionRun persistence, resume, and branch state. It
  consumes analyzer results instead of computing metrics.
- `workflow` owns orchestration, artifact dependency resolution,
  discontinuous execution, resume/branch coordination, and orchestration
  provenance. It is not a scientific backend.
- `verfeinert.cli` is a thin entry point: parse args, load config, call the
  public workflow API, and print a structured result.

## Artifact Flow

Not every workflow uses every artifact, but the supported end-to-end flow is:

```text
Candidate / StagedPackage
    -> AnalysisResult
    -> EvolutionRun when requested and applicable
    -> Pareto / Ranking
    -> ComparisonResult
    -> JSON / CSV
    -> optional Visualization
```

Stages are artifact transformations. Compatible persisted artifacts can be
loaded as entry points without rerunning unrelated upstream work.

## Persistent Contracts

First-class persisted contracts are versioned JSON documents:

- Candidate: canonical scientific candidate identity and circuit structure.
- StagedPackage: ordered candidate package and source/export metadata.
- AnalysisResult: metrics, cost, classifications, candidate refs, and analyzer
  provenance.
- EvolutionRun: generations, candidate/analysis refs, events, selection state,
  resume/branch metadata, and evolver/workflow provenance.
- ComparisonResult: explicit sources, compatibility report, global Pareto,
  ranking rows, cost eligibility, and comparison provenance.

Root schemas under `schemas/` mirror packaged schemas under
`verfeinert/schemas/`. Runtime schema resources load from the packaged
resources so installed packages do not depend on repository-relative paths.

Ranking/Pareto JSON and WorkflowResult manifests are derived outputs. Their
schema-version labels identify transform payloads, but durable module-to-module
exchange remains the first-class contracts above unless a future release
promotes additional schemas.

## Scientific Execution And Postprocessing

Scientific execution operations are:

- `generate`;
- `analyze`;
- `evolve`, only for evolutionary workflows.

Postprocessing operations are independently selectable:

- Pareto;
- ranking;
- comparison;
- tables and CSV/JSON export;
- visualization.

The public workflow model preserves this distinction even though the runner has
separate internal handlers.

## Discontinuous Workflow

Supported discontinuous entry points include:

- `Candidate` or `StagedPackage` -> analyze;
- `AnalysisResult` -> ranking/Pareto/comparison/export/visualization;
- persisted `EvolutionRun` -> resume or branch;
- selected compatible runs -> comparison;
- persisted `ComparisonResult` -> CSV or visualization.

Existing compatible artifacts are consumed or reused. They are not silently
recomputed.

## Resume And Branch

Evolution continuation uses a fingerprint of the compatible evolution contract.
If the requested run changes comparison-critical evolution configuration,
continuation fails and the caller must request a branch. Branches preserve
source evolution provenance while producing a new run identity.

## Identity And Provenance

Candidate JSON owns canonical scientific identity. Downstream records propagate
that identity through `candidate_ref` and structured semantic metadata. They do
not create a second independent candidate ID system.

Lineage, root/parent, generation, layer, run, mutation, and source roles are
structured fields with clear owners. Display aliases are presentation metadata
only and never mutate canonical identity.

Analyzer provenance owns metric execution details and materialization/QNode
truth flags. Evolver provenance owns selection and evolution state. Workflow
provenance owns orchestration. Comparison provenance owns explicit source
selection and compatibility fingerprints.

## Scientific Comparison

Comparison is a structured postprocessing transform over explicitly selected
`AnalysisResult` sources. Compatibility is based on metric and cost provenance:
trainability Hamiltonian, trainability config, expressibility config,
structural-cost model and normalization, score definitions, Pareto objectives
and directions, thresholds, and other requested analysis dimensions.

Comparison ignores irrelevant output paths and display labels. It never uses
campaign names as compatibility evidence.

## Optional Visualization

Visualization lives under `verfeinert.ansatz_analyzer.visualization`.
Matplotlib is optional and required only when plot functions or figure export
are called. The public default style is campaign-neutral publication-grade
`DEFAULT_STYLE`; there is no
thesis mode or automatic research-specific renaming.

Raw visualization reference notebooks and private/global-export data are
development material, not runtime or package dependencies.

## Document Map

- `core.md`: shared primitives and dependency boundaries.
- `data_model.md`: canonical artifacts, identity, and provenance.
- `schemas.md`: schema versioning and JSON Schema contracts.
- `data_and_output_policy.md`: source/input/output separation.
- `execution.md`: local execution policy.
- `ansatz_generator.md` and `ansatz_generator_exporters.md`: generator
  ownership and persistence.
- `ansatz_analyzer_design.md`, `analyzer_foundation.md`,
  `analyzer_collections.md`, `pareto.md`, `ranking.md`, and `comparison.md`:
  analyzer, postprocessing, tables, and comparison.
- `ansatz_evolver_design.md`, `evolver_foundation.md`, and
  `evolution_data_model.md`: evolver state, selection, mutation, and
  EvolutionRun.
- `workflow_runner.md`: public orchestration.
- `visualization.md` and `visualization_system.md`: optional plotting,
  centralized style, and export boundaries.
