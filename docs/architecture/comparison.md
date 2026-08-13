# Comparison And Global Analysis

## Role

`verfeinert.ansatz_analyzer.comparison` compares explicitly selected
`AnalysisResultCollection` sources. It is a pure postprocessing transform over
persisted scientific artifacts. It does not generate candidates, execute
QNodes, rerun analyzer metrics, rerun evolution, import notebooks, or create
figures.

## Data Flow

```text
explicit AnalysisResult sources
    -> compatibility validation
    -> global Pareto and optional ranking
    -> ComparisonResult JSON
    -> optional CSV/table/visualization
```

Each comparison has its own `comparison_id`, source list, compatibility report,
rows, and exports. Multiple comparisons can coexist in one workflow without
shared singleton state.

## Compatibility

Compatibility is based on structured metric and cost provenance, not campaign
names. The comparison fingerprint checks the metric definitions required by the
requested objectives/ranking, trainability Hamiltonian provenance when
trainability is compared, expressibility configuration when expressibility is
compared, structural-cost model/reference/bounds/weights/depth semantics, Pareto
objectives and directions, ranking score configuration, and cost thresholds.

It intentionally ignores scientifically irrelevant differences such as output
paths, filenames, visualization settings, CLI invocation, and display labels.
Missing or inconsistent comparison-critical provenance fails clearly instead of
being inferred from names or column values.

## Semantics

Global Pareto is a static nondominance transform over the selected compatible
points using explicit objective directions. Pareto membership, scalar ranking
score, and cost eligibility are separate fields. Cost thresholds filter
eligibility and threshold-specific views; they do not mutate canonical Pareto
identity or imply scalar score.

## Identity

Canonical identity remains `candidate_ref.candidate_id` and
`analysis_result_id`. `ComparisonResult` rows preserve those refs unchanged.
Optional display aliases are presentation-only and fall back to canonical IDs
when not supplied. Root, parent, generation, layer, and run/source metadata are
copied only from structured AnalysisResult metadata.

## Exports

`ComparisonResult` is the JSON-first persisted artifact. CSV exports are flat,
deterministic derived tables with canonical refs, source attribution,
objective values, global Pareto membership, ranking fields, cost eligibility,
and structured lineage/source columns when available. Arbitrary external CSV
ingestion is deliberately outside this contract.
