# User Documentation

These guides describe reproducible researcher workflows built on public
`verfeinert` APIs. They are current user-facing documentation, while
`docs/migration/` remains historical implementation context.

## Installation

From a GitHub release wheel once downloaded:

```bash
python -m pip install ./verfeinert-0.4.0-py3-none-any.whl
```

From a repository checkout:

```bash
python -m pip install .
```

For development and test work:

```bash
python -m pip install -e ".[dev]"
```

Plotting is optional:

```bash
python -m pip install ".[visualization]"
```

NumPy, PennyLane, PyYAML, and JSON Schema support are standard runtime
dependencies because Verfeinert includes analyzer-owned scientific execution.
Matplotlib is required only for visualization calls.

Scientific analyzer and workflow analysis stages support sequential execution
by default and explicit candidate-level multiprocessing through
`execution.mode: multiprocessing`, `parallelize_candidates: true`, and a
positive `worker_count`. Multiprocessing is fail-closed: unpicklable callables,
worker failures, or order-dependent `global_sequential` RNG policy are rejected
rather than run sequentially in disguise.

## Minimal Individual Campaign

An individual campaign generates and analyzes selected candidates without
evolution:

```yaml
run:
  run_id: minimal-individual
paths:
  output_root: outputs/minimal-individual
workflow:
  campaign_type: individual
  scientific_execution: [generate, analyze]
  postprocessing: [ranking, export_csv]
generation:
  family: sanz19
  template_ids: [A02]
  layers: [1]
  n_qubits: 4
  candidate_id_prefix: demo
analyzer:
  selected_metrics: [structural_cost]
  structural_cost:
    reference_bounds:
      parameter_count: {min: 0, max: 32}
      depth: {min: 0, max: 64}
      two_qubit_operation_count: {min: 0, max: 16}
  ranking:
    score_components: {cost.structural_cost: 1.0}
    combination: weighted_sum
    ascending: true
```

Run it with the CLI:

```bash
verfeinert validate workflow.yaml
verfeinert run workflow.yaml
```

or with Python:

```python
from verfeinert.workflow import WorkflowConfig, WorkflowRunner

result = WorkflowRunner(WorkflowConfig.from_mapping(config)).run()
```

## CLI Surface

The non-interactive CLI is a thin wrapper over public workflow APIs:

```bash
verfeinert validate workflow.yaml
verfeinert run workflow.yaml
verfeinert resume outputs/run-root-or-checkpoints/latest.json
verfeinert inspect outputs/run-id/reports/workflow_report.json
```

`validate` checks config normalization without running science. `run` executes
the requested workflow operations. `resume` accepts a checkpoint JSON path or a
run directory containing `checkpoints/latest.json`. `inspect` renders workflow
reports or checkpoint summaries for humans.

## Evolutionary Campaign

An evolutionary campaign keeps the same public workflow API and adds `evolve`
plus a declarative mutation policy:

```yaml
workflow:
  campaign_type: evolutionary
  scientific_execution: [generate, analyze, evolve]
evolver:
  selection_mode: fitness
  metric_name: structural_cost
  direction: minimize
  keep: 1
  max_generations: 3
  mutation_policy:
    policy_id: demo-insert-schedule
    variants_per_parent: 1
    candidate_factory: {type: canonical}
    recipes:
      - recipe_id: crx_insert
        mutation_type: insert
        parameters:
          gate: crx
          edge: [0, 1]
```

The workflow owns orchestration only. The generator owns candidate construction,
the analyzer owns metric execution/materialization, and the evolver owns
selection, mutation requests, generation state, stopping, and checkpointable
EvolutionRun state.

## Artifact Reuse

Verfeinert workflows are artifact transformations. Existing compatible
artifacts are consumed, reused, or transformed without silent upstream
recomputation:

- `Candidate` or `StagedPackage` -> `analyze`;
- `AnalysisResult` -> ranking, Pareto, comparison, CSV, optional visualization;
- persisted `EvolutionRun` generation -> resume or branch;
- selected compatible `AnalysisResult` sources -> `ComparisonResult`;
- `ComparisonResult` -> CSV export or optional visualization.

Comparison requires explicit source selection:

```yaml
workflow:
  campaign_type: individual
  scientific_execution: []
  postprocessing: [comparison, export_csv]

comparisons:
  - comparison_id: selected-runs
    sources:
      - source_id: run-a
        analysis_results: [artifacts/run-a/analysis]
      - source_id: run-b
        analysis_results: [artifacts/run-b/analysis]
    objectives:
      - {metric_name: trainability, direction: maximize}
      - {metric_name: expressibility, direction: maximize}
```

