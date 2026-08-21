# MIXT-5G Reproduction

This example preserves the mixed five-generation strict-Pareto campaign
configuration while running a small default smoke profile through the
Verfeinert workflow runner and evolver state model.

The smoke workflow uses one canonical `campaign_type=evolutionary` workflow run
with a public insert-gate candidate factory. It keeps lineage, references,
resume-compatible EvolutionRun JSON, and ranking outputs intact without
executing expensive expressibility or trainability workloads.

## Declarative Full-Lite CLI

`config/mixt5g_full_lite_workflow.yaml` is a no-wrapper, no-notebook workflow
config. It uses public Sanz19 generation, a declarative generic mutation policy,
the workflow-owned canonical generator mutation factory, analyzer-owned
PennyLane materialization with tiny expressibility/trainability budgets,
multi-generation evolution, ranking, Pareto, CSV exports, publication figures,
checkpointing, manifest/traceability, and a deterministic report.

```bash
verfeinert run examples/MIXT5G_reproduction/config/mixt5g_full_lite_workflow.yaml --output-root outputs/mixt5g-full-lite
```

The historical strict-Pareto-feedback threshold trajectories remain preserved
in the `full` reference profile below. The full-lite CLI workflow uses
deterministic fitness selection so CI and external-install validation exercise a
small multi-generation path reliably.

The `full` profile is an explicit opt-in reproduction coordinator. It builds the
30 configured generation-0 Sanz19 parents, then runs three independent public
`WorkflowRunner` trajectories for structural-cost thresholds `1.0`, `0.2`, and
`0.1`. Each trajectory uses the configured CRX -> CRZ -> CZ -> CRX -> CRZ
schedule, fixed edge `[0, 1]`, all single-layer insertion positions,
repeat-mutated-single-layer propagation, strict Pareto feedback over
`expressibility` and `trainability`, and structural cost only as a threshold
filter.
