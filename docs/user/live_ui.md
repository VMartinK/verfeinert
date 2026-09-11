# Live evolution UI (`verfeinert serve`)

The live UI is a local, dependency-free web application that lets you pick a
target Hamiltonian, the number of qubits and the number of metric trials, watch
an evolutionary ansatz search produce better circuits in real time, and finally
validate the best-scoring circuits with a VQE.

```bash
verfeinert serve                # opens http://127.0.0.1:8765/ in the browser
verfeinert serve --port 9000 --no-browser
```

## What the page does

1. **Hamiltonian** – Local-X, transverse-field Ising (TFIM) or Heisenberg, with
   editable couplings (`h`; `J`, `h`; `Jx`, `Jy`, `Jz`, `h`) and open or
   periodic boundary conditions. The same specification drives the
   trainability metric and the VQE.
2. **System and sampling** – number of qubits `n`, number of independent trials
   (the manuscript uses 3–5), random seed and the sampling protocol:
   * `paper`: 10 000 fidelity pairs, 75 equal-mass bins, 3 000 gradient samples;
   * `fast`: 1 000 pairs, 30 bins, 300 samples;
   * `custom`: your own sample sizes.
3. **Initial population** – any subset of the 19 Sanz19 templates and layer
   counts (`L`). "Pareto del paper" preselects the templates that appear on the
   manuscript Pareto fronts.
4. **Evolution** – generations, elite size (parents kept per generation),
   children per parent, an optional normalized-cost threshold (feasibility
   constraint), parallel worker processes and the allowed mutation types
   (insert, replace, remove, swap). Children are produced with the canonical
   mutation factory, deduplicated structurally and scored with
   `Expr' x Trainability`.

While the run proceeds the page streams events (Server-Sent Events) and updates:

* KPI tiles (generation, evaluated circuits, best score, best Expr'/Train with
  their standard deviations, elapsed time);
* the expressibility–trainability plane with ±1σ error bars, generation
  colours, the empirical Pareto front and the best circuit;
* best score per generation;
* the leaderboard (score, Expr' ± σ, Train ± σ, normalized cost, parameters,
  depth, two-qubit gates) and the event log;
* a circuit diagram for the selected candidate, downloadable as canonical
  Candidate JSON, plus a JSON export of the whole search.

## How a generation works

Generation 0 evaluates every selected template × layer count (any positive
number of layers is accepted). Each later generation then:

1. takes the `elite_size` best feasible circuits of the *whole* leaderboard so
   far as parents (elitist selection, parents survive);
2. creates `children_per_parent` children per parent. Each child is the parent
   with **one** random mutation: the mutation type is drawn among the selected
   types with weights insert 0.4, replace 0.3, remove 0.15, swap 0.15
   (renormalised over the selected types), and its details (gate from the
   pools `rx/ry/rz/h` and `cx/cz/crx/cry/crz`, qubits, position) are random.
   Invalid, no-op or structurally duplicated circuits are discarded and
   redrawn (up to `max_mutation_attempts` = 30 per parent);
3. evaluates the new children only (parents are never re-evaluated).

So a generation simulates `elite_size × children_per_parent` new circuits
(12 with the defaults) regardless of how many mutation types are enabled;
enabling more types only widens the menu each child's single mutation is drawn
from. Mutations accumulate along lineages: a grandchild differs from its
template by two mutations.

## VQE validation

After the search finishes (or is cancelled) choose circuits from the
leaderboard and run the VQE. The default is the manuscript setting (Adam,
learning rate 0.05, 200 steps, 5 random restarts); the *Optimizador* selector
switches to any of the optimizers below while keeping the steps and restarts.
The page shows the live energy trajectories against the exact ground-state
energy `E0`, the final normalized error `|(E - E0) / E0|` (best restart,
mean ± σ), the fidelity with the exact ground state, the mean number of
energy evaluations per restart and the dominant basis-state amplitudes of the
optimized state.

