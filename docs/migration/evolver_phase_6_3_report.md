# Evolver Phase 6.3 Population Report

## Summary

Implemented reference-only population helpers.

## Created Files

- `population/__init__.py`
- `population/refs.py`
- `population/snapshots.py`
- `population/deduplication.py`

## Behavior

- Population snapshots store ordered `CandidateRef` records only.
- Deduplication supports `candidate_id`, `structural_hash`, and `lineage_hash`.
- Deduplication emits an audit report with retained, removed, and missing-key
  candidate IDs.

## Validation

Covered by population tests in
`tests/test_ansatz_evolver_population_mutation_evaluation.py`.

## Deferred

Archive summary tables and long-run population persistence remain future work.
