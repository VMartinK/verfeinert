# User Documentation

These guides show reproducible researcher workflows built on public
`verfeinert` APIs.

## Official Examples

- `cx01_reproduction.md`: CX-01 reproduction workflow with a fast smoke profile
  and documented full scientific settings.
- `mixt5g_reproduction.md`: MIXT-5G strict-Pareto evolution reproduction with a
  bounded smoke profile and documented full schedule.

Both examples write artifacts only under caller-provided output roots. Expensive
scientific metrics remain explicit opt-in workflows.

For a minimal new campaign, start from the canonical `workflow` section used by
the examples: choose `campaign_type`, declare `scientific_execution`, add
optional `postprocessing`, and provide either generated candidates, persisted
artifacts, or a public candidate factory such as `InsertGateMutationFactory`.

## Postprocessing Existing Artifacts

Phase 10 workflows are artifact transformations. Existing compatible
`AnalysisResult` JSON can feed Pareto, ranking, comparison/global analysis, CSV
export, and optional visualization without rerunning generation, analyzer
metrics, QNodes, or evolution.

Comparison requires explicit source selection:

```yaml
workflow:
  campaign_type: individual
  scientific_execution: []
  postprocessing: [comparison, csv]

comparisons:
  - comparison_id: selected-runs
    sources:
      - source_id: run-a
        analysis_results: [artifacts/run-a/analysis]
      - source_id: run-b
        analysis_results: [artifacts/run-b/analysis]
    objectives:
      - {metric_name: trainability, direction: maximize}
      - {metric_name: expressibility, direction: maximize}
```

Compatibility is provenance-based. Hamiltonian definitions, metric
configurations, structural-cost normalization, objectives, directions,
thresholds, and ranking score definitions are checked where relevant; output
paths and display labels are ignored. CSV export covers canonical and derived
Verfeinert artifacts. Broad arbitrary external CSV import is deferred.

Visualization uses the neutral public `DEFAULT_STYLE` and remains optional via
the `visualization` extra. Display aliases, when supplied, are presentation-only
and fall back to canonical candidate IDs.
