# Changelog

All notable changes to Verfeinert will be documented in this file.

## Unreleased - n-qubit manuscript protocol, benchmark Hamiltonians, live UI

### Scientific Metrics

- Added `verfeinert.ansatz_analyzer.metrics.hamiltonians` with parametrized
  Local-X, transverse-field Ising (`J`, `h`) and Heisenberg (`Jx`, `Jy`, `Jz`,
  `h`) Hamiltonians for any qubit count (Pauli terms, PennyLane observable,
  sparse/dense matrices, exact ground state). Trainability accepts
  `hamiltonian`, `hamiltonian_parameters` and `hamiltonian_boundary`; legacy
  `hamiltonian_kind: sum_x` / `hamiltonian_scale` still work and Local-X
  metadata is unchanged.
- Added multi-trial estimation (`n_trials`) to expressibility and trainability
  with mean, sample standard deviation and per-trial metadata, equal-mass Haar
  bins (`bin_strategy: equal_mass`) and the `average_over: all` estimator
  (manuscript Eq. 10). `n_trials=1` reproduces earlier artifacts exactly.
- Added PennyLane parameter-broadcast batching for materialized circuits (both
  metrics) and `expval`-QNode gradients for trainability, removing the dense
  `2^n x 2^n` matrix from the materialized path (roughly 40-150x faster).
- Added `verfeinert.ansatz_analyzer.metrics.protocol` presets reproducing the
  manuscript sampling (10000 pairs / 75 equal-mass bins / 3000 gradient
  samples / 5 trials), IBM Heron r2 cost weights, `Expr x Train` ranking and
  Pareto cost thresholds.
- Comparison compatibility now includes Hamiltonian parameters and boundary.

### CLI, Live UI And Examples

- `verfeinert run|validate` accept `--n-qubits`, `--hamiltonian`,
  `--hamiltonian-param NAME=VALUE`, `--trials` and `--protocol paper|fast`.
- Added `verfeinert serve`: a local web UI (`verfeinert.live`) to choose the
  Hamiltonian, qubits and trials, watch an elitist mutation search improve
  circuits in real time (SSE), inspect circuits, export Candidate JSON and run
  the manuscript VQE (Adam, 0.05, 200 steps, 5 restarts) on the best circuits.
- The live VQE (`verfeinert.live.VQEConfig(optimizer=...)`, `POST
  /api/runs/<id>/vqe`, UI selector) supports, besides Adam and gradient
  descent, Momentum, Nesterov, RMSProp, Adagrad, quantum natural gradient,
  SPSA, Rotosolve, Rotoselect and the SciPy methods COBYLA, Nelder-Mead,
  Powell and L-BFGS-B. Rotosolve/Rotoselect use an exact Fourier
  reconstruction per parameter (frequency spectra derived from the gates,
  including controlled rotations); Rotoselect reports the selected RX/RY/RZ
  generators. Results include per-restart `iterations` and `evaluations`;
  `GET /api/catalog` exposes `vqe_optimizers`.
- `materialize_candidate` accepts `rotation_overrides` (operation id ->
  `rx`/`ry`/`rz`) to swap single-qubit rotation generators at execution time.
- `build_sanz19_candidate_record` (and therefore the live UI *Capas* field and
  the CLI `layers`) accepts any positive layer count; `SUPPORTED_SANZ19_LAYERS`
  now only documents the reference sweep `(1, 2, 3)`.
- Added `examples/paper_protocol/` and `docs/user/live_ui.md`,
  `docs/architecture/hamiltonians_and_protocol.md`, and
  `PROPUESTA METRICAS.pdf` (scaling proposals for metric computation).
- `scipy` is now a runtime dependency (sparse Hamiltonians and exact ground
  states); `verfeinert.live` static assets ship as package data.

## v0.4.0 - 2026-08-21 - Declarative Scientific Workflow Productization

### Workflow Product Surface

- Added config-first `verfeinert validate`, `verfeinert run`,
  `verfeinert resume`, and `verfeinert inspect` CLI commands over public
  workflow APIs.
- Completed explicit workflow stage semantics for `generate`, `analyze`,
  `evolve`, ranking, Pareto, comparison, CSV export, visualization, and
  deterministic reports.
- Added strict workflow checkpoint/resume over durable JSON artifacts with
  compatibility fingerprints and artifact hash validation.
- Added workflow event logs, deterministic manifests, traceability JSON/CSV,
  machine-readable reports, and Markdown report rendering.

### Scientific Execution And Determinism

- Added analyzer-owned Candidate-to-PennyLane materialization with explicit
  permissions, resource limits, capability failures, and precedence for
  caller-supplied state callables.
- Added real candidate-level multiprocessing for analyzer/workflow analysis
  stages with fail-closed worker errors and deterministic per-candidate RNG
  behavior.
- Added a dedicated reproducibility equivalence gate comparing sequential run
  A/B, sequential versus multiprocessing, and uninterrupted versus
  checkpoint/resume final state.

### Evolution And Mutation

- Completed campaign-neutral mutation policy execution through generator-owned
  canonical mutation factories for insert, replace, remove, swap, reorder, and
  layer/template propagation.
- Unified stopping and patience governance, including deterministic
  no-improvement state and independent threshold trajectory serialization.
- Moved generation transitions into the evolver state-machine boundary while
  keeping analyzer metric execution outside the evolver.

### Public Reproduction Examples

- Added declarative full-lite CX-01 and MIXT-5G workflow configs that run from
  an installed package through the CLI without campaign-specific Python.
- External validation now installs with visualization support, runs both
  full-lite workflows through the installed console script, checks computed
  expressibility/trainability metrics, and verifies imports resolve from
  site-packages.

