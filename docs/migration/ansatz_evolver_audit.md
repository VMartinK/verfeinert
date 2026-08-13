# Ansatz Evolver Audit

## Summary

This audit covers the current evolution-related material in the TFG
repository and classifies what should inform the future
`verfeinert.ansatz_evolver` architecture.

Phase 6.0 is documentation-only. No `Verfeinert/` code, legacy notebooks,
schemas, generator/analyzer modules, experiments, or outputs are modified.

The future evolver is not a compatibility layer for Verfeinert v1. It will use
canonical Candidate JSON and AnalysisResult JSON as its only scientific
exchange contracts.

## Classification Key

- **A migrate directly:** concept or pure behavior can move into v2 with only
  naming/API adaptation.
- **B refactor before migration:** scientific behavior is useful, but current
  implementation is table-oriented, campaign-specific, v1-import coupled, or
  path-bound.
- **C keep only as thesis-specific material:** useful as scientific reference
  or figure provenance, not package code.
- **D discard:** generated artifacts, caches, scratch outputs, duplicates, or
  smoke harnesses that must not become framework APIs.

## Current Stable V2 Context

`Verfeinertv2/verfeinert/ansatz_evolver/` currently contains only the namespace
placeholder. The stable upstream v2 flow is:

```text
ansatz_generator
    -> Candidate JSON / StagedPackage JSON
    -> ansatz_analyzer
    -> AnalysisResult JSON
```

The evolver must attach to this flow through canonical JSON documents, not
through analyzer internal classes, pandas tables, visualization outputs, or
notebook-local data.

## Component Audit

