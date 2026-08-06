# Analyzer Ranking

## Role

Ranking is a derived analytical transform over `AnalysisResultCollection`. It
does not mutate canonical `AnalysisResult` JSON and it does not introduce a new
required exchange schema. Ranking outputs are reproducible derived structures
and optional CSV/JSON artifacts for inspection.

## Score Model

The default combined score preserves the proven product convention:

```text
combined_score = expressibility * trainability
```

The scoring components and weights are explicit `RankingConfig` data. The
default combination is weighted product; weighted sum is available when a
linear score is desired. Different weights are recorded in every ranking
payload and exported row.

## Cost Policy

Cost can filter ranking inputs through an explicit threshold. Cost is not
included as a score component unless the caller explicitly adds a `cost.*`
component. This keeps cost-aware selection traceable and avoids hidden campaign
rules.

## Derived Exports

Ranking JSON and CSV writers produce derived artifacts under caller-provided
output roots guarded by `verfeinert.core`. Exports record:

- source AnalysisResult IDs;
- transform name and version;
- score configuration;
- per-row component values and weights;
- artifact hash metadata.

Tables are derived views only. They are not canonical module exchange formats.

## Dependency Boundary

Ranking and exports are stdlib-only aside from `verfeinert.core` and analyzer
models. They do not import visualization, notebooks, pandas, NumPy, PennyLane,
generator internals, or evolver internals.
