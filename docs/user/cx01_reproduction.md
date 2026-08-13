# CX-01 Reproduction Example

The CX-01 reproduction example lives in `examples/CX01_reproduction/`. It is a researcher-facing workflow that preserves the reference meaning of the v1 CX-01 campaign while using only Verfeinert public APIs.

## Files

- `config/cx01_reproduction.yaml`
- `scripts/run_cx01_reproduction.py`
- `notebooks/cx01_reproduction_workflow.ipynb`
- `comparison/reference_summary.json`
- `outputs/.gitkeep`

## Workflow

The script and notebook run:

```text
canonical YAML workflow config
  -> campaign_type: individual
  -> example-local CX knock-in candidate record preparation
  -> public workflow runner
  -> canonical Candidate JSON
  -> canonical StagedPackage JSON
  -> structural-cost AnalysisResult JSON
  -> ranking and comparison artifacts
```

The candidate preparation is intentionally example-local. It encodes CX-01
reproduction inputs without adding campaign-specific branches to `verfeinert`.
The migrated example does not request `evolve` and does not produce an
EvolutionRun.

## Profiles

`smoke` is the default test profile:

- templates `A02` and `A09`;
- layer `1`;
- two valid CX edges;
- four generated candidates;
- structural-cost-only analysis.

`materialized_smoke` is a tiny bridge profile:

- one generated candidate;
- analyzer-owned PennyLane materialization enabled;
- expressibility/trainability permissions enabled;
- very small metric sample counts for development validation.

`full` preserves the reference configuration:

- all Sanz19 templates;
- layers `1`, `2`, and `3`;
- all valid CX edges;
- structural cost plus documented expressibility/trainability and Pareto settings.

Expensive metrics are not run by default. They remain explicit opt-in once a canonical metric runtime configuration is selected.

## Command

From the repository root:

```bash
python3 examples/CX01_reproduction/scripts/run_cx01_reproduction.py --profile smoke
```

Use `--output-root` to direct all artifacts to a caller-owned run directory.

## Outputs

All artifacts are written below the configured output root:

- candidate JSON files;
- `staged_package.json`;
- analyzer result JSON files;
- ranking JSON/CSV;
- comparison report.
