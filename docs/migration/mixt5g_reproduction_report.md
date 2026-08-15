# MIXT-5G Reproduction Report

## Created Files

- `examples/MIXT5G_reproduction/README.md`
- `examples/MIXT5G_reproduction/config/mixt5g_reproduction.yaml`
- `examples/MIXT5G_reproduction/scripts/run_mixt5g_reproduction.py`
- `examples/MIXT5G_reproduction/notebooks/mixt5g_reproduction_workflow.ipynb`
- `examples/MIXT5G_reproduction/comparison/reference_summary.json`
- `examples/MIXT5G_reproduction/outputs/.gitkeep`
- `docs/user/mixt5g_reproduction.md`
- `tests/test_mixt5g_reproduction.py`

## APIs Used

- `verfeinert.ansatz_generator.build_sanz19_candidate_records`
- `verfeinert.workflow.WorkflowConfig`
- `verfeinert.workflow.WorkflowRunner`
- `verfeinert.ansatz_evolver.CandidateRef`
- `verfeinert.ansatz_evolver.GenerationRecord`
- `verfeinert.ansatz_evolver.EvolutionRunState`
- `verfeinert.ansatz_evolver.write_evolution_run_json`
- `verfeinert.core.read_yaml`
- `verfeinert.core.write_json`

## Scientific Meaning Preserved

The YAML records:

- generation-0 Sanz19 reference pool;
- five-generation mutation schedule `crx`, `crz`, `cz`, `crx`, `crz`;
- strict-Pareto feedback semantics;
- independent thresholds `[1.0, 0.2, 0.1]`;
- no fallback policy;
- lineage-preserving child IDs.

## Validation

The integration test runs the smoke profile, validates generated Candidate and AnalysisResult JSON documents, validates the combined EvolutionRun JSON, checks parent/child lineage references, and scans example files for local/thesis/legacy coupling.

## v0.2.1 Hotfix

- The full profile now coordinates three independent public `WorkflowRunner`
  trajectories for thresholds `1.0`, `0.2`, and `0.1`.
- Full-profile selection uses `strict_pareto_feedback` with objectives
  `expressibility` and `trainability`; `structural_cost` is only a threshold
  filter.
- Mutation expansion is generic: `apply_to: all_valid_positions`, fixed edge
  `[0, 1]`, and `propagation_policy: repeat_mutated_single_layer`.
- The closed historical accounting anchors are recorded in
  `examples/MIXT5G_reproduction/comparison/reference_summary.json` without
  making old artifacts runtime dependencies.
