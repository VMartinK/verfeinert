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

## Deferred Work

- Full mixed strict-Pareto reproduction with expressibility and trainability remains opt-in.
- The reusable multi-generation loop should move from the example into evolver once Phase 6 APIs are hardened around analysis-result linkage and generation factories.
