# Expressibility Alignment Report

Phase 8.0.1 aligns Verfeinertv2 expressibility with Verfeinert v1.

## Changes

- Replaced stdlib `random.Random` sampling with `numpy.random.default_rng`.
- Added v1-compatible `rng_policy` support:
  - `per_circuit` by default;
  - `global_sequential` through analyzer pipeline shared RNG state.
- Preserved v1 sampling range, sample count, bin count, Haar distribution, KL clipping, and `-log10` score.
- Kept canonical `MetricRecord` output and added v1-aligned metadata for RNG backend, policy, seed, calls, and fidelity summary.

## Validation

Tiny deterministic fixture:

- candidate: `reference-a02-l1-parent`
- `n_qubits=2`
- `n_pairs=8`
- `n_bins=5`
- `rng_seed=123`

Result: v1 and v2 match for `dkl` and `expressibility` within test tolerance.

## Classification

`A`: identical methodology for the tested reference fixture scope.
