# MIXT-5G Reproduction Example

The MIXT-5G reproduction example lives in `examples/MIXT5G_reproduction/`. It preserves the reference strict-Pareto evolution plan while using Verfeinert public APIs and keeping campaign-specific candidate factories in the example.

## Files

- `config/mixt5g_reproduction.yaml`
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

- candidate, staged package, analysis, evolution, and ranking artifacts from
  one generic workflow run;
- a resume-compatible `EvolutionRun` JSON document;
- comparison report.
