# Evolution Data Model

## Role

EvolutionRun JSON is the canonical run-state record for
`verfeinert.ansatz_evolver`. It records the identity, configuration,
generations, candidate references, survivor/archive references, events, and
provenance of an evolution workflow.

The current schema version is:

```text
verfeinert.evolution_run.v1
```

EvolutionRun JSON is an orchestration record. It is not a replacement for
Candidate JSON or AnalysisResult JSON.

## Document Boundary

Canonical document ownership:

- Candidate JSON owns circuits, operations, parameters, lineage, metadata, and
  candidate provenance.
- AnalysisResult JSON owns metrics, costs, classifications, analysis
  provenance, and candidate references.
- EvolutionRun JSON owns generation state, population membership, mutation and
  selection events, archive membership, stopping state, configuration, and run
  provenance.

EvolutionRun records should reference Candidate IDs and AnalysisResult IDs. It
should not duplicate full candidate or analysis documents unless a future
schema explicitly defines embedded snapshots for archival purposes.

## Top-Level Fields

`schema_version`
: Must be `verfeinert.evolution_run.v1`.

`evolution_run_id`
: Stable identifier for the run.

`run_metadata`
: Run creation time, current status, software version, and Git commit when
available. Status values are `planned`, `running`, `completed`, `failed`, and
`cancelled`.

`configuration`
: JSON-safe snapshot of the effective run configuration.

`generations`
: Ordered generation records.

`provenance`
: Run-level source label, creation time, and input hashes.

`metadata`
: Optional non-canonical annotations. This should not contain campaign-specific
logic or local or project-specific paths.

## Configuration

The existing schema requires:

- `random_seed`;
- `execution`.

The configuration object may also include:

- `experiment_ref`;
- `mutation_policy`;
- `selection_policy`.
- `stopping_policy`.

The effective configuration records the scientific and orchestration choices
needed to resume, branch, audit, or compare compatible runs:

- run ID and output-root policy;
- maximum generations;
- initial candidate/staged-package references;
- random seed or null seed policy;
- mutation schedule and operator probabilities;
- child limits and deduplication keys;
- selection objectives, cost fields, thresholds, tie-breaking, and fallback
  policy;
- stopping conditions;
- execution permissions;
- provenance and input-hash policy.

## Generation Records

Each generation records:

- `generation_index`;
- `candidate_refs`;
- `survivor_refs`;
- `archive_refs`;
- optional generation-local configuration;
- optional event records.

`candidate_refs` contains the candidates produced or considered in that
generation. `survivor_refs` contains selected candidates that may seed the next
generation. `archive_refs` contains candidates retained for accumulated
frontier or run-history purposes.

## Candidate References

The schema-level `candidate_ref` supports:

- `candidate_id`;
- `candidate_uri`;
- `structural_hash`;
- `lineage_hash`.

Use candidate references for population snapshots. Do not embed full Candidate
JSON under `generations`. When the caller needs circuit details, it should load
the referenced Candidate JSON.

Recommended `candidate_uri` values are relative to the run root or artifact
root when written by the evolver. Absolute local paths should be avoided in
portable EvolutionRun documents.

## Analysis Result References

The scientific evaluation boundary is:

```text
Candidate JSON
    -> analyzer
    -> AnalysisResult JSON
    -> evolver selection
```

EvolutionRun must preserve which AnalysisResult documents informed selection.
The current schema supports first-class `generation.analysis_result_refs`
while keeping `verfeinert.evolution_run.v1` compatible with earlier minimal
documents.

Analysis result references use:

```json
{
  "analysis_result_id": "analysis-candidate-001",
  "candidate_id": "candidate-001",
  "analysis_result_uri": "analysis/generation_001/analysis-candidate-001.json",
  "schema_version": "verfeinert.analysis_result.v1",
  "hash": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
}
```

Events may still record analysis lifecycle details, but they are no longer the
only place where AnalysisResult traceability lives.

## Population Snapshots

Population state should be represented through candidate references and events.

Recommended generation roles:

- `parent`: candidate used to produce children;
- `child`: generated candidate awaiting analysis or selection;
- `survivor`: candidate selected for the next generation;
- `archive`: candidate retained in accumulated run memory;
- `rejected`: candidate considered but not selected.

The current schema supports optional `parent_refs` and `rejected_refs`
alongside `candidate_refs`, `survivor_refs`, and `archive_refs`. Population
events can still record richer provenance, but membership does not require
event-only encoding.

Recommended event examples:

```json
{
  "event_type": "population_membership",
  "population_id": "generation-001-parents",
  "role": "parent",
  "candidate_ids": ["candidate-001", "candidate-002"]
}
```

```json
{
  "event_type": "selection_rejection",
  "policy_id": "strict-pareto-v1",
  "candidate_id": "candidate-003",
  "analysis_result_id": "analysis-candidate-003",
  "reason": "dominated_by_accumulated_frontier"
}
```

## Mutation Events

Mutation provenance belongs primarily in child Candidate JSON lineage. The
EvolutionRun should still record mutation events so the run can be audited
without loading every candidate document.

Recommended event fields:

- `event_type="mutation_requested"` or `event_type="mutation_generated"`;
- `policy_id`;
- `recipe_id`;
- `parent_candidate_id`;
- `child_candidate_id`;
- `generation_index`;
- `mutation_type`;
- `operator`;
- `parameters`;
- `status`;
- `warnings`.

Mutation events summarize run orchestration. Candidate JSON remains the source
of truth for full lineage.

## Selection Events

Selection events should record:

- policy ID and version;
- source AnalysisResult IDs;
- selected survivor IDs;
- rejected candidate IDs;
- threshold used when applicable;
- objective names and directions;
- deterministic tie-breaking;
- terminal status;
- warnings.

Fitness-based, Pareto-based, strict-Pareto, and threshold-filter policies can
share this event approach while preserving their policy-specific metadata.

## Archive State

Archive records should use `archive_refs` and optional archive events. The
archive should be deduplicated by structural hash when available and otherwise
by candidate ID only when explicitly configured.

Archive metadata should record:

- deduplication key;
- keep policy;
- previous archive size;
- new candidate count;
- retained candidate count;
- removed duplicate IDs;
- warnings.

## Execution Metadata

EvolutionRun execution metadata must be truthful. The evolver itself does not
execute QNodes or compute metrics. If a broader workflow runs analyzer metrics,
the AnalysisResult JSON provenance records those execution details, and the
EvolutionRun records only that it requested or ingested those results.

Recommended run metadata flags:

- `evolver_executed_metrics=false`;
- `qnodes_executed_by_evolver=false`;
- `analysis_requested=true|false`;
- `analysis_results_ingested=true|false`;
- `selection_executed=true|false`;
- `plots_generated_by_evolver=false`.

The schema allows these flags under `run_metadata.execution`, with
constant-false guards for work the evolver must not perform.

## Source/Input/Output Separation

EvolutionRun documents should use caller-owned roots and relative artifact
references when written. Input roots, output roots, Candidate documents,
AnalysisResult documents, and configuration files should be hashable and
recorded through provenance.

No local paths, external data-processing folders, generated callable package paths, or
notebook paths should appear in public EvolutionRun documents.

## Extension Points

The current schema supports:

- first-class `analysis_result_refs`;
- parent/rejected population refs;
- event records that require `event_type`;
- optional run-level execution flags.

Later schema releases may add:

- stricter typed event variants;
- archive summary structure;
- explicit population snapshot objects;
- richer execution metadata constraints.
