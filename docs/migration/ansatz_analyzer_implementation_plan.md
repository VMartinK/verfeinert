# Ansatz Analyzer Implementation Plan

## Objective

Migrate validated analyzer science into the clean future
`verfeinert.ansatz_analyzer` architecture. The migration is not a compatibility
port. It must use canonical JSON as the module boundary and keep tables,
figures, and notebooks as derived endpoints.

## Contract Decisions

Analyzer input:

- one `verfeinert.candidate.v1` Candidate JSON document;
- or a `verfeinert.staged_package.v1` document containing canonical
  candidates;
- optional reference result collections for Pareto comparison, supplied as
  canonical AnalysisResult JSON.

Analyzer output:

- one `verfeinert.analysis_result.v1` document per candidate;
- metric records use `computed`, `skipped`, or `failed`;
- cost records include structural cost, operation count, two-qubit operation
  count, parameter count, and cost-model metadata;
- classification records hold Pareto and threshold labels;
- derived tables must record source AnalysisResult IDs and transform version.

Internal model requirements:

- immutable or copy-safe records for candidate views, metric results, cost
  results, classifications, execution context, and analysis provenance;
- no campaign-name branches;
- no hidden QNode execution;
- deterministic ordering for candidates, metric records, classifications, and
  ranked outputs;
- all path writes through `verfeinert.core` guards.

## Migration Tasks

| Task | Source logic | Destination | Required refactor | Dependencies | Validation criteria |
| --- | --- | --- | --- | --- | --- |
| ANA-001 Candidate ingestion and validation | `staging.py`, canonical schemas, Phase 3.5 projection tests | `verfeinert.ansatz_analyzer.io`, `models`, `validation` | Read Candidate/StagedPackage JSON instead of Beta metadata tables. Build a normalized `CandidateView` from nested `candidate_id`, `circuit`, `identity`, `lineage`, and `provenance`. | `verfeinert.core`, JSON schemas | Valid candidate examples load deterministically; invalid/missing circuit fields fail; no generated callable import occurs. |
| ANA-002 AnalysisResult model | `payload.py`, `schemas.py`, `writer.py`, `analysis_result.schema.json` | `models`, `results`, `validation` | Replace notebook-compatible final payload with schema-conformant one-candidate AnalysisResult records. | ANA-001, `verfeinert.core` | Minimal and full AnalysisResult examples validate against schema; statuses and provenance are truthful. |
| ANA-003 Analyzer configuration and safety | `config.py`, `campaign_runner.py`, Alpha `analysis_io/result_schema.py` | `config` | Replace campaign/notebook fields with experiment input, metric selection, execution flags, random seed, and caller-owned output roots. | `verfeinert.core.config`, ANA-001 | Invalid metric names, unsafe roots, missing roots, and QNode-disabled expensive metrics are rejected. |
| ANA-004 Staged package input reader | `staging.py`, Alpha `analysis_io/loader.py` | `io` | Load canonical staged package manifests and embedded candidates. Generated callable artifacts are references only until an execution config explicitly enables loading. | ANA-001, ANA-003 | Staged packages validate; selected candidate IDs preserve order; source/input/output roots remain separate. |
| ANA-005 Structural cost migration | `metrics/structural_cost.py`, thesis cost reconstruction cells | `metrics/structural_cost.py` | Port formula to record-first candidate operations. Keep equal-weight reference-normalized cost and reference-status metadata. Tables become derived views. | ANA-001, ANA-002 | Pinned structural fixtures match current scientific behavior; operation-count depth proxy warnings are preserved when configured. |
| ANA-006 Metric execution boundary | `campaign_runner.py`, `AnalysisSafetyFlags`, expressibility/trainability configs | `execution` or `metrics/runtime.py` | Centralize explicit permission checks, call counters, workload estimates, RNG seed policy, backend labels, and failure records. | ANA-003 | Expensive metrics cannot run unless enabled; dry structural/classification analyses never execute QNodes. |
| ANA-007 Expressibility migration | `metrics/expressibility.py`, expressibility pilot tests | `metrics/expressibility.py` | Preserve D_KL/Haar sampling math. Return canonical metric records and execution provenance. Put NumPy/backend needs outside `core`; keep QNode calls explicit. | ANA-006 | Tiny deterministic callable produces stable finite metric values and accurate qnode call counts. |
| ANA-008 Trainability migration | `metrics/trainability.py`, trainability contract tests | `metrics/trainability.py` | Preserve Local-X Hamiltonian and active mean squared gradient definition. Return canonical metric records with gradient budget metadata. | ANA-006 | Tiny deterministic callable produces finite score; inactive gradients report zero; budget failures become failed/skipped metric records. |
| ANA-009 Score derivation | `reporting/metric_scores.py`, `analysis_export.ensure_analysis_scores` | `tables.scoring` and ranking helpers | Keep `expressibility_score = -log10(D_KL + eps)`, trainability aliasing, and `combined_score = trainability_score * expressibility_score` as derived transforms. | ANA-002, ANA-007, ANA-008 | Derived table values match metric records; source metric IDs are recorded; no canonical metric is silently overwritten. |
| ANA-010 Pareto classification | `metrics/pareto.py`, `reporting/pareto_reporting.py`, `python/analysis/campaigns/pareto_helpers.py`, thesis `pareto_mask` cells | `classification.pareto` | Make Pareto a classification policy over AnalysisResult collections. Keep cost as external constraint, not objective. Split current/imported/baseline/accumulated comparisons into reference-set inputs. | ANA-002, ANA-005, ANA-009 | Dominance, tie behavior, duplicate policy, threshold filtering, and labels match focused fixtures. |
| ANA-011 Ranking | `reporting/rankings.py`, `analysis_export.build_analysis_rankings`, thesis ranking tables | `ranking.py` | Rank AnalysisResult collections by configured metric/cost/classification-derived score with deterministic candidate ID tie-breaks. | ANA-002, ANA-009, ANA-010 | Stable top-N outputs for expressibility, trainability, combined score, and cost-aware filters. |
| ANA-012 Derived table and export layer | `analysis_export.py`, `writer.py`, `summary.py` | `tables.exports`, `tables.summaries`, `io` | Build CSV/JSON/Markdown/manifest artifacts from canonical AnalysisResult JSON. Keep table schema version and source result IDs. | ANA-002, ANA-009, ANA-010, ANA-011 | Round-trip from AnalysisResult JSON to derived tables is deterministic; tables are reproducible without source notebooks. |
| ANA-013 Visualization extraction | `reporting/design_space.py`, plotting functions in `pareto_reporting.py` and `generation_summary.py`, `Thesis_Data_Processing/*.ipynb` | Deferred `visualization.style`, `visualization.objective_space`, `visualization.evolution` | Define centralized style and data-input contracts only after tables are stable. Do not redesign plots during analyzer migration. | ANA-010, ANA-011, ANA-012 | Static dependency test proves metric modules do not import Matplotlib; future plot tests use derived tables only. |
| ANA-014 Notebook and example endpoints | `Verfeinert/notebooks/*_clean_interface.ipynb`, `plot_example.ipynb`, Alpha analysis notebooks | `Verfeinertv2/notebooks`, `examples` | Rebuild as thin endpoints over public APIs. No package code copied from notebooks. No executed outputs committed. | ANA-001 through ANA-012 | Notebooks import final namespace, use caller-provided roots, and can be statically checked without running experiments. |
| ANA-015 Test and validation migration | `Verfeinert/tests/analyzer/*`, selected integration smokes, legacy Behave references | `Verfeinertv2/tests` | Port behavior into fast unittest/pytest tests with schema fixtures. Keep heavy metric tests explicit and small. | All implementation tasks | Unit tests cover schema contracts, no-QNode boundaries, structural cost, Pareto, ranking, writer/export, and optional tiny metric execution. |

