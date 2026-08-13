# Ansatz Evolver Implementation Plan

## Summary

This roadmap turns the Phase 6.0 audit into an implementation sequence for
`verfeinert.ansatz_evolver`. The plan is JSON-first and does not preserve
compatibility with old Verfeinert workflows.

The evolver must consume Candidate JSON and AnalysisResult JSON. It must not
import analyzer internals, depend on pandas tables, execute metrics, generate
plots, or branch on campaign names.

## Recommended Implementation Order

1. Resolve the EvolutionRun schema gap for analysis-result references.
2. Implement JSON validation and reference models.
3. Implement population snapshots and deduplication.
4. Implement mutation policy/request records.
5. Define generator boundary and child Candidate JSON production.
6. Define evaluation request/result ingestion.
7. Implement selection policies.
8. Implement run state, stopping, archives, and EvolutionRun export.
9. Add examples after the core is stable.

## Task Roadmap

| Task | Source Logic | Destination | Required Refactor | Dependencies | Validation Criteria |
|---|---|---|---|---|---|
| `EVO-001` schema strategy | `evolution_run.schema.json`; Phase 6 data-model doc | `schemas/evolution_run.schema.json` decision and docs | Decide whether to add `analysis_result_refs` before coding or use documented interim events only for prototypes. | Canonical schema policy. | Decision recorded; schema tests updated if schema changes; no implementation proceeds with an undocumented analysis-result reference shape. |
| `EVO-002` JSON validation/readers | v2 analyzer/generator validation patterns | `ansatz_evolver.validation`, `ansatz_evolver.io` | Load and validate Candidate, StagedPackage, AnalysisResult, and EvolutionRun JSON without analyzer class imports. | `verfeinert.core`, `jsonschema`, schema files. | Invalid documents rejected; valid examples load; no pandas/analyzer/evolver circular imports. |
| `EVO-003` candidate refs and population snapshots | v1 `Individual`, `Population` | `models`, `population.refs` | Replace full operation-bearing individuals with candidate refs and shallow cached identity/status fields. | `EVO-002`. | Ordered refs preserve candidate IDs; duplicate IDs rejected; no full Candidate JSON embedded in population snapshots. |
| `EVO-004` deduplication | v1 `deduplication.py` | `population.deduplication` | Deduplicate candidate refs by structural hash, lineage hash, or candidate ID with explicit keep policy and report. | `EVO-003`. | Deterministic reports for duplicate/missing keys; warnings recorded; original order preserved for keep-first. |
| `EVO-005` mutation policy records | v1 `mutation_policy.py`; Alpha mutation recipes | `mutation.policies`, `mutation.schedules` | Keep recipe/schedule concepts; remove v1 generator imports and campaign presets as defaults. | `verfeinert.core`; optional public generator registry. | Massive/custom schedules validate; probabilities/limits/seeds recorded; unsupported policies fail clearly. |
| `EVO-006` mutation request/result model | v1 `mutation_generation.py`; Alpha template mutation concepts | `mutation.requests`, `mutation.ids` | Model requested child creation without editing circuits inside evolver. Child Candidate JSON comes from public generator APIs or injected factory. | `EVO-003`, `EVO-005`, public generator exporters. | Requests preserve parent/root/generation/mutation metadata; deterministic variant IDs; skipped/no-op status supported. |
| `EVO-007` generator interaction boundary | v1 generator compilation boundary notes; Phase 5.9 exporters | `pipeline` integration hook | Define callable protocol for candidate factories returning canonical Candidate/StagedPackage JSON. Evolver never imports generator internals. | `EVO-006`; public `ansatz_generator` APIs. | Test factory can produce child candidates; lineage validates; no generated callables or QNodes imported. |
| `EVO-008` evaluation request boundary | v1 `analysis_ingestion.py`; v2 AnalysisResult JSON | `evaluation.requests`, `evaluation.results` | Replace analyzer export table ingestion with AnalysisResult JSON request/result refs. | `EVO-002`, `EVO-003`. | Evaluation requests are JSON-safe; result ingestion validates AnalysisResult docs; candidate/result IDs map one-to-one or report missing results. |
| `EVO-009` fitness and threshold selection | v1 `selection.py`; analyzer ranking concepts | `selection.fitness`, `selection.thresholds` | Select over AnalysisResult metrics/cost/classifications with configured expressions and thresholds. | `EVO-008`. | Deterministic survivor/rejection reasons; no metric computation; unavailable metrics produce rejection/warnings. |
| `EVO-010` Pareto and strict-Pareto selection | v1 `strict_pareto_feedback.py`; v2 analyzer Pareto semantics | `selection.pareto`, `selection.strict_pareto` | Reimplement over AnalysisResult JSON objective values and references; cost remains a filter. | `EVO-008`. | Frontier selection matches small fixtures; strict ties, dominated candidates, threshold failures, and no-new-Pareto terminal status tested. |
| `EVO-011` multi-threshold trajectories | v1 `strict_pareto_multithreshold.py`; MIXT-5G config | `selection.multithreshold` or `policies.threshold_trajectories` | Extract generic independent threshold state; remove Sanz/CX/MIXT constants. | `EVO-010`. | Independent survivor/archive refs per threshold; duplicate candidates across thresholds tracked without duplicate analysis. |
| `EVO-012` run state and stopping | v1 runners/manifests | `pipeline.state`, `policies.stopping` | Represent planned/running/completed/failed/cancelled state and policy-driven stopping events. | `EVO-003`, `EVO-008`, `EVO-009`. | Max-generation, no-candidate, no-result, no-survivor, duplicate-only, and strict-no-new-Pareto stops are recorded deterministically. |
| `EVO-013` EvolutionRun exporter | v1 manifests/run storage | `exporters.evolution_run_json` | Make EvolutionRun JSON the primary run artifact; derived summaries are deferred. | `EVO-001`, `EVO-012`. | Exported EvolutionRun validates against schema; refs are relative where possible; provenance records input hashes/config. |
| `EVO-014` derived outputs | v1 summaries/archive tables | `exporters.derived_tables` later | Produce optional JSON/CSV summaries from EvolutionRun and AnalysisResult JSON only. | `EVO-013`. | Tables include source EvolutionRun and AnalysisResult IDs; no table becomes input contract. |
| `EVO-015` MIXT-5G example | v1 MIXT scripts/configs; thesis plots | `examples/MIXT5G_evolution` later | Rebuild as a researcher example over public APIs after core evolver is stable. | `EVO-013`, `EVO-011`. | Example runs or dry-runs with caller-owned outputs; no campaign branches in package code. |