| Key | Optimizer | Family | Uses learning rate | Notes |
| --- | --- | --- | --- | --- |
| `adam` | Adam | gradient | yes | manuscript default (η = 0.05) |
| `gradient_descent` | Gradient descent | gradient | yes | |
| `momentum` | Momentum | gradient | yes | momentum 0.9 |
| `nesterov` | Nesterov momentum | gradient | yes | momentum 0.9 |
| `rmsprop` | RMSProp | gradient | yes | default η = 0.01 |
| `adagrad` | Adagrad | gradient | yes | |
| `qng` | Quantum natural gradient | natural gradient | yes | block-diagonal metric, λ = 10⁻³ |
| `spsa` | SPSA | stochastic | no | two energy evaluations per step |
| `rotosolve` | Rotosolve | analytic | no | one step = one sweep over all parameters |
| `rotoselect` | Rotoselect | analytic | no | also selects the RX/RY/RZ generator of every single-qubit rotation and reports the choice |
| `cobyla` | COBYLA | SciPy | no | `steps` bounds the energy evaluations |
| `nelder_mead` | Nelder-Mead | SciPy | no | |
| `powell` | Powell | SciPy | no | |
| `l_bfgs_b` | L-BFGS-B | SciPy | no | autograd gradients |

Rotosolve and Rotoselect reconstruct the energy along each parameter from its
frequency spectrum (`{1}` for RX/RY/RZ/Ising rotations, `{1/2, 1}` for
controlled rotations, combined when a parameter is shared by several gates),
so every sub-step is an exact minimisation and the trajectory is monotone.
Rotoselect swaps the generators of the candidate's single-qubit rotations; the
result lists the selected generator per parameter (`selected_generators`) and
the `rotation_overrides` needed to rebuild the modified circuit with
`materialize_candidate(..., rotation_overrides=...)`.

Optimizers that converge before `steps` iterations (SciPy methods) pad the
trajectory with the final energy; each restart reports the real `iterations`
and `evaluations`. The selector can be preset with `?optimizer=<key>` in the
page URL.

## HTTP API

The UI is a thin client over a JSON API that can be scripted:

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/catalog` | Hamiltonians, templates, protocol presets, defaults |
| POST | `/api/runs` | Start a run (`LiveRunConfig` JSON) |
| GET | `/api/runs/<id>` | Status and leaderboard |
| GET | `/api/runs/<id>/events` | SSE stream (`?from=<sequence>` to resume) |
| POST | `/api/runs/<id>/cancel` | Cancel |
| GET | `/api/runs/<id>/candidates/<cid>` | Canonical Candidate JSON |
| GET | `/api/runs/<id>/export` | Full export (documents + evaluations) |
| POST | `/api/runs/<id>/vqe` | Start VQE on `candidate_ids` (or `top`) |
| GET | `/api/vqe/<id>/events` | SSE stream of the VQE job |
| POST | `/api/vqe/<id>/cancel` | Cancel the VQE job |

The same engine is available from Python:

```python
from verfeinert.live import LiveRunConfig, run_live_evolution, run_vqe, VQEConfig

engine, result = run_live_evolution(
    {"n_qubits": 6, "hamiltonian": "heisenberg", "n_trials": 5, "protocol": "paper",
     "max_generations": 10, "elite_size": 4, "children_per_parent": 3, "workers": 4},
    emit=print,
)
best = result["leaderboard"][0]["candidate_id"]
vqe = run_vqe(engine.document(best), engine.config.hamiltonian, config=VQEConfig())
rotosolve = run_vqe(engine.document(best), engine.config.hamiltonian, config=VQEConfig(optimizer="rotosolve"))
```

`VQEConfig(optimizer=...)` accepts the keys of the table above (also
`Nelder-Mead`, `L-BFGS-B`, `sgd` style spellings); `optimizer_options`
overrides per-optimizer defaults such as `momentum`, `lam` (QNG), `c` (SPSA) or
`grid_points` (Rotosolve). `verfeinert.live.optimizer_catalog()` returns the
same catalog the UI receives from `GET /api/catalog` (`vqe_optimizers`).

## Performance notes

Metrics use PennyLane parameter broadcasting: all fidelity pairs and gradient
samples of a trial are simulated in batches, so the full manuscript protocol
(5 trials) takes about one second per 4-qubit circuit and grows with
`2**n_qubits`. Use several worker processes for larger populations. Strategies
to scale further are discussed in `PROPUESTA METRICAS.pdf`.
