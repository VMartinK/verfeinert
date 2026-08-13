# Metrics Expressibility Audit

Phase 8.0 captured the pre-alignment comparison between Verfeinert v1 expressibility and the then-current Verfeinertv2 analyzer metric. Phase 8.0.1 supersedes the original `D` finding by aligning v2 with the validated v1 methodology.

## Sources

- v1: `Verfeinert/src/ansatz_analyzer/metrics/expressibility.py`
- v1 tests: `Verfeinert/tests/analyzer/test_expressibility_contract.py`
- v2: `Verfeinertv2/verfeinert/ansatz_analyzer/metrics/expressibility.py`
- v2 tests: `Verfeinertv2/tests/test_ansatz_analyzer_phase_5_5_expressibility.py`

## Shared Scientific Definition

Both versions implement the same high-level metric:

- sample pairs of random parameter vectors;
- execute a state-producing circuit callable for each vector;
- compute state fidelity for each pair;
- build an empirical fidelity histogram over `[0, 1]`;
- compare against the Haar fidelity distribution;
- report `D_KL(P_empirical || P_Haar)` and `-log10(max(D_KL, floor))`.

The Haar bin-mass formula is equivalent in intent: for dimension `2**n_qubits`, each equal-width bin mass is `(1 - left)**(dimension - 1) - (1 - right)**(dimension - 1)`.

## Phase 8.0 Pre-Alignment Comparison

| Area | v1 behavior | v2 behavior | Phase 8.0 status |
| --- | --- | --- | --- |
| Formula | KL divergence to Haar fidelity distribution, then `-log10` score | Same formula and score | Equivalent in definition |
| Parameter range | `[0, 2*pi]` | `[0, 2*pi]` | Equivalent |
| Default samples | `n_pairs=5000`, `n_bins=75` | `n_pairs=5000`, `n_bins=75` | Equivalent |
| RNG backend | NumPy `default_rng` | Python stdlib `random.Random` | Different numerical stream |
| Seed derivation | `sha256(base_seed:expressibility:circuit_id)[:8]` for per-circuit policy | shared `stable_metric_seed(base_seed, metric_name, candidate_id)` with the same token shape | Equivalent token shape, different RNG engine |
| RNG policies | `per_circuit` and `global_sequential` | deterministic per-candidate only | Missing v1 global policy |
| Circuit execution | callable with NumPy-like parameter arrays; batch API marks QNodes executed | explicit state callable; QNode execution is permission-gated and usually false | Architectural difference |
| Workload guards | total QNode calls, per-layer circuit limits, parameter-count filters | total state-call guard | v2 is narrower |
| Output shape | pandas tables plus notebook-compatible payload | canonical `MetricRecord` inside AnalysisResult JSON | v2 JSON-first by design |

## Phase 8.0 Scientific Issue

The RNG backend and available RNG policies are not identical. Under the same seed, v1 NumPy `default_rng` and v2 `random.Random` will generally produce different sampled parameter vectors, different fidelity histograms, and therefore different KL values.

This is not a safe implementation correction to make silently. The framework needs a human decision on whether v2 should:

- adopt NumPy RNG for metric equivalence with v1;
- keep stdlib RNG and classify the output as scientifically equivalent but numerically different;
- expose an explicit RNG backend/policy setting.

## Classification

Original Phase 8.0 classification: `D`, requiring human scientific decision.

The formula is preserved, but numerical reproducibility under equivalent configurations is not established because the sampling engine differs from v1.

## Phase 8.0.1 Alignment

The scientific decision was resolved in favor of v1 methodology. Verfeinertv2 expressibility now uses:

- `numpy.random.default_rng`;
- default `rng_policy="per_circuit"`;
- `global_sequential` support through the analyzer pipeline;
- v1-compatible seed derivation;
- v1-compatible Haar/KL and histogram behavior.

Updated classification after alignment: `A` for the tiny deterministic reference fixture.

## Fixture Status

Reference fixtures now live under `tests/fixtures/reference_metrics/`. The tiny fixture compares v1 and v2 for `reference-a02-l1-parent` with `n_pairs=8`, `n_bins=5`, and `rng_seed=123`.
