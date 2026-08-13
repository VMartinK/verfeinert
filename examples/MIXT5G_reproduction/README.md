# MIXT-5G Reproduction

This example preserves the mixed five-generation strict-Pareto campaign
configuration while running a small default smoke profile through the
Verfeinert workflow runner and evolver state model.

The smoke workflow uses one canonical `campaign_type=evolutionary` workflow run
with a public insert-gate candidate factory. It keeps lineage, references,
resume-compatible EvolutionRun JSON, and ranking outputs intact without
executing expensive expressibility or trainability workloads.
