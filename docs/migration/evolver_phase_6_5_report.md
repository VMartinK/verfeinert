# Evolver Phase 6.5 Generator Boundary Report

## Summary

Implemented the candidate-factory boundary.

## Created Files

- `candidate_factory.py`

## Behavior

- Defines `CandidateFactory` as a public callable protocol.
- `produce_candidate_from_request()` validates parent and child Candidate JSON.
- The child candidate must preserve parent ID, generation index, and mutation
  type in canonical lineage.

## Validation

The test factory uses public generator/exporter APIs only and validates a
synthetic child Candidate JSON.

## Deferred

No MIXT-5G factory or full runner was added.
