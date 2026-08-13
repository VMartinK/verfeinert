# CX-01 Reproduction

This example preserves the CX-01 scientific configuration while running a fast
default smoke profile through the Verfeinert JSON-first workflow.

The workflow is:

```text
canonical workflow config, campaign_type=individual
  -> CX knock-in candidate records
  -> canonical Candidate/StagedPackage JSON
  -> analyzer structural-cost smoke analysis
  -> ranking and comparison artifacts
```

The migrated reproduction does not request `evolve` and does not produce an
EvolutionRun. The `materialized_smoke` profile demonstrates the analyzer-owned
PennyLane materialization bridge with tiny expressibility/trainability settings.
Full expressibility/trainability reproduction remains opt-in because the
reference scientific settings are expensive.
