# Verfeinert

Verfeinert is an open-source scientific framework for quantum ansatz generation,
analysis, evolution, and reproducible workflow orchestration.

## Authors
Developed by Víctor Martín Kruglova

## Citation
If you use Verfeinert in academic work, please cite the software according to the citation metadata provided in `CITATION.cff`.
[View citation information](CITATION.cff)

The citation file is also available through GitHub's "Cite this repository" functionality.

## Namespace

```text
verfeinert
  core
  ansatz_generator
  ansatz_analyzer
  ansatz_evolver
  workflow
```

## Current Capabilities

- canonical JSON schemas for candidates, staged packages, analysis results,
  experiments, and evolution runs;
- packaged schema resources available after installation;
- standardized ansatz generation and canonical Candidate/StagedPackage export;
- analyzer structural cost, Pareto/ranking foundations, and v1-aligned
  expressibility/trainability metric implementations;
- artifact-first postprocessing: Pareto, ranking, explicit comparison/global
  analysis, deterministic JSON/CSV exports, and optional visualization;
- reference-based evolver population, mutation, selection, and EvolutionRun
  export foundations;
- workflow runner and researcher-facing CX-01 and MIXT-5G reproducibility
  examples.

## Installation

From a GitHub release wheel once downloaded:

```bash
python -m pip install ./verfeinert-0.4.0-py3-none-any.whl
```

From a repository checkout:

```bash
python -m pip install .
```

Visualization is optional:

```bash
python -m pip install ".[visualization]"
```

For development and test work from this directory:


```bash
python -m pip install -e ".[dev]"
```

The scientific analyzer runtime uses NumPy and PennyLane as declared runtime
dependencies. Matplotlib is required only for plotting and figure export:

```bash
python -m pip install -e ".[dev,visualization]"
```

Scientific analyzer and workflow analysis stages support sequential execution
by default and explicit candidate-level multiprocessing through:

```yaml
execution:
  mode: multiprocessing
  parallelize_candidates: true
  worker_count: 2
```

Multiprocessing is fail-closed. If workers cannot honor the requested
configuration because of pickling, startup failure, worker exceptions, or an
order-dependent metric RNG policy, the run fails rather than silently falling
back to sequential execution.

## Validate

```bash
PYTHONDONTWRITEBYTECODE=1 MPLCONFIGDIR=/tmp/matplotlib-verfeinert python -m unittest discover -s tests -q
python -m pytest tests -q
```

`pytest` is part of the dev extra and is required in CI. If it is not installed
in a local environment, the stdlib `unittest` suite is the minimum supported
check.

## Examples

```bash
verfeinert run examples/CX01_reproduction/config/cx01_full_lite_workflow.yaml \
  --output-root outputs/cx01-full-lite

verfeinert run examples/MIXT5G_reproduction/config/mixt5g_full_lite_workflow.yaml \
  --output-root outputs/mixt5g-full-lite
```

Generated artifacts must be written under caller-provided output roots and
should not be committed.

CX-01 is an `individual` workflow: it generates and analyzes configured
candidates, then runs ranking/Pareto/export/report/visualization
postprocessing without evolution. MIXT-5G is an `evolutionary` workflow: it
initializes a population, applies a declarative generic mutation schedule,
analyzes each generation, selects survivors, and writes a resume-compatible
EvolutionRun.

The historical script/notebook endpoints remain researcher conveniences for
the reference profiles, but the full-lite release validation path is config and
CLI only.

## Analyzer Scientific Execution

Expressibility and trainability can be computed from canonical Candidate or
StagedPackage JSON when analyzer materialization is explicitly enabled and both
expensive-metric and QNode permissions are granted:

```python
from verfeinert.ansatz_analyzer import (
    AnalyzerConfig,
    AnalyzerExecutionPermissions,
    CircuitMaterializationConfig,
)

config = AnalyzerConfig.from_mapping({
    "run_id": "scientific-analysis",
    "input_roots": ["inputs"],
    "output_root": "outputs",
    "selected_metrics": ["expressibility", "trainability"],
    "permissions": {
        "allow_expensive_metrics": True,
        "allow_qnode_execution": True,
    },
    "materialization": {
        "enabled": True,
        "backend": "pennylane",
        "device": "default.qubit",
        "interface": "autograd",
        "diff_method": "best",
    },
    "metric_configs": {
        "expressibility": {"n_pairs": 100, "n_bins": 20},
        "trainability": {"n_repeats": 100},
    },
})
```

Automatic materialization is disabled by default. Explicit user-provided state
callables still take precedence over automatic materialization.

## Artifact-Oriented Workflows

