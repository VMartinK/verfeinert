# Trainability Alignment Report

Phase 8.0.1 aligns Verfeinertv2 trainability with Verfeinert v1.

## Changes

- Replaced central finite differences with PennyLane autodiff via `qml.grad`.
- Preserved Local-X methodology: `H = sum_i X_i`.
- Added v1-compatible NumPy RNG and PennyLane NumPy parameter initialization.
- Normalized configuration to `hamiltonian_kind="sum_x"` and `trainability_n_pairs`.
- Kept `hamiltonian="local_x"` only as a normalized input alias.
- Rejected `finite_difference_step` in reference metric configuration.

## Validation

Tiny deterministic fixture:

- candidate: `reference-a02-l1-parent`
- `n_qubits=2`
- `n_repeats=3`
- `rng_seed=123`

Result: v1 and v2 match for `trainability_score`, `holmes_metric`, active-parameter counts, gradient variance, gradient mean, and mean absolute gradient within test tolerance.

## Classification

`A`: identical methodology for the tested reference fixture scope.
