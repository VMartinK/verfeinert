# MIXT-5G Reproduction Example

The MIXT-5G reproduction example lives in `examples/MIXT5G_reproduction/`. It preserves the reference strict-Pareto evolution plan while using Verfeinert public APIs. The full-lite CLI config runs without campaign-specific Python.

## Files

- `config/mixt5g_reproduction.yaml`
- `config/mixt5g_full_lite_workflow.yaml`
- `scripts/run_mixt5g_reproduction.py`
- `notebooks/mixt5g_reproduction_workflow.ipynb`
- `comparison/reference_summary.json`
- `outputs/.gitkeep`

## Workflow

The example runs a bounded generic evolutionary workflow:

```text
canonical YAML workflow config
  -> campaign_type: evolutionary
  -> generation-0 Sanz19 parents
  -> public WorkflowRunner
  -> public insert-gate CandidateFactory
  -> analyzer structural-cost results per generation
  -> strict-Pareto selection
  -> resume-compatible EvolutionRun JSON
```

The example wrapper compiles compact profile/schedule data into a generic
`evolver.mutation_policy`; it does not run a separate campaign engine. The
EvolutionRun JSON records all generation snapshots, parent references,
analysis-result references, survivor references, and workflow provenance.

## Declarative CLI Workflow

For installed-package validation or no-Python reproduction, run:

```bash
verfeinert run examples/MIXT5G_reproduction/config/mixt5g_full_lite_workflow.yaml --output-root outputs/mixt5g-full-lite
```

The full-lite config computes structural cost, expressibility, and trainability
through analyzer-owned materialization with tiny budgets, then writes a
multi-generation EvolutionRun, ranking, Pareto, CSV, publication figures,
checkpoint, manifest/traceability, and report artifacts.

## Profiles

`smoke` is the default local profile:

- initial templates `A04` and `A07`;
- layer `1`;
- two mutation generations;
- one parent per generation;
- one edge;
- structural-cost-only analysis.

`full` preserves the scientific plan:

- reference Sanz19 pool;
- five generations;
- mutation gate schedule `crx`, `crz`, `cz`, `crx`, `crz`;
- independent thresholds `[1.0, 0.2, 0.1]`;
- three independent `WorkflowRunner` trajectories, one per threshold;
- strict Pareto feedback over `expressibility` and `trainability`;
- structural cost used only as the threshold filter;
- fixed mutation edge `[0, 1]`;
- all valid single-layer insertion positions;
- repeat-mutated-single-layer propagation;
- no fallback policy.

Expensive expressibility/trainability reproduction is documented but not run by default.

## Command

From the repository root:

```bash
python3 examples/MIXT5G_reproduction/scripts/run_mixt5g_reproduction.py --profile smoke
```

Use `--output-root` to direct all artifacts to a caller-owned run directory.

## Outputs

All artifacts are written below the configured output root:

- candidate, staged package, analysis, evolution, and ranking artifacts from
  one generic workflow run;
- a resume-compatible `EvolutionRun` JSON document;
- Pareto JSON/CSV when configured;
- workflow checkpoint when enabled;
- workflow manifest and traceability JSON/CSV;
- deterministic workflow report JSON/Markdown;
- publication figures when visualization is requested;
- comparison report from the example script profiles.