Workflow configuration distinguishes scientific execution from downstream
postprocessing. A workflow may request only the operations it needs, for
example `generate -> analyze`, `Candidate JSON -> analyze`, or
`AnalysisResult -> ranking`, without recomputing unrelated upstream artifacts.

Minimal individual workflow configuration:

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

Run it through the thin CLI:

```bash
verfeinert validate workflow.yaml
verfeinert run workflow.yaml
```

Resume from a workflow checkpoint or run directory:

```bash
verfeinert resume outputs/minimal-individual/minimal-individual
verfeinert inspect outputs/minimal-individual/minimal-individual/reports/workflow_report.json
```

The same workflow can be run through Python:

```python
from verfeinert.workflow import WorkflowConfig, WorkflowRunner

config = WorkflowConfig.from_mapping({
    "run": {"run_id": "rank-existing-results"},
    "paths": {"output_root": "outputs"},
    "workflow": {
        "campaign_type": "individual",
        "scientific_execution": [],
        "postprocessing": ["ranking"],
    },
    "artifacts": {
        "analysis_results": ["analysis/analysis-result.json"],
    },
})

result = WorkflowRunner(config).run()
```

Postprocessing is independently selectable:

- `Candidate` or `StagedPackage` artifacts can feed `analyze`.
- `AnalysisResult` artifacts can feed ranking, Pareto, comparison, CSV export,
  and optional visualization.
- `EvolutionRun` artifacts can be resumed or branched by compatible workflow
  configs.
- `ComparisonResult` artifacts can feed CSV export or visualization without
  recomputing comparison.

Comparison/global analysis uses only explicitly selected compatible
AnalysisResult sources:

```python
config = WorkflowConfig.from_mapping({
    "run": {"run_id": "compare-existing-results"},
    "paths": {"output_root": "outputs"},
    "workflow": {
        "campaign_type": "individual",
        "scientific_execution": [],
        "postprocessing": ["comparison", "csv"],
    },
    "comparisons": [{
        "comparison_id": "selected-runs",
        "sources": [
            {"source_id": "run-a", "analysis_results": ["run-a/analysis"]},
            {"source_id": "run-b", "analysis_results": ["run-b/analysis"]},
        ],
        "objectives": [
            {"metric_name": "trainability", "direction": "maximize"},
            {"metric_name": "expressibility", "direction": "maximize"},
        ],
        "cost_thresholds": [1.0],
    }],
})
```

Comparison compatibility is based on structured metric and cost provenance, not
campaign names. Pareto membership, scalar score, and cost eligibility remain
separate fields in the resulting `ComparisonResult`.

Visualization is optional and consumes persisted or derived artifacts. It uses
campaign-neutral publication-grade `DEFAULT_STYLE`; display aliases are explicit
presentation metadata and
never change canonical candidate IDs. Objective-space publication plots default
to generic `T(H)` trainability and expressibility labels with opaque legends
above plotted data.

Legacy `stages` declarations are normalized into the same internal plan. If
both legacy and structured workflow declarations are supplied, conflicting
requests fail during configuration validation.

Evolutionary workflows can define mutation policies declaratively:

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

To define a third campaign, compose the same public pieces: canonical workflow
configuration, Sanz19 or provided candidate records, declarative mutation
policy, analyzer materialization/permissions, ranking/Pareto/report/export
postprocessing, and `WorkflowRunner` or the CLI. Do not copy CX-01 or MIXT-5G
internals unless you are reproducing those specific studies.

Every successful workflow writes deterministic manifest and traceability
artifacts under `<output_root>/<run_id>/manifest/`. Add `report` to
`workflow.postprocessing` to write machine-readable and Markdown run reports
under `<output_root>/<run_id>/reports/`. Add
`workflow.checkpoint.enabled: true` to write
`<output_root>/<run_id>/checkpoints/latest.json` for strict resume.

## External Validation

```bash
python scripts/validate_external_install.py \
  --output-root outputs/external-validation
```

This creates a temporary virtual environment, installs the package, checks
public imports and packaged schemas, runs both declarative full-lite workflows
through the installed console script, and verifies that imports resolve from
site-packages rather than the repository checkout.

## Limits

- Global F/F2 visualization remains out of contract.
- Arbitrary external CSV ingestion is not a canonical workflow entry point.
- Materialization currently supports the documented PennyLane/default.qubit
  capability boundary; unsupported gates or parameter modes fail closed.
- Workflow visualization consumes computed artifacts and never recomputes
  metrics, ranking, Pareto membership, or evolution state.

## License

Verfeinert is licensed under the Apache License, Version 2.0. See
[`LICENSE`](LICENSE).
