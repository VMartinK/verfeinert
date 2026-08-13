# Phase 10.2 Workflow Architecture Report

Phase 10.2 changes the public workflow runner from a monolithic
generate-analyze-evolve-rank path into an artifact-oriented orchestrator. The
workflow still composes the Verfeinert subsystems, but it now executes only
requested capabilities or unavoidable dependencies that cannot be satisfied by
compatible supplied artifacts.

## Public Model

Workflow configuration now separates:

- scientific execution: `generate`, `analyze`, `evolve`;
- postprocessing: `ranking`, `pareto`, `export_csv`.

`workflow.campaign_type` is explicit and accepts:

- `individual`;
- `evolutionary`.

Individual campaigns may generate, analyze, and postprocess, but cannot request
evolution. Evolutionary campaigns may run or resume evolution.

Legacy `stages` declarations remain accepted for v0.2.0 migration. Both
top-level `stages` and nested `workflow.stages` normalize into the same
scientific/postprocessing representation. If both legacy and structured
declarations are present and conflict, configuration validation fails.

## Artifact Entry Points

`artifacts` can provide persisted workflow inputs:

- `candidates`: canonical Candidate JSON;
- `staged_packages`: canonical StagedPackage JSON;
- `analysis_results`: AnalysisResult JSON files/directories/mappings;
- `evolution_run`: a persisted EvolutionRun JSON document.

The runner uses existing loaders and model validators. It does not introduce a
parallel serialization format.

Examples now supported by the workflow API include:

- `generate -> analyze`;
- `generate -> analyze -> export_csv`;
- `Candidate JSON -> analyze`;
- `StagedPackage -> analyze`;
- `AnalysisResult -> ranking`;
- `AnalysisResult -> Pareto`;
- `persisted EvolutionRun -> resume`.

## No Silent Recomputation

Supplied compatible artifacts satisfy dependencies directly. For example,
`AnalysisResult -> ranking` loads an `AnalysisResultCollection`, runs the
ranking transform, and does not call the analyzer. A requested downstream CSV
export from existing results does not execute QNodes.

If inputs are insufficient or incompatible, workflow raises
`WorkflowConfigError` with a domain-specific reason, such as missing analysis
input, missing ranking metric, incompatible resume state, branch required, or
unresolved evolution parent reference.

## Evolution Resume And Branch

Fresh evolutionary workflow creates an `EvolutionRunState` with G0 from
candidate and analysis references. When `evolver.max_generations` is greater
than the number of existing generations and a `candidate_factory` is supplied,
the runner uses the existing evolver mutation request, candidate factory,
analysis ingestion, and selection APIs to append new generations.

Continuation requires:

- same logical evolution run identity;
- matching continuation-critical evolution fingerprint.

The fingerprint includes campaign type, random seed, execution config, mutation
policy, selection policy, selected analyzer metrics, structural-cost config, and
metric configs. It intentionally excludes output paths and the stopping target
`max_generations`, so extending G2 to G3 is a valid continuation.

When the fingerprint or logical run identity changes, workflow requires explicit
`workflow.resume.mode: branch`. Branch mode creates a new EvolutionRun identity,
copies historical generations without recomputing them, appends any requested
new generations, and stores `metadata.workflow.relationship` with source run,
source generation, source artifact, and source/derived fingerprints.

## Ownership Boundaries

The workflow runner orchestrates only. Candidate/StagedPackage persistence stays
in `ansatz_generator`, including packaging already-canonical Candidate documents.
Scientific metrics and materialization stay in `ansatz_analyzer`. Evolution
state, refs, mutation requests, candidate factory validation, ingestion, and
selection stay in `ansatz_evolver`.

Phase 10.2 does not implement the Phase 10.3 CLI/example migration or the Phase
10.4 comparison and visualization maturation work.