| Component | Class | Current Location | Scientific Purpose | Current Dependencies | Future Destination | Required Refactor | Risks |
|---|---:|---|---|---|---|---|---|
| `Individual` record | B | `Verfeinert/src/ansatz_evolver/population.py` | Represents one evolved candidate with lineage and structural metadata. | `pandas`, Beta flat fields, full operation payloads. | `verfeinert.ansatz_evolver.models.CandidateRef` and `population.PopulationSnapshot`. | Store canonical candidate references only; keep shallow identity cache and role/status metadata. | Copying full operations would duplicate Candidate JSON and create drift. |
| `Population` record | B | `Verfeinert/src/ansatz_evolver/population.py` | Groups individuals by generation and supports validation/grouping. | `pandas`, DataFrame roundtrips. | `population.PopulationSnapshot`, `population.GenerationPopulation`. | Replace DataFrames with ordered JSON-safe records and canonical candidate refs. | Old layer grouping depends on Beta `layer` fields that are not canonical selectors. |
| Deterministic circuit ID functions | A | `Verfeinert/src/ansatz_evolver/circuit_ids.py` | Creates stable evolved candidate IDs and mutation codes. | stdlib only. | `models.ids` or `mutation.ids`. | Adapt names from `circuit_id` to canonical `candidate_id`; keep mutation details in lineage metadata, not parse-only IDs. | Over-encoding scientific semantics in IDs can become brittle. |
| Deduplication report | A | `Verfeinert/src/ansatz_evolver/deduplication.py` | Records duplicate counts and duplicate identity fields. | Beta `Population`. | `population.deduplication`. | Use canonical `identity.structural_hash`, `identity.lineage_hash`, and `candidate_id`. | Missing hashes must be explicit warnings, not silent equality decisions. |
| Deduplication implementation | B | `Verfeinert/src/ansatz_evolver/deduplication.py` | Keeps first/last candidate by structural or lineage key. | Beta population objects. | `population.deduplicate_candidate_refs`. | Operate on canonical refs; expose policy configuration. | Deduplicating by `candidate_id` can hide structural duplicates if hashes exist. |
| `EvolutionConfig` | B | `Verfeinert/src/ansatz_evolver/config.py` | Validates generation, mutation, selection, and output settings. | Beta naming, campaign defaults, table assumptions. | `policies.config` and `pipeline.EvolutionRunConfig`. | Split into run config, mutation policy, selection policy, evaluation permissions, stopping criteria. | Hardcoded defaults such as CX-only or cost thresholds should not become v2 defaults. |
| Mutation recipes/policies/schedules | A/B | `Verfeinert/src/ansatz_evolver/mutation_policy.py` | Defines deterministic mutation recipes, massive/custom schedules, and limits. | Imports v1 generator gate constants. | `mutation.Policy`, `mutation.Recipe`, `mutation.Schedule`. | Keep recipe/schedule concepts; validate gates through public generator registry or caller-supplied registry. | Direct generator imports can create tight coupling if not isolated. |
| Metadata child generation | B | `Verfeinert/src/ansatz_evolver/mutation_generation.py` | Generates child operation records, lineage, mutation metadata, and hashes. | `pandas`, v1 generator compilation constants, Beta `Population`. | `mutation.operators` plus generator-facing candidate factory. | Refactor to produce canonical Candidate JSON through public generator/exporter APIs or injected candidate factory. | Evolver must not become a circuit compiler or QNode/runtime layer. |
| Layer propagation mutation concept | A | `Verfeinert/src/ansatz_evolver/mutation_generation.py`; `python/ansatz_generator/mutations/template_mutation.py` | Mutate one template unit and repeat across layers. | Alpha/Beta genome and operation records. | `mutation.layer_policies` or generator mutation adapters. | Preserve as a named mutation policy with canonical lineage metadata. | Needs careful parameter renaming and lineage preservation. |
| Insert/replace/remove/swap/reorder concepts | A | `Verfeinert/src/ansatz_evolver/mutation_policy.py`; Alpha mutation modules. | Structural mutation families for candidate evolution. | Beta/Alpha internal operation models. | `mutation.operators` or generator-owned mutation functions. | Define abstract mutation request/result records; delegate concrete operation edits to generator where possible. | Duplicating generator mutation logic in evolver would split scientific behavior. |
| Survivor selection from Pareto-like table | B | `Verfeinert/src/ansatz_evolver/selection.py` | Selects survivors by cost threshold, Pareto category, score, and deterministic ordering. | `pandas`, table columns, Beta labels. | `selection.policies`. | Operate on AnalysisResult JSON and classification records; make objective/cost fields configurable. | Category names from v1 may not match v2 classifications one-to-one. |
| Strict Pareto feedback selector | A/B | `Verfeinert/src/ansatz_evolver/strict_pareto_feedback.py` | Selects strict new Pareto candidates against accumulated frontier, no fallback. | `pandas` tables. | `selection.strict_pareto`. | Keep semantics; reimplement over AnalysisResult JSON and reference collections. | Strict tie handling must be reproducible and documented. |
| True multithreshold utilities | B | `Verfeinert/src/ansatz_evolver/strict_pareto_multithreshold.py` | Maintains independent threshold trajectories and canonical ID hygiene. | `pandas`, campaign constants, Sanz-specific expectations. | `policies.threshold_trajectories`, `selection.multithreshold`. | Extract generic threshold-trajectory model; remove expected template IDs and Sanz/CX/MIXT branches. | Campaign constants can accidentally become framework rules. |
| Analysis ingestion | B | `Verfeinert/src/ansatz_evolver/analysis_ingestion.py` | Loads analyzer exports, selects survivors, writes selected/rejected/archive tables. | `numpy`, `pandas`, CSV export layout. | `evaluation.results` and `selection.inputs`. | Load canonical AnalysisResult JSON; derived tables stay optional exports. | Depending on analyzer table paths would violate v2 architecture. |
| Run storage layout helpers | B | `Verfeinert/src/ansatz_evolver/run_storage.py` | Defines run/generation/archive paths and CSV/JSON writers. | `pandas`, fixed output layout. | `pipeline.storage` and `exporters.evolution_run_json`. | Use caller-owned output roots and EvolutionRun JSON as primary record; make tables derived artifacts. | Fixed `plots/` and CSV-first layout conflicts with no-visualization boundary. |
| Generation manifests | A/B | `Verfeinert/src/ansatz_evolver/manifest.py` | Records parent/child counts, config snapshot, deduplication, and selection summary. | Beta config/population assumptions. | `models.GenerationRecord` and EvolutionRun events. | Fold into canonical EvolutionRun generations and events. | Manifest duplication can conflict with `evolution_run.schema.json`. |
| Simple `EvolutionRunner` | B | `Verfeinert/src/ansatz_evolver/runner.py` | Composes child generation, deduplication, optional selection, and writes. | Beta config, Beta population, pandas selection inputs. | `pipeline.EvolutionPipeline`. | Rebuild around explicit JSON stages and injected analysis execution boundary. | It must not import analyzer or generator internals. |
| Multigeneration `run_evolution` runner | B | `Verfeinert/src/ansatz_evolver/evolution_run.py` | Coordinates mutation, compilation, analyzer runs, selection, archive, summary. | `pandas`, `numpy`, analyzer internals, generator compilation, env gates. | `pipeline` plus external orchestration hooks. | Separate planning, generation, analysis request, result ingestion, selection, and export. | Direct analyzer imports are forbidden in v2. |
| I/O helpers | B | `Verfeinert/src/ansatz_evolver/io.py` | Writes populations and generation manifests. | CSV/table assumptions. | `io` and `exporters`. | Use `verfeinert.core` JSON/path helpers and guarded output roots. | Derived CSV exports may be mistaken for canonical state. |
| Schema constants | B | `Verfeinert/src/ansatz_evolver/schemas.py` | Defines Beta table/manifest schemas. | Beta field names. | `models` constants where needed. | Align with canonical schema versions and Candidate/AnalysisResult refs. | Reusing Beta schema names would reintroduce compatibility fields. |
| Strict Pareto feedback scripts | C | `Verfeinert/scripts/run_strict_pareto_feedback_*.py` | Reproduce CX and MIXT evolution campaigns. | Repo-relative paths, configs, pandas, analyzer/generator v1 modules. | Future `examples/MIXT5G_evolution/` reference only. | Extract scientific strategy into v2 policies; scripts remain thesis provenance. | Hardcoded paths and run IDs are not framework APIs. |
| Evolution config examples | C/B | `Verfeinert/configs/*strict_pareto*`, `*evolution_mutation_schedule*` | Document historical CX/MIXT schedules and thresholds. | Campaign paths and v1 run IDs. | Future examples/config docs. | Convert to campaign-neutral YAML/JSON examples after core evolver exists. | Copying them directly would create campaign-specific branches. |
| Beta evolver tests and Behave features | B/C | `Verfeinert/tests/evolver/*` | Contract coverage for mutation, population, selection, storage, smoke runs. | v1 import paths, scripts, tmp outputs, Behave. | v2 unit-test design reference. | Rewrite as lightweight `unittest` tests over canonical JSON. | Smoke scripts should not be migrated as runtime code. |
| Alpha population instantiation | C/B | `python/ansatz_generator/experiments/population.py` | Instantiates template populations and summaries. | Alpha genome/template/constraints. | Generator examples or candidate factory reference. | Use public v2 generator APIs and canonical Candidate JSON. | Alpha genome concepts are superseded by v2 candidate contracts. |
| Alpha mutation smoke campaign | C | `python/ansatz_generator/experiments/mutation_smoke_campaign.py` | Demonstrates mutation families, validation, reports, visuals. | PennyLane, Matplotlib, Alpha internals, paths. | Thesis/reference material only. | Pull conceptual mutation catalog only. | Includes visualization and notebook/report behavior outside evolver scope. |
| Alpha template/permutation mutations | B/C | `python/ansatz_generator/mutations/*` | Template-unit knock-in/permutation concepts. | Alpha genomes, constraints, validators. | Generator mutation adapters or evolver policy docs. | Re-express as policy requests against canonical candidates. | Direct migration would duplicate generator internals. |
| Thesis evolution notebooks and outputs | C | `Thesis_Data_Processing/*evo*`, `mixt_5g_plots.ipynb`, comparison outputs. | Final thesis figures, postprocessing, scientific interpretation. | pandas, Matplotlib, local CSV/PNG/PDF/SVG outputs. | Documentation/examples reference only. | Use as visual/scientific validation references, not package inputs. | Notebooks contain executed state and thesis-specific paths. |
| Generated outputs/caches | D | `Verfeinert/tmp/**`, `__pycache__`, generated callables/results. | Historical run artifacts. | Local filesystem state. | None. | Do not migrate. | Treating generated outputs as source would break reproducibility. |

