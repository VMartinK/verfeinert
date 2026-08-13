# Evolver Phase 6.8 State And Stopping Report

## Summary

Implemented stopping-condition records and a minimal pipeline state wrapper.

## Created Files

- `policies/__init__.py`
- `policies/stopping.py`
- `pipeline.py`

## Behavior

- Supports terminal decisions for maximum generations, no candidates, no
  analysis results, no survivors, duplicate-only generations, no strict
  improvement, cancellation, and failure.
- `EvolutionPipelineState` builds an `EvolutionRunState` from append-only
  generation records.
- EvolutionRun configuration now records `stopping_policy.max_generations`.

## Validation

Covered by stopping and pipeline tests in
`tests/test_ansatz_evolver_selection_export.py`.

## Deferred

Long-running runner state, cancellation files, and restart/resume workflows are
not implemented.
