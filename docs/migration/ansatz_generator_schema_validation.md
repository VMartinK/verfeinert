# Ansatz Generator Schema Validation

## Validation Scope

This Phase 3.5 validation checks whether migrated
`verfeinert.ansatz_generator` objects can be represented according to the
canonical Verfeinertv2 JSON data contracts.

The validation is intentionally not a compatibility layer. It does not modify
schemas, generator implementation, analyzer/evolver modules, or historical
Verfeinert code. The tests use local projection helpers to map generator
records into canonical documents.

## Tested Objects

The test suite covers:

- a baseline Sanz19 candidate produced by `build_sanz19_candidate_record`;
- a structurally mutated candidate produced with
  `move_first_gate_to_end_on_wire`;
- deterministic canonical structural hashes based on canonical circuit
  payloads;
- a staged package generated under a temporary caller-provided output root;
- portability scans for generated artifacts and generator imports.

The tests validate canonical projections against:

- `candidate.schema.json`;
- `staged_package.schema.json`.

No QNodes, notebooks, scientific metrics, analyzer workflows, or evolver
workflows are executed.

## Schema Compatibility

The generator has the scientific concepts needed for the canonical candidate
contract:

- backend-independent gates and operations;
- ordered operations;
- parameterized operation markers;
- Sanz19 reference-template construction;
- lineage and mutation concepts;
- metadata-only staged package generation;
- no implicit callable import or QNode execution.

Projected baseline and mutated candidates validate against
`verfeinert.candidate.v1`. Projected staged packages validate against
`verfeinert.staged_package.v1`.

Canonical structural identity is deterministic:

- equivalent generated candidates produce identical canonical structural
  hashes;
- modified circuits produce different canonical structural hashes.

## Discovered Discrepancy

Current generator staged metadata is not yet emitted in canonical Phase 3 JSON
shape. The raw generator output still uses the migrated Beta staging schema:

```text
verfeinert.compiled_candidates.v1
```

The canonical staged package schema expects:

```text
verfeinert.staged_package.v1
```

This is expected for this phase and is covered by a regression test. The test
asserts that raw generator staging does not silently validate as a canonical
staged package.

## Decisions Made

- The schemas were not changed to match the current generator output.
- The generator was not changed during this validation phase.
- Test-local projection helpers are used only to prove representability.
- Raw generator output remains documented as noncanonical until a future export
  layer is implemented.

## Deferred Issues

- Add a public canonical candidate export API in `ansatz_generator`.
- Add a public canonical staged package export API that writes
  `verfeinert.staged_package.v1`.
- Decide whether canonical hash generation belongs in generator or core schema
  helpers.
- Decide how much provenance should be collected automatically during canonical
  export.
- Keep CSV as a derived artifact, not the generator-to-framework exchange
  contract.

## Verification

The focused validation command is:

```text
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_ansatz_generator_schema_contract -q
```

Expected result:

```text
Ran 6 tests
OK
```
