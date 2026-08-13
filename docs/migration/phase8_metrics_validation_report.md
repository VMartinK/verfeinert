# Phase 8 Metrics Validation Report

## Summary

Phase 8.0 identified scientific metric discrepancies and paused at Checkpoint A. Phase 8.0.1 then aligned Verfeinertv2 with the validated Verfeinert v1 methodology.

The previous `D` classifications are superseded by the 8.0.1 alignment work.

## Environment

The repository virtual environment was used for numeric reference validation:

- `numpy`: available
- `pandas`: available
- `pennylane`: available
- `joblib`: available

The system Python still lacks these dependencies, so Phase 8.0.1 treats scientific dependencies as required project dependencies rather than optional conveniences.

## Metric Classification

| Metric | Classification | Reason |
| --- | --- | --- |
| Expressibility | `A` | v2 now uses NumPy `default_rng`, v1-compatible seed derivation, and v1-compatible `per_circuit` and `global_sequential` policies. Tiny deterministic v1/v2 fixture values match. |
| Trainability | `A` | v2 now uses PennyLane autodiff via `qml.grad`, NumPy/PennyLane parameter initialization, and the Local-X `sum_x` Hamiltonian. Tiny deterministic v1/v2 fixture values match. |

## Required Stop

Checkpoint A requires all metric differences to be `A` or `B` before package hardening, CI, external validation, and release readiness work can continue.

Because both metrics are now classified `A` for the tested reference fixture scope, Checkpoint A is satisfied for Phase 8.0.1.

## Affected Modules

- `verfeinert.ansatz_analyzer.metrics.expressibility`
- `verfeinert.ansatz_analyzer.metrics.trainability`
- analyzer pipeline paths that execute optional metrics
- CX-01 and MIXT-5G full reproduction modes, if they later enable expensive scientific metrics

## Scientific Impact

Expressibility and trainability smoke tests remain deterministic inside v2 and now use v1-aligned scientific methodology. Full reproduction still requires larger campaign-scale fixtures, but no remaining metric-definition compromise is known at this checkpoint.

## Alignment Decisions

- V1 methodology is authoritative.
- Expressibility uses `numpy.random.default_rng`.
- Trainability uses PennyLane autodiff and not finite differences.
- Local-X remains the only trainability Hamiltonian.
- NumPy and PennyLane are base scientific dependencies.

## Tests Added

Updated `tests/test_metrics_reference_validation.py`.

The test now:

- verifies v1/v2 metric source files are available in the current TFG context;
- asserts that v2 no longer uses stdlib RNG for expressibility;
- asserts that v2 uses `qml.grad` and no central finite-difference gradient path;
- compares tiny deterministic v1/v2 expressibility values;
- compares tiny deterministic v1/v2 trainability values;
- verifies committed reference fixture files are present.

## Validation Maintenance

Full-suite validation exposed an existing staged-package schema resolver issue: after resolving embedded Candidate records, local staged-package refs could be interpreted against the Candidate schema by legacy `RefResolver` call sites. The staged-package schema now qualifies its cross-schema Candidate ref and package-local artifact/provenance refs with stable schema URIs. This changes no canonical fields or payload shapes.

## Deferred Phases

Phase 8.1 package hardening, Phase 8.2 CI/CD, Phase 8.3 external validation, and Phase 8.4 release readiness were not executed in this slice. They may proceed after review of this Checkpoint A update.
