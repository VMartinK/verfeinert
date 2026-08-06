# Analyzer Collections

## Role

`AnalysisResultCollection` is the analyzer's internal ordered view over
canonical `verfeinert.analysis_result.v1` documents. It does not introduce a
new exchange schema. The canonical boundary remains one `AnalysisResult` JSON
document per candidate, while collections provide reusable in-memory behavior
for classification, Pareto analysis, ranking, derived tables, and plots.

## Collection Rules

- Every document is validated against `analysis_result.schema.json` on load.
- Collection order is deterministic and follows the caller-provided order or
  sorted JSON filenames when a directory is loaded.
- Result identifiers and candidate identifiers are unique inside a collection.
- Empty filtered collections are valid internal values.
- Homogeneity means a single canonical AnalysisResult schema version, not a
  shared campaign name or notebook workflow.

## Classification Boundary

Classification primitives operate on result documents and return canonical
`ClassificationRecord` payloads. Threshold, cost eligibility, and invalid or
rejected states are generic policies. Pareto-specific classifications are
implemented separately and visualization consumes classifications only after
they are computed.

## Cost Normalization

Structural-cost normalization remains record-based and configurable through
`StructuralCostConfig`. Component weights, reference bounds, depth proxy use,
reference status, and warnings are stored in cost metadata so downstream
classification and ranking can be reproduced without reading notebooks or
campaign-specific tables.

## Dependency Boundary

Collections and threshold classifications use only stdlib analyzer code,
canonical schemas, and `verfeinert.core` helpers. They do not import notebooks,
Matplotlib, PennyLane, NumPy, pandas, generator internals, or evolver internals.