## Metric Migration Order

1. Structural cost, because it is metadata-only and does not require QNodes.
2. AnalysisResult model and writer, so every metric has a canonical target.
3. Score derivation, Pareto classification, and ranking, using hand-authored
   AnalysisResult fixtures.
4. Expressibility with tiny explicit execution fixtures.
5. Trainability with tiny explicit execution fixtures.
6. Derived reporting tables.
7. Visualization and notebooks.

## Cost Model Migration

The first cost model should preserve the current scientific definition:

- components: parameter count, depth, two-qubit operation count;
- default equal weights;
- reference normalization against explicit reference bounds;
- optional operation-count depth proxy with a recorded warning;
- cost thresholds as classification/reporting filters.

The future cost output lives in the AnalysisResult `cost` object. Reference
bounds, component source, weights, and warning state belong in `cost.metadata`.
Campaign-specific thresholds must be configuration data, not code branches.

## Pareto And Classification Separation

Pareto logic should not be a metric routine. It should be a classification
policy over existing metric/cost results. The policy must accept:

- objective names and directions;
- optional cost constraint;
- optional reference result set;
- duplicate/tie policy.

The output is one or more AnalysisResult classification records such as
`pareto_front`, `new_pareto`, `expressibility_gain`, `trainability_gain`,
`dominated_or_tradeoff`, or `rejected_by_cost`. Plots and CSV front tables are
derived outputs.

## Ranking Migration

Ranking should consume AnalysisResult collections and produce derived ranking
records or tables. It should support metric-value rankings, combined score
rankings, and cost-filtered rankings with deterministic tie-breaking by
candidate ID. Ranking should not mutate AnalysisResult JSON.

## Visualization Strategy

Visualization is deferred until after canonical analysis outputs and derived
tables are stable. The first visualization design should provide:

- centralized style configuration;
- objective-axis convention, including thesis convention where applicable;
- plot data adapters from derived tables only;
- no imports from metric computation modules into plotting code;
- no hard-coded thesis paths or campaign branches.

Thesis_Data_Processing notebooks remain the visual and scientific reference,
not an implementation dependency.

## What To Implement First

Start with ANA-001 through ANA-005 and ANA-015:

- candidate ingestion;
- internal result records;
- analysis config and safety gates;
- staged package reader;
- structural cost;
- schema-first tests.

This gives external researchers a usable metadata-only analyzer path before
heavy scientific execution is migrated.

## Deferred Work

- full expressibility and trainability runtime support;
- Parquet export;
- visualization APIs;
- notebook conversion;
- thesis figure reproduction;
- compatibility adapters for Beta table outputs.

## Open Decisions

- final metric identifiers and units;
- exact uncertainty/error structure for metric records;
- whether analyzer heavy dependencies are installed by default or through
  optional extras;
- whether ranking policies are named profiles or plain JSON config;
- whether cross-candidate AnalysisResult bundles need a separate schema.
