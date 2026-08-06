# MIXT-5G Reproduction Example

The MIXT-5G reproduction example lives in `examples/MIXT5G_reproduction/`. It preserves the reference strict-Pareto evolution plan while using Verfeinert public APIs and keeping campaign-specific candidate factories in the example.

## Files

- `config/mixt5g_reproduction.yaml`
- `scripts/run_mixt5g_reproduction.py`
- `notebooks/mixt5g_reproduction_workflow.ipynb`
- `comparison/reference_summary.json`
- `outputs/.gitkeep`

## Workflow

The example runs a bounded multi-generation reproduction loop:

```text
generation-0 Sanz19 parents
  -> workflow runner per generation
  -> analyzer structural-cost results
  -> strict-Pareto selection
  -> scheduled example-local child records
  -> combined EvolutionRun JSON
```

Each generation uses public `WorkflowRunner` orchestration. The final combined EvolutionRun JSON records all generation snapshots, parent references, analysis-result references, survivor references, and campaign reference metadata.

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
- strict-Pareto semantics;
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

- generation-local candidate, staged package, analysis, evolution, and ranking artifacts;
- a combined `EvolutionRun` JSON document;
- comparison report.
