# Workflow Runner

`verfeinert.workflow` is the public orchestration layer for JSON-first
Verfeinert workflows. It coordinates generator, analyzer, evolver, comparison,
table export, and optional visualization APIs without becoming a scientific
engine.

## Role

`WorkflowRunner` composes:

- public `verfeinert.ansatz_generator` candidate generation and canonical
  Candidate/StagedPackage exporters;
- public `verfeinert.ansatz_analyzer` analysis, collections, Pareto, ranking,
  comparison, and derived table writers;
- public `verfeinert.ansatz_evolver` refs, selection policies, mutation
  requests, generation records, and EvolutionRun persistence;
- optional analyzer visualization functions only when visualization is
  requested.

It does not implement campaign-specific branches, scientific metric
algorithms, PennyLane/QNode construction, mutation algorithms, plotting logic,
or notebook execution.

## Public Configuration

`WorkflowConfig` defines one run:

- `run.run_id`, optional seed and timestamp;
- caller-owned `paths.input_roots` and `paths.output_root`;
- explicit `workflow.campaign_type`: `individual` or `evolutionary`;
- scientific execution operations: `generate`, `analyze`, and optionally
  `evolve`;
- independent postprocessing operations: `ranking`, `pareto`, `comparison`,
  `export_csv`, and `visualization`;
- generation, analyzer, evolver, comparison, artifact, resume, and execution
  configuration blocks.

Legacy `stages` declarations are normalized into the same conceptual model.
Conflicting legacy and structured declarations fail during validation.

## WorkflowResult

`WorkflowResult` is a JSON-safe artifact manifest. It records:

- requested and executed operations;
- consumed, reused, and produced artifacts;
- Candidate, StagedPackage, AnalysisResult, EvolutionRun, ComparisonResult,
  CSV, and visualization paths when produced;
- candidate, analysis, survivor, and rejected IDs;
- warnings;
- workflow provenance.

It is a run manifest, not the canonical scientific artifact replacing the
versioned JSON contracts.

## Data Flow

The runner supports partial and discontinuous flows:

```text
candidate records or persisted Candidate/StagedPackage
    -> analyze
    -> AnalysisResult collection
    -> optional evolve
    -> optional Pareto / ranking / comparison / export / visualization
```

Artifact-only flows are first-class:

```text
AnalysisResult -> ranking -> CSV
AnalysisResult -> Pareto -> CSV
AnalysisResult sources -> ComparisonResult -> CSV
ComparisonResult -> CSV / visualization
EvolutionRun -> resume / branch / lineage visualization
```

The runner does not silently recompute compatible artifacts supplied by the
caller.

## Campaign Type

`individual` workflows may generate and analyze candidates and run
postprocessing. They must not execute evolution and cannot implicitly create an
EvolutionRun.

`evolutionary` workflows may execute `evolve` when a compatible candidate
factory, mutation policy, and parent population are available. Evolution is
still requested explicitly.

## Generation Boundary

The built-in generation families are:

- `sanz19`, a public reference-template generator family;
- `provided`, where the caller supplies candidate records.

Campaign-specific preparation, such as selecting a research seed set or
constructing a reproduction fixture, belongs in examples or caller code. The
framework core consumes candidate records and public factories.

## Analysis Boundary

The runner calls `AnalysisPipeline` with explicit analyzer configuration.
Materialization and QNode execution are owned by `ansatz_analyzer` and require
the analyzer's permissions. The workflow runner records orchestration
provenance but does not calculate metrics.

## Evolution Boundary

The runner uses evolver selection and mutation request APIs over canonical
Candidate and AnalysisResult refs. It exports EvolutionRun JSON with
generations, parent/candidate/survivor/archive refs, analysis refs, events,
configuration, and provenance.

## Resume And Branch

Continuation of a persisted EvolutionRun requires a compatible continuation
fingerprint. Historical generations and historical analysis artifacts are
preserved and not recomputed. If the requested evolution contract changes,
continuation fails unless the caller requests a branch with a new run ID.

Branch provenance records the source EvolutionRun and the branch relationship.

## Comparison And Postprocessing

Comparison uses explicitly configured sources. It validates scientific
compatibility through structured metric/cost provenance and writes
ComparisonResult JSON plus optional CSV. Multiple comparisons can coexist in
one workflow.

Ranking and Pareto consume AnalysisResult collections. CSV exports are
deterministic derived tables and preserve canonical candidate and analysis
refs.

## Visualization

Visualization is optional postprocessing. The runner imports visualization
helpers only for requested visualization operations. Plotting consumes existing
AnalysisResult, Pareto, Ranking, ComparisonResult, or EvolutionRun artifacts
and writes figures under caller-owned output roots.

## Output Policy

All writes go below the caller-provided output root:

```text
<output_root>/<run_id>/candidates/
<output_root>/<run_id>/analysis/
<output_root>/<run_id>/evolution/
<output_root>/<run_id>/derived_outputs/
```

Output-root separation is enforced with `verfeinert.core.io.ensure_output_root`.
Input artifacts may be outside the output root but are recorded as consumed or
reused artifacts.

## Provenance

Workflow provenance records the runner, software version, Git commit when
available, config snapshot, requested operations, executed operations, artifact
reuse, campaign type, resume/branch relationship, and truth flags such as
`notebooks_executed = false` and
`campaign_specific_logic_in_framework = false`.
