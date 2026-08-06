# CX-01 Reproduction

This example preserves the CX-01 scientific configuration while running a fast
default smoke profile through the Verfeinert JSON-first workflow.

The workflow is:

```text
CX knock-in candidate records
  -> canonical Candidate/StagedPackage JSON
  -> analyzer structural-cost smoke analysis
  -> evolver selection and EvolutionRun JSON
  -> comparison report
```

Full expressibility/trainability reproduction is intentionally opt-in because
the reference scientific settings are expensive.
