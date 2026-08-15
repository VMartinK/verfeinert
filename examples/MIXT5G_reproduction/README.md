# MIXT-5G Reproduction

This example preserves the mixed five-generation strict-Pareto campaign
configuration while running a small default smoke profile through the
Verfeinert workflow runner and evolver state model.

The smoke workflow uses one canonical `campaign_type=evolutionary` workflow run
with a public insert-gate candidate factory. It keeps lineage, references,
resume-compatible EvolutionRun JSON, and ranking outputs intact without
executing expensive expressibility or trainability workloads.

The `full` profile is an explicit opt-in reproduction coordinator. It builds the
30 configured generation-0 Sanz19 parents, then runs three independent public
`WorkflowRunner` trajectories for structural-cost thresholds `1.0`, `0.2`, and
`0.1`. Each trajectory uses the configured CRX -> CRZ -> CZ -> CRX -> CRZ
schedule, fixed edge `[0, 1]`, all single-layer insertion positions,
repeat-mutated-single-layer propagation, strict Pareto feedback over
`expressibility` and `trainability`, and structural cost only as a threshold
filter.
