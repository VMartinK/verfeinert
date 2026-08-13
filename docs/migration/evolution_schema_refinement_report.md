# Evolution Schema Refinement Report

## Summary

Phase 6.1 resolves the minimum EvolutionRun schema gap needed before
implementing `verfeinert.ansatz_evolver`.

The schema remains `verfeinert.evolution_run.v1`. The refinement is additive:
existing minimal EvolutionRun documents remain valid, while production evolver
documents can now reference AnalysisResult JSON explicitly.

## Schema Changes

Updated `schemas/evolution_run.schema.json`:

- added optional `generation.parent_refs`;
- added optional `generation.rejected_refs`;
- added optional `generation.analysis_result_refs`;
- added `$defs.analysis_result_ref`;
- refined `generation.events` so event objects require `event_type`;
- added optional `run_metadata.execution`;
- added optional `configuration.stopping_policy`;
- guarded evolver-forbidden execution flags with constant `false` values:
  `evolver_executed_metrics`, `qnodes_executed_by_evolver`, and
  `plots_generated_by_evolver`.

The required fields were not changed.

## Decisions

- Keep the schema version as `verfeinert.evolution_run.v1` because the change is
  backward-compatible.
- Store population membership as references, not embedded Candidate JSON.
- Store analysis traceability as first-class AnalysisResult references.
- Keep events lightly typed for now: requiring `event_type` gives auditability
  without over-designing every event variant before implementation.

## Documentation Updates

Updated `docs/architecture/evolution_data_model.md` to replace the earlier
schema-blocker language with the refined reference model.

## Validation Additions

Updated schema tests to validate:

- legacy/minimal EvolutionRun documents still pass;
- refined documents with parent, rejected, and analysis-result references pass;
- run execution metadata passes;
- event records without `event_type` fail.

## Deferred Schema Decisions

- stricter event subtypes;
- archive summary structures;
- explicit population snapshot objects;
- richer execution metadata constraints.

These can be addressed after the foundation evolver proves the reference model.
