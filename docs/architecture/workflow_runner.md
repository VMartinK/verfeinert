# Workflow Runner

The `verfeinert.workflow` package is the public orchestration layer for JSON-first Verfeinert workflows. It coordinates the existing module APIs without becoming a new scientific engine.

## Role

`WorkflowRunner` composes:

- public `verfeinert.ansatz_generator` generation and canonical exporters;
- public `verfeinert.ansatz_analyzer` analysis, collections, ranking, and derived table writers;
- public `verfeinert.ansatz_evolver` references, analysis-result ingestion, selection policies, and `EvolutionRun` export.

It does not implement campaign branches, metric algorithms, mutation algorithms, plotting, notebook execution, QNode execution, pandas tables, or legacy adapters.

## Public Records

`WorkflowConfig` defines one run:

- `run_id`;
- caller-owned `input_roots` and `output_root`;
- generation configuration;
- analyzer configuration;
- evolver selection configuration;
- selected stages;
- execution settings;
- random seed and provenance metadata.

`WorkflowResult` is a JSON-safe artifact manifest:

- canonical Candidate JSON paths;
- canonical StagedPackage JSON path;
- AnalysisResult JSON paths;
- EvolutionRun JSON path;
- optional derived ranking JSON/CSV paths;
- survivor and rejected candidate IDs;
- warnings and execution flags.

## Data Flow

The runner implements the current minimal public flow:

```text
candidate records
  -> generator canonical staged package exporter
  -> analyzer structural-cost pipeline
  -> AnalysisResultCollection
  -> evolver selection
  -> EvolutionRun JSON
  -> optional derived ranking artifacts
```

The canonical exchange artifacts remain JSON. Ranking files are derived outputs and are not module-to-module contracts.

## Generation Boundary

The generic generation mode supports Sanz19 records through public generator APIs. Campaign-specific reproduction logic can pass `candidate_records` into a `provided` generation stage. This keeps campaign factories in examples while preserving a campaign-neutral framework.

## Analysis Boundary

The runner calls the analyzer pipeline with explicit configuration. Smoke workflows use `structural_cost` only. Optional scientific metrics can be supplied later through analyzer metric callables and explicit permissions; the workflow runner itself does not calculate them.

## Evolution Boundary

The runner uses evolver selection policies over AnalysisResult JSON documents. It exports reference-based `EvolutionRun` JSON with `candidate_refs`, `analysis_result_refs`, survivor refs, rejected refs, events, configuration, and provenance.

## Output Policy

All writes go below the caller-provided output root:

- `<output_root>/<run_id>/candidates/`;
- `<output_root>/<run_id>/analysis/`;
- `<output_root>/<run_id>/evolution/`;
- `<output_root>/<run_id>/derived_outputs/`.

Output-root separation is enforced with `verfeinert.core.io.ensure_output_root`.

## Limitations

- The runner currently executes a single generation batch per invocation.
- Multi-generation mutation loops remain example-level until a dedicated evolver pipeline is promoted.
- Full expressibility/trainability reproduction is opt-in and requires analyzer runtime callables.
- Visualization hooks remain outside the runner.
