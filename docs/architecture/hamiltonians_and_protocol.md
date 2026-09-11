# Benchmark Hamiltonians, manuscript protocol and n-qubit evaluation

This note documents the scientific additions that align the analyzer with
*Efficiently Architecting VQAs: Expressibility–Trainability–Resources
Pareto-Optimality* (Sanz et al.) and make every metric usable for an arbitrary
number of qubits.

## Hamiltonians (`verfeinert.ansatz_analyzer.metrics.hamiltonians`)

`HamiltonianSpec(kind, parameters, boundary)` defines the trainability cost
function and the VQE target for any `n`:

| kind | definition | parameters (defaults) |
| --- | --- | --- |
| `local_x` (`sum_x`) | `H = h Σ X_i` | `h = 1` |
| `tfim` (`ising`) | `H = -J Σ Z_i Z_{i+1} - h Σ X_i` | `J = 1`, `h = 1` |
| `heisenberg` (`xxx`) | `H = Σ (Jx XX + Jy YY + Jz ZZ) + h Σ Z_i` | `Jx = Jy = Jz = 1`, `h = 0` |

`boundary` is `open` (chain, manuscript default) or `periodic` (ring). Each spec
exposes `pauli_terms(n)`, `to_pennylane(n)` (a `qml.Hamiltonian` used for
`expval` QNodes), `to_sparse(n)`, `to_dense(n)` (guarded to `n <= 12`),
`ground_state(n)` (exact diagonalization, sparse `eigsh` above 10 qubits) and
`metric_metadata()`.

Trainability metric records keep the historical Local-X fields
(`hamiltonian="local_x"`, `hamiltonian_kind="sum_x"`,
`hamiltonian_definition="H = sum_i X_i"`, `hamiltonian_scale`) and add
`hamiltonian_parameters`, `hamiltonian_boundary` and `hamiltonian_label`.
Comparison compatibility includes the parameters, so results computed for
different couplings are never merged silently.

Configuration (`analyzer.metric_configs.trainability`):

```yaml
trainability:
  hamiltonian: heisenberg          # local_x | tfim | heisenberg (+ aliases)
  hamiltonian_parameters: {Jx: 1.0, Jy: 1.0, Jz: 1.5, h: 0.0}
  hamiltonian_boundary: open
  n_repeats: 3000                  # alias: n_samples
  n_trials: 5
  average_over: all                # all (manuscript Eq. 10) | active (legacy)
```

Legacy `hamiltonian_kind: sum_x` / `hamiltonian_scale` remain valid.

## Trials, equal-mass bins and batching

* `n_trials` (both metrics) repeats the full estimate with independent random
  streams. Trial 0 uses the historical seed, so `n_trials=1` reproduces earlier
  artifacts bit-for-bit. Values report the mean, and `*_std` the sample
  standard deviation (`ddof=1`); per-trial values live in `metadata.trials`.
* `bin_strategy: equal_mass` places fidelity bin edges at Haar quantiles
  `F_k = 1 - (1 - k/n_bins)^(1/(N-1))`, keeping the estimator bias constant as
  `n` grows (manuscript footnote 4). `equal_width` is the legacy default.
* When the state callable comes from analyzer materialization, both metrics
  evaluate parameter batches through PennyLane broadcasting. Random parameters
  are still drawn pair by pair / sample by sample, so batched and sequential
  results are identical for the same seed. Trainability gradients are
  evaluated on an `expval` QNode (`energy_backend =
  pennylane.expval.broadcast`), which avoids dense `2^n x 2^n` matrices;
  explicit user callables keep the dense-matrix path (`dense_matrix.state`).
  Batch sizes are auto-sized from `max_batch_state_elements`.

## Protocol presets (`verfeinert.ansatz_analyzer.metrics.protocol`)

`protocol_metric_configs("paper", n_trials=5, hamiltonian="tfim")` returns the
manuscript sampling (10 000 pairs, 75 equal-mass bins, 3 000 gradient samples,
`θ ∈ [0, 2π)`), `protocol_structural_cost()` the IBM Heron r2 cost weights
`(α, β, γ) = (0.0894, 0.1966, 0.7140)`, `protocol_ranking()` the
`Expr' x Train` composite score and `protocol_pareto()` the cost thresholds
`1.0 / 0.2 / 0.1`. `apply_protocol_to_workflow_mapping` powers the CLI
overrides:

```bash
verfeinert run workflow.yaml --n-qubits 8 --hamiltonian ising \
    --hamiltonian-param J=1 --hamiltonian-param h=0.5 --trials 5 --protocol paper
```

Structural-cost normalization bounds may be omitted; they are then derived
from the analyzed family, which is what makes one workflow file valid for any
qubit count.

## Live engine (`verfeinert.live`)

`LiveEvolutionEngine` composes the public pieces (Sanz19 templates, canonical
Candidate JSON export, materialization, metrics, `CanonicalMutationFactory`)
into a streaming elitist search: evaluate the initial family, keep the
`elite_size` best feasible circuits by score, create `children_per_parent`
random mutations per parent (insert/replace/remove/swap), deduplicate by gate
sequence, evaluate (optionally in worker processes) and repeat. `run_vqe`
optimizes a candidate against the same Hamiltonian with the manuscript VQE
settings and reports the normalized error and ground-state fidelity. The
server in `verfeinert.live.server` exposes both over HTTP/SSE for the UI.
