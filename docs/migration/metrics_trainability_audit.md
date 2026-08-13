# Metrics Trainability Audit

Phase 8.0 captured the pre-alignment comparison between Verfeinert v1 trainability and the then-current Verfeinertv2 analyzer metric. Phase 8.0.1 supersedes the original `D` finding by aligning v2 with the validated v1 methodology.

## Sources

- v1: `Verfeinert/src/ansatz_analyzer/metrics/trainability.py`
- v1 tests: `Verfeinert/tests/analyzer/test_trainability_contract.py`
- v2: `Verfeinertv2/verfeinert/ansatz_analyzer/metrics/trainability.py`
- v2 tests: `Verfeinertv2/tests/test_ansatz_analyzer_phase_5_6_trainability.py`

## Shared Scientific Definition

Both versions implement an empirical Local-X trainability proxy:

- sample random parameter vectors;
- compute the expectation value of `H = sum_i X_i`;
- evaluate parameter gradients;
- filter inactive parameters using an active-gradient tolerance;
- report the mean squared active gradient as `trainability`, `holmes_metric`, and `mean_squared_gradient_active`.

Both versions explicitly reject TFIM-style Hamiltonian selection.

## Phase 8.0 Pre-Alignment Comparison

| Area | v1 behavior | v2 behavior | Phase 8.0 status |
| --- | --- | --- | --- |
| Hamiltonian | dense `sum_x` matrix built from Kronecker products | dense/list Local-X matrix plus direct expectation helper | Equivalent Local-X intent |
| Hamiltonian naming | `hamiltonian_kind="sum_x"` | `hamiltonian="local_x"` | Naming differs, definition matches |
| Parameter range | `[-pi, pi]` | `[-pi, pi]` | Equivalent |
| Default repeats | `n_repeats=5000`, alias `trainability_n_pairs` | `n_repeats=5000` | Equivalent sample count, v2 lacks alias |
| RNG backend | NumPy `default_rng` | Python stdlib `random.Random` | Different numerical stream |
| Seed derivation | `sha256(base_seed:trainability:circuit_id)[:8]` for per-circuit policy | shared `stable_metric_seed(base_seed, metric_name, candidate_id)` with the same token shape | Equivalent token shape, different RNG engine |
| Gradient method | PennyLane autodiff via `qml.grad` | central finite difference with configurable step | Scientifically material difference |
| Active-gradient logic | parameter active if any repeat is nonzero beyond tolerance | same conceptual rule | Equivalent intent |
| Output shape | pandas tables plus notebook-compatible payload | canonical `MetricRecord` inside AnalysisResult JSON | v2 JSON-first by design |

## Phase 8.0 Scientific Issue

The gradient computation is not equivalent. v1 differentiates the energy function with PennyLane autodiff. v2 approximates the gradient using central finite differences over explicit state callables.

This can change values even when the Hamiltonian, sampled parameters, circuit callable, and active-gradient threshold are otherwise aligned. It may still be an acceptable scientific approximation for a dependency-light framework, but that is a methodology decision and cannot be made silently in the release-preparation phase.

The RNG backend also differs, so sampled parameters are not expected to match v1 under the same seed.

## Classification

Original Phase 8.0 classification: `D`, requiring human scientific decision.

Local-X methodology is preserved and TFIM is not introduced, but numerical equivalence to v1 trainability is not established because v2 changes the gradient method and RNG engine.

## Phase 8.0.1 Alignment

The scientific decision was resolved in favor of v1 methodology. Verfeinertv2 trainability now uses:

- PennyLane autodiff via `qml.grad`;
- `numpy.random.default_rng`;
- PennyLane NumPy parameter arrays with `requires_grad=True`;
- default `rng_policy="per_circuit"`;
- `global_sequential` support through the analyzer pipeline;
- `hamiltonian_kind="sum_x"` with `hamiltonian="local_x"` accepted only as a normalized alias.

Finite differences are no longer the reference trainability path.

Updated classification after alignment: `A` for the tiny deterministic reference fixture.

## Fixture Status

Reference fixtures now live under `tests/fixtures/reference_metrics/`. The tiny fixture compares v1 and v2 for `reference-a02-l1-parent` with `n_repeats=3` and `rng_seed=123`.