Scientific metric definitions, structural-cost semantics, Pareto/ranking
semantics, strict-Pareto behavior, and the frozen publication visualization
contract are unchanged. Global F/F2 visualizations remain out of contract.

## v0.3.2 - 2026-08-21 - Visualization Publication Contract Hardening

### Visualization

- Centralized generic publication objective labels, including Hamiltonian-agnostic
  trainability notation using `T(H)`.
- Hardened publication legends so objective-space legends render above data with
  opaque publication frames.
- Corrected evolution metric-grid labels/titles, shared legend placement,
  generation-frontier color/alpha encoding, and two-panel comparison layout.
- Added prepared `ObjectiveSeries.score` as a keyword-only field for campaign
  frontier score coloring while preserving the positional constructor contract.
- Updated global campaign-frontier, aggregate-bar, contribution, and lineage
  publication legend/headroom semantics.

Scientific metric, Pareto, cost, ranking, mutation, evolution, workflow, CX-01,
MIXT-5G, and multithreshold trajectory semantics are unchanged. Global F/F2
visualizations remain out of contract.

## v0.3.1 - 2026-08-20 - Correctness and Contract Hardening

### Contract corrections

- Synchronized package version metadata across `pyproject.toml`,
  `verfeinert._version`, installed metadata checks, citation metadata, and
  current installation documentation.
- Corrected workflow provenance so runner-generated visualization artifacts set
  the corresponding visualization, figure, and legacy plot-generation flags.
- Added clean CLI handling for missing visualization dependencies when
  visualization output is requested.

### Capability honesty

- Scientific metric definitions are unchanged.
- Pareto, ranking, evolution, strict Pareto feedback, CX-01, MIXT-5G, and
  multithreshold trajectory semantics are unchanged.
- Multiprocessing executor primitives remain available in `verfeinert.core`,
  but scientific workflow/analyzer multiprocessing integration remains
  deferred.
- Candidate JSON remains more expressive than the current PennyLane
  materializer; unsupported gate identities, derived parameters, and unsupported
  runtime parameter forms now fail closed with explicit materialization errors.
- Broader workflow architecture work remains deferred to v0.4.0.

### Maintenance

- Migrated production schema validation from deprecated
  `jsonschema.RefResolver` usage to a packaged-schema `referencing` registry.
- Updated current docs/docstrings that overstated analyzer and visualization
  terminology.

## 0.3.0 - 2026-08-16

### Visualization

- Added immutable semantic visualization models for prepared objective points,
  metric series, bar series, and publication tables.
- Promoted `DEFAULT_STYLE` to publication-grade defaults with
  `PublicationLayouts`, ordered palettes, semantic role styles, and canonical
  PNG/PDF/SVG export formats.
- Added Individual, Evolution, and Global analysis publication renderers over
  already-prepared semantic data.
- Added `save_publication_figure` for guarded multi-format publication export
  with deterministic PNG/PDF/SVG output.

### Validation

- Added structural golden tests for the frozen publication figure families.
- Added scientific-boundary tests ensuring visualization renderers do not
  import metric implementations or call Pareto, dominance, ranking, selection,
  evolution, or top-lineage selection internals.

Visualization consumes prepared scientific results. It does not recompute
Trainability, Expressibility, structural cost, Pareto membership, dominance,
combined scientific score, ranking, selection, evolution, or top-lineage
selection.

## 0.2.0 - 2026-08-13

### Scientific execution

- Added analyzer-owned Candidate/StagedPackage to PennyLane materialization for
  canonical circuit records.
- Added real Expressibility and Trainability execution from canonical
  candidates when QNode and expensive-metric permissions are explicitly granted.
- Preserved bounded structural-cost workflows as the default inexpensive
  validation path.

### Workflow

- Added explicit individual and evolutionary campaign semantics.
- Added artifact-oriented partial and discontinuous workflows without silent
  upstream recomputation.
- Added persisted evolution resume behavior with continuation versus branch
  semantics.

### Public reproducibility

- Migrated CX-01 to the public individual workflow example with smoke and full
  profiles.
- Migrated MIXT-5G to the generic evolutionary workflow path with smoke and
  full profiles.
- Strengthened third-campaign portability through public APIs, configuration,
  and the thin `verfeinert run` CLI.

### Postprocessing

- Added standard Pareto, ranking, structured comparison/global analysis, and
  deterministic CSV/JSON export paths.
- Added optional visualization support with neutral `DEFAULT_STYLE` semantics.

### Persistent contracts

- Added first-class `ComparisonResult` JSON/schema validation.
- Strengthened public artifact contracts for Candidate, StagedPackage,
  AnalysisResult, EvolutionRun, and comparison outputs.

### Validation and limitations

- Release validation uses bounded smoke profiles for CX-01 and MIXT-5G; full
  scientific reproductions remain explicit opt-in workflows.
- Broad arbitrary external CSV ingestion remains deferred.
- Known `jsonschema.RefResolver` deprecation debt remains deferred.

## 0.1.0 - Framework Foundation

- Established the `verfeinert` Python namespace.
- Added `core` configuration, execution, I/O, metadata, hashing, validation, and
  packaged schema-resource helpers.
- Added canonical JSON schemas and schema examples.
- Migrated generator foundations and public canonical Candidate/StagedPackage
  exporters.
- Added analyzer foundations, collections, Pareto/ranking, visualization hooks,
  and v1-aligned expressibility/trainability metrics.
- Added evolver foundations for candidate/analysis references, mutation
  requests, selection, stopping, and EvolutionRun export.
- Added workflow runner plus CX-01 and MIXT-5G smoke reproduction examples.
- Added package-hardening, CI, and external-validation preparation.
