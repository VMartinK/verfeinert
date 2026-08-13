# User Documentation

These guides describe reproducible researcher workflows built on public
`verfeinert` APIs. They are current user-facing documentation, while
`docs/migration/` remains historical implementation context.

## Installation

From a GitHub release wheel once downloaded:

```bash
python -m pip install ./verfeinert-0.2.0-py3-none-any.whl
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
verfeinert run workflow.yaml
```

or with Python:

```python
from verfeinert.workflow import WorkflowConfig, WorkflowRunner

result = WorkflowRunner(WorkflowConfig.from_mapping(config)).run()
```

## Evolutionary Campaign

An evolutionary campaign keeps the same public workflow API and adds `evolve`
plus a public candidate factory or provided candidate records:

```python
from verfeinert.ansatz_generator import InsertGateMutationFactory
from verfeinert.workflow import WorkflowConfig, WorkflowRunner

result = WorkflowRunner(WorkflowConfig.from_mapping(config)).run(
    candidate_records=initial_records,
    candidate_factory=InsertGateMutationFactory(),
)
```

The workflow owns orchestration only. The generator owns candidate construction,
the analyzer owns metric execution/materialization, and the evolver owns
selection, mutation requests, generation state, resume, and branch semantics.

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

## Official Examples

- `cx01_reproduction.md`: CX-01 individual reproduction workflow with a fast
  smoke profile and documented full scientific settings.
- `mixt5g_reproduction.md`: MIXT-5G evolutionary reproduction with a bounded
  smoke profile and documented full schedule.

Both examples write artifacts only under caller-provided output roots. Smoke
profiles are CI-friendly and structural-cost oriented. Full scientific profiles
are explicit opt-in workflows because expressibility/trainability execution can
be expensive and may construct QNodes.

## Define A Third Campaign

For a new campaign, start from the canonical `workflow` section instead of
copying CX-01 or MIXT-5G internals:

1. choose `campaign_type`;
2. declare `scientific_execution`;
3. declare independent `postprocessing`;
4. provide generated candidates, persisted artifacts, or `family: provided`;
5. provide public mutation policies/factories when evolution is needed;
6. keep campaign-specific data preparation outside the framework core.

Display aliases are presentation metadata only. Canonical candidate IDs,
`candidate_ref`, lineage, generation, and comparison compatibility remain
scientific data.

## Visualization

Visualization uses the neutral public `DEFAULT_STYLE` and remains optional via
the `visualization` extra. Plot data adapters can be used independently from
figure export. Plotting calls fail with a clear optional-dependency error when
Matplotlib is unavailable.

Broad arbitrary external CSV import is deferred. CSV export for canonical and
derived Verfeinert artifacts is part of the standard workflow surface.
