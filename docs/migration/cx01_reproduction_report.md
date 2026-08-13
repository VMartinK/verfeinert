# CX-01 Reproduction Report

## Created Files

- `examples/CX01_reproduction/README.md`
- `examples/CX01_reproduction/config/cx01_reproduction.yaml`
- `examples/CX01_reproduction/scripts/run_cx01_reproduction.py`
- `examples/CX01_reproduction/notebooks/cx01_reproduction_workflow.ipynb`
- `examples/CX01_reproduction/comparison/reference_summary.json`
- `examples/CX01_reproduction/outputs/.gitkeep`
- `docs/user/cx01_reproduction.md`
- `tests/test_cx01_reproduction.py`

## APIs Used

- `verfeinert.ansatz_generator.build_sanz19_candidate_records`
- `verfeinert.workflow.WorkflowConfig`
- `verfeinert.workflow.WorkflowRunner`
- `verfeinert.core.read_yaml`
- `verfeinert.core.write_json`

The example relies on public generator, workflow, analyzer, and evolver APIs through the runner.

## Scientific Meaning Preserved

The YAML records:

- Sanz19 source family;
- four-qubit candidates;
- layers `1`, `2`, and `3`;
- CX knock-in intent;
- all-template and all-valid-edge full profile;
- structural cost;
- expressibility/trainability settings as opt-in reference settings;
- Pareto objectives and thresholds `[1.0, 0.2, 0.1]`.

## Validation

The integration test verifies config loading, smoke candidate generation, Candidate schema validation, AnalysisResult schema validation, EvolutionRun schema validation, lineage mutation fields, and absence of local/thesis/legacy path coupling in the example files.

## Deferred Work

- Full expressibility/trainability reproduction is not automated in smoke tests.
- Historical numeric comparisons need a future opt-in metric runtime and reference-result fixtures.
