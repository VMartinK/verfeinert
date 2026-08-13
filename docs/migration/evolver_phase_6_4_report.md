# Evolver Phase 6.4 Mutation Report

## Summary

Implemented mutation policy, recipe, schedule, and request records.

## Created Files

- `mutation/__init__.py`
- `mutation/ids.py`
- `mutation/policies.py`
- `mutation/requests.py`
- `mutation/schedules.py`

## Behavior

- Supported mutation types are `insert`, `replace`, `remove`, `swap`,
  `reorder`, and `layer_propagation`.
- Mutation requests are deterministic intentions.
- The evolver does not mutate operation lists or construct circuits.

## Validation

Covered by deterministic schedule/request tests in
`tests/test_ansatz_evolver_population_mutation_evaluation.py`.

## Deferred

Operation-level edits remain owned by generator APIs or caller-provided
candidate factories.