## Internal Model Requirements

Initial internal records should include:

- `CandidateRef`;
- `AnalysisResultRef`;
- `PopulationSnapshot`;
- `MutationRecipe`;
- `MutationPolicy`;
- `MutationSchedule`;
- `MutationRequest`;
- `SelectionDecision`;
- `GenerationState`;
- `EvolutionRunState`;
- `StoppingCondition`.

These are internal helpers around canonical JSON and should not become a
second exchange format.

## Dependency Rules For Implementation

- `core` may not import evolver.
- Evolver may import `core`.
- Evolver should validate Candidate and AnalysisResult JSON through schema
  helpers or local schema loading, not analyzer internal models.
- Evolver may use public generator APIs only at the candidate production
  boundary.
- Non-visual evolver modules must not import Matplotlib, notebooks, pandas,
  PennyLane, generated callables, or `Thesis_Data_Processing`.

If pandas is ever introduced for optional derived tables, it must be an
optional export-layer dependency and not required for importing
`verfeinert.ansatz_evolver`.

## Validation Plan

Future implementation tests should cover:

- EvolutionRun schema validation;
- Candidate and AnalysisResult reference loading;
- reference-based population creation;
- duplicate detection by structural hash, lineage hash, and candidate ID;
- mutation schedule validation and deterministic request generation;
- candidate factory integration with public generator exporters;
- evaluation-result ingestion without analyzer internals;
- fitness, threshold, Pareto, and strict-Pareto selection fixtures;
- independent multi-threshold trajectory state;
- stopping-condition decisions;
- no-QNode/no-plot/no-notebook/no-thesis dependency AST checks.

All tests should be fast, deterministic, and independent of external data.

## Deferred Features

- MIXT-5G researcher example.
- Visualization of evolution history.
- Parquet exports.
- Workflow-runner integration that actively invokes analyzer jobs.
- Distributed execution/backends.
- Resuming partially complete external metric runs.
- Compatibility adapters for old v1 CSV/table outputs.

## Blocked Decisions Before Coding

- Whether to update `evolution_run.schema.json` with first-class
  `analysis_result_refs`.
- Whether parent/rejected population refs need first-class schema fields or
  remain event records.
- Final expression language for fitness selection.
- Final policy for stochastic mutation probabilities versus deterministic
  schedules in the first implementation slice.
- Whether candidate generation is always delegated to generator APIs or can be
  supplied by an external user factory from day one.

## What To Implement First

Implement the schema/reference foundation first:

1. `EVO-001`;
2. `EVO-002`;
3. `EVO-003`;
4. `EVO-013` for planned/empty EvolutionRun export.

This gives external researchers a stable run-state contract before mutation
and selection logic are added.
