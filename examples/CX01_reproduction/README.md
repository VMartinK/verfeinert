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

The `full` profile uses the historical topology-aware L1 mutation expansion:
A01 is disconnected, A05/A06 are all-to-all, A10/A13/A14/A15/A18/A19 are
rings, and the remaining templates use linear/brickwork edges. The example
mutates the L1 structural block once and repeats that mutated block for layers
1, 2, and 3.
