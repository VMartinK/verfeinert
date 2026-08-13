# Ansatz Generator Migration Report

## Created Files

This phase implements the first controlled `ansatz_generator` migration inside
`Verfeinertv2/` only. The existing `Verfeinert/` and
`python/ansatz_generator/` trees were not modified.

Generator source added:

- representation: `operations.py`, `parameters.py`, `connectivity.py`,
  `constraints.py`, `lineage.py`, `candidates.py`, `validation.py`;
- compilation and staging: `compilation.py`, `staging.py`, `campaign_spec.py`;
- templates: `templates/sanz19.py`;
- mutations: `mutations/structural.py`.

Public exports are wired through `verfeinert.ansatz_generator`.

Documentation added:

- `docs/architecture/ansatz_generator.md`;
- `docs/migration/ansatz_generator_migration_report.md`.

Tests added:

- `tests/test_ansatz_generator_operations.py`;
- `tests/test_ansatz_generator_constraints.py`;
- `tests/test_ansatz_generator_compilation.py`;
- `tests/test_ansatz_generator_sanz19_mutations.py`;
- `tests/test_ansatz_generator_dependency_boundaries.py`.

`pyproject.toml` now includes `pytest-cov` in the development extras. No
runtime scientific dependency was added.

## Beta Behavior Reused

The canonical Beta implementation under `Verfeinert/src/ansatz_generator` was
used as the behavioral reference for:

- known gate set and operation normalization shape;
- candidate validation issues;
- candidate alias handling for `circuit_id`, `child_id`, `candidate_id`, and
  `id`;
- `metadata.operations` and `genome.operations` candidate input fallback;
- structural and lineage hash payloads;
- Sanz19 template IDs, supported layers, operation ordering, and metadata
  records;
- structural wire-local mutations;
- callable-source generation text and no-QNode safety flags;
- staged package file names and manifest semantics.

## Alpha Concepts Incorporated Or Rejected

Incorporated as concepts:

- `GateDef` and `GateRegistry` for external gate extensibility;
- `ParameterMap` for stable symbolic parameter mapping;
- stricter connectivity and constraint validation.

Rejected or deferred:

- Alpha genome execution/campaign stack;
- backend compilers;
- visualization modules;
- notebook-specific helpers;
- historical experiment material and generated outputs.

## Deliberate API Changes

- Imports now use the final namespace `verfeinert.ansatz_generator`; no
  compatibility aliases for obsolete top-level imports were added.
- Candidate compilation is record-first and does not return a pandas
  `DataFrame`. CSV files are still supported as a staging artifact using the
  Python standard library.
- Staged package roots are caller-provided and validated through
  `verfeinert.core`; no TFG-local default paths are used.
- Generated callable modules remain optional source artifacts and are not
  imported or executed by the generator.

## Hash And Schema Compatibility

Equivalent normalized candidate records preserve the Beta-compatible hash
payloads. The explicit hash schema is:

```text
verfeinert.generator.candidate_hash.beta_v1
```

Pinned fixture hashes in tests:

```text
structural_hash = 1e570166e0cef6151ea5dac603c2db7d92af4d6f574bc34bea01ac46ec706164
lineage_hash = 9497fa31f16f16c54af63d3783a4aabf54b6b70c2995970c9afc42ae83a1612e
```

Staged package schemas:

```text
verfeinert.compiled_candidates.v1
verfeinert.candidate_compilation_manifest.v1
```

## Verification

Executed from `Verfeinertv2/`:

```text
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
```

Current result:

```text
Ran 23 tests in 0.078s
OK
```

`pytest` remains an optional development tool. It is declared in
`pyproject.toml`, but the visible Python environments used for this migration
do not currently have it installed.

## Deferred Decisions And Risks

- Analyzer and evolver imports remain deferred until their migration phases.
- Visualization remains deferred; generator records only preserve metadata
  needed by a later visualization layer.
- Future backend compilers may need a separate package or optional dependency
  group so the generator runtime stays lightweight.
- Multiprocessing and campaign execution are not part of this generator phase.
- Stricter operation arity validation may reveal invalid legacy metadata during
  later migration; those records should be corrected or explicitly loaded under
  a compatibility mode if a real need appears.
