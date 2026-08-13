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

## Install For Development

From this directory:

```bash
python -m pip install -e ".[dev]"
```

The scientific metric reference implementation requires NumPy and PennyLane as
runtime dependencies. Visualization support is optional:

```bash
python -m pip install -e ".[dev,visualization]"
```

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
python examples/CX01_reproduction/scripts/run_cx01_reproduction.py \
  --profile smoke \
  --output-root /tmp/verfeinert-cx01

python examples/MIXT5G_reproduction/scripts/run_mixt5g_reproduction.py \
  --profile smoke \
  --output-root /tmp/verfeinert-mixt5g
```

Generated artifacts must be written under caller-provided output roots and
should not be committed.

CX-01 is an `individual` campaign: it generates and analyzes configured
candidates, then runs ranking postprocessing without evolution. MIXT-5G is an
`evolutionary` campaign: it initializes a population, uses a generic insert-gate
candidate factory and configured mutation schedule, and writes a
resume-compatible EvolutionRun.

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

Postprocessing is independently selectable. For example, comparison/global
analysis uses only explicitly selected compatible AnalysisResult sources:

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
neutral `DEFAULT_STYLE`; display aliases are explicit presentation metadata and
never change canonical candidate IDs.

Legacy `stages` declarations are normalized into the same internal plan. If
both legacy and structured workflow declarations are supplied, conflicting
requests fail during configuration validation.

Evolutionary campaigns can use the public factory boundary:

```python
from verfeinert.ansatz_generator import InsertGateMutationFactory
from verfeinert.workflow import WorkflowConfig, WorkflowRunner

result = WorkflowRunner(WorkflowConfig.from_mapping(config)).run(
    candidate_records=initial_records,
    candidate_factory=InsertGateMutationFactory(),
)
```

The optional CLI is a thin wrapper around the same API:

```bash
verfeinert run workflow.yaml --output-root /tmp/verfeinert-run
```

## External Validation

```bash
python scripts/validate_external_install.py \
  --output-root /tmp/verfeinert-external-validation
```

This creates a temporary virtual environment, installs the package, checks
public imports and packaged schemas, and runs both smoke reproduction examples.

## License

Verfeinert is licensed under the Apache License, Version 2.0. See
[`LICENSE`](LICENSE).
