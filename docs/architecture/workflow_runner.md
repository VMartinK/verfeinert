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

## Stage Execution

`WorkflowRunner.run()` builds one normalized stage plan from `WorkflowConfig`
and dispatches it through explicit stage executors:

- generation writes canonical Candidate/StagedPackage artifacts;
- analysis builds analyzer configuration and runs/reuses AnalysisResult
  artifacts;
- evolution writes EvolutionRun artifacts through evolver-owned state
  transitions;
- postprocessing writes ranking, Pareto, comparison, CSV, and visualization
  artifacts.

Each executor receives only the artifacts and configuration needed for its
stage. Downstream stages are not inferred from missing inputs: for example,
`analyze` does not generate candidates, and postprocessing over persisted
AnalysisResult artifacts does not run analyzer or evolver stages. Scientific
work remains delegated to the owning public module.

## WorkflowResult

`WorkflowResult` is a JSON-safe artifact manifest. It records:

- requested and executed operations;
- consumed, reused, and produced artifacts;
- Candidate, StagedPackage, AnalysisResult, EvolutionRun, ComparisonResult,
  CSV, visualization, checkpoint, event-log, manifest, and traceability paths
  when produced;
- candidate, analysis, survivor, and rejected IDs;
- warnings;
- workflow provenance.

It is the in-memory return object for Python callers. The persisted
`workflow_manifest.json` described below is the durable run manifest. Neither
artifact replaces the versioned canonical scientific JSON contracts.

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

`generation.constraints` is an optional declarative `ConstraintSet` snapshot.
When present, workflow routes it to canonical Candidate export, validates
loaded Candidate/StagedPackage artifacts before analysis or evolution,
validates every child returned by a candidate factory, persists it under
EvolutionRun mutation configuration, and includes it in the evolution
compatibility fingerprint. Concrete gate and connectivity checks stay in
`ansatz_generator`; workflow does not duplicate generator validation rules.

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

## Workflow Checkpoints

`workflow.checkpoint.enabled: true` writes an atomic
`WorkflowCheckpoint` JSON document under
`<output_root>/<run_id>/checkpoints/latest.json`. The checkpoint records the
effective config, a path-independent workflow compatibility fingerprint,
completed stages, seed/execution state, consumed/reused/produced artifact refs,
and hashed canonical artifact refs.

`workflow.resume.checkpoint` resumes from a checkpoint artifact. Resume is
strict: the checkpoint run ID and compatibility fingerprint must match the
requested workflow, checkpointed artifact hashes must still match on disk, and
already completed generation/analysis stages cannot be requested again.
Checkpoint artifact refs are routed through the same public Candidate,
StagedPackage, AnalysisResult, ComparisonResult, and EvolutionRun entry points
as caller-supplied artifacts. Evolution continuation still uses the
evolver-owned EvolutionRun state-machine boundary.

## Observability

`workflow.observability.event_log.enabled: true` writes a deterministic JSONL
workflow event log under
`<output_root>/<run_id>/observability/events.jsonl`. Events are JSON-safe
`WorkflowEvent` records with monotonic sequence numbers, event type, run ID,
optional stage/status/reason/message, and compact metadata.

Python callers may also pass `event_sink` to `WorkflowRunner.run()` or
`run_workflow()`. The sink receives `WorkflowEvent` objects in the same order
as the event log. Observer errors are governed by
`workflow.observability.observer_error_policy`: `raise` fails truthfully, while
`record_warning` records an `observer_error` event and includes a workflow
warning without changing scientific execution order.

## Run Manifest And Traceability

Every successful run writes deterministic audit exports under:

```text
<output_root>/<run_id>/manifest/workflow_manifest.json
<output_root>/<run_id>/manifest/workflow_traceability.json
<output_root>/<run_id>/manifest/workflow_traceability.csv
```

`workflow_manifest.json` records the run ID, Verfeinert version, effective
workflow config snapshot and stable config hash, seed policy, execution mode
and worker count, materialization and constraint configuration, requested and
completed stages, consumed/reused/produced artifact refs, key artifact paths,
warnings, checkpoint/event-log refs when present, and the final evolution
stopping reason when an EvolutionRun is available.

`workflow_traceability.json` and `workflow_traceability.csv` are derived audit
tables with a fixed column order. Rows are keyed by canonical candidate IDs and
include available structural and lineage hashes, generation, parent candidate
ID from Candidate lineage when available, AnalysisResult ID, computed
expressibility/trainability/structural-cost values, survivor/rejected/archive
roles from EvolutionRun refs, and final stopping reason. Missing or skipped
metrics remain null in JSON and blank in CSV; workflow does not fabricate
metric values. When a workflow reuses a persisted EvolutionRun, traceability
loads candidate and analysis documents through EvolutionRun refs when their
URIs are available and otherwise preserves the ref-level audit row.

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

`workflow.visualization.profile` defaults to `generic`, preserving the existing
artifact-derived Pareto/ranking/comparison/lineage figures. Setting
`profile: publication` opts into the frozen publication renderers through
public prepared-data adapters. The publication profile supports configured
`figure_set` values (`individual`, `evolution`, or `auto`), optional explicit
figure names, and `png`/`pdf`/`svg` export formats. Individual publication
figures are prepared from computed AnalysisResult objective metrics and
candidate semantics; evolution publication figures consume EvolutionRun
generation refs and, when available, AnalysisResult refs. Missing objective
metrics skip objective-space figures rather than fabricating values. Global
publication figures remain a multi-run prepared-artifact concern instead of
being inferred inside one run-scoped workflow.

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
available, config snapshot, normalized stage plan, requested operations,
executed operations, artifact reuse, campaign type, resume/branch relationship,
and truth flags such as
`notebooks_executed = false` and
`campaign_specific_logic_in_framework = false`.

Flags ending in `_by_runner` describe work directly executed or exported by
`WorkflowRunner`, not work delegated to analyzer/evolver APIs. For example,
`qnodes_executed_by_runner` remains false even when analyzer-owned metric
execution records QNode work in AnalysisResult provenance. When workflow
visualization is requested and figures are written, `visualization_executed`,
`figure_exported`, and the legacy `plots_generated_by_runner` flag are all
true. Workflows without visualization leave those figure flags false.