## Scientific Concepts To Preserve

- Candidate lineage must record parent, root, generation, mutation type,
  mutation operation, and mutation parameters.
- Population evolution should be deterministic when a random seed and policy
  configuration are fixed.
- Deduplication by structural identity is scientifically useful and must be
  auditable.
- Strict Pareto feedback is a valid selection policy, but it is one policy
  among several, not the framework's only strategy.
- Multi-threshold selection trajectories are useful for MIXT-5G-style
  workflows, but threshold values and schedules are configuration data.
- Cost is a selection filter or ranking component depending on policy; it must
  not silently become a Pareto objective.

## Main Refactor Drivers

- Replace pandas/DataFrame-first population and selection with canonical JSON
  records and optional derived tables.
- Replace analyzer-internal imports with AnalysisResult JSON ingestion.
- Replace generator compilation imports with public generator APIs or injected
  candidate factories.
- Keep plotting and visualization out of evolver internals.
- Keep campaign names such as CX and MIXT in examples/metadata only.
- Move external paths to caller-owned configuration and preserve provenance via
  hashes and relative artifact references.

## Architecture Blocker

`Verfeinertv2/schemas/evolution_run.schema.json` currently records
`candidate_refs`, `survivor_refs`, and `archive_refs`, but does not provide a
first-class `analysis_result_refs` field. Phase 6.0 should document interim
event-based references and require a schema decision before implementing the
evolver.