Compatibility is provenance-based. Hamiltonian definitions, metric
configuration, structural-cost normalization, objectives, directions,
thresholds, and ranking score definitions are checked where relevant. Output
paths and display aliases are ignored for compatibility.

## Checkpoints, Manifests, And Traceability

Enable workflow checkpointing with:

```yaml
workflow:
  checkpoint:
    enabled: true
```

The checkpoint is written to
`<output_root>/<run_id>/checkpoints/latest.json`. Resume is strict: run ID,
workflow compatibility fingerprint, scientifically relevant configuration, and
artifact hashes must match. Completed `generate` and `analyze` stages are not
rerun during checkpoint resume.

Every successful workflow writes:

```text
<output_root>/<run_id>/manifest/workflow_manifest.json
<output_root>/<run_id>/manifest/workflow_traceability.json
<output_root>/<run_id>/manifest/workflow_traceability.csv
```

The manifest records config, seed policy, execution mode/workers,
materialization, constraints, consumed/reused/produced artifacts, warnings, and
final stopping reason when evolution ran. Traceability rows connect candidate
IDs, structural and lineage hashes, AnalysisResult IDs, available metric
values, selection roles, and stopping facts.

## Scientific Overrides And Live UI

`run` and `validate` accept `--n-qubits`, `--hamiltonian` (`local_x`, `tfim`
or `ising`, `heisenberg`), repeatable `--hamiltonian-param NAME=VALUE`,
`--trials` and `--protocol paper|fast`, which rewrite the workflow mapping
before validation. `verfeinert serve` starts the interactive evolution page
described in `live_ui.md`.

## Official Examples

- `cx01_reproduction.md`: CX-01 individual reproduction workflow with a fast
  smoke profile, documented full scientific settings, and a declarative
  full-lite CLI config.
- `mixt5g_reproduction.md`: MIXT-5G evolutionary reproduction with a bounded
  smoke profile, documented full schedule, and a declarative full-lite CLI
  config.
- `examples/paper_protocol/`: manuscript-protocol evaluation of the full
  Sanz19 family for any qubit count and Hamiltonian.
- `live_ui.md`: the `verfeinert serve` web UI (live evolution + VQE).

Both examples write artifacts only under caller-provided output roots. The
full-lite configs are CI-friendly and compute selected metrics with tiny
materialized budgets from config/CLI only. Thesis-scale full scientific
profiles are explicit opt-in workflows because expressibility/trainability
execution can be expensive and may construct many QNodes.

## Define A Third Campaign

For a new campaign, start from the canonical `workflow` section instead of
copying CX-01 or MIXT-5G internals:

1. choose `campaign_type`;
2. declare `scientific_execution`;
3. declare independent `postprocessing`;
4. provide generated candidates, persisted artifacts, or `family: provided`;
5. provide declarative mutation policies when evolution is needed;
6. keep campaign-specific data preparation outside the framework core.

Display aliases are presentation metadata only. Canonical candidate IDs,
`candidate_ref`, lineage, generation, and comparison compatibility remain
scientific data.

## Reports

Add `report` to workflow postprocessing to write deterministic run summaries:

```yaml
workflow:
  postprocessing: [ranking, pareto, report]
```

Reports are written under `<output_root>/<run_id>/reports/` as
`workflow_report.json` and `workflow_report.md`. They summarize factual run
state, metric availability, ranking/Pareto artifact summaries, EvolutionRun
stopping facts, warnings, and artifact locations. They do not compute metrics
or add scientific interpretation beyond the configured artifacts.

## Visualization

Visualization uses the campaign-neutral publication-grade public `DEFAULT_STYLE`
and remains optional via
the `visualization` extra. Plot data adapters can be used independently from
figure export. Plotting calls fail with a clear optional-dependency error when
Matplotlib is unavailable.
Objective-space publication plots default to generic `T(H)` trainability and
expressibility labels, and publication legends use opaque frames above data.

Workflow visualization defaults to the generic artifact-derived profile. To
write publication-renderer figures from workflow artifacts, request
`postprocessing: [visualization]` and configure:

```yaml
workflow:
  visualization:
    profile: publication
    figure_set: individual  # or evolution / auto
    formats: [png, pdf, svg]
```

The publication profile consumes already-computed AnalysisResult and
EvolutionRun artifacts. It does not compute metrics, Pareto membership,
selection, or evolution state.

Broad arbitrary external CSV import is deferred. CSV export for canonical and
derived Verfeinert artifacts is part of the standard workflow surface.
