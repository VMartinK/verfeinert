# Phase 10.0 Reproducibility Architecture Audit

## Summary

Verfeinert v0.1.0 can run public structural-cost workflows from an external
installation, including candidate generation, canonical JSON export, analyzer
structural metrics, evolver selection, ranking artifacts, and example smoke
runs.

Full scientific reproduction is incomplete. The analyzer can compute
expressibility and trainability when it receives explicit Python
`state_callable` objects, and workflow permissions can allow expensive metric
and QNode-capable execution. However, there is no public declarative bridge
from canonical Candidate JSON to an executable PennyLane state callable, so
`AnalysisResult` records mark expressibility and trainability as skipped with
`"no state callable provided"`.

This audit is documentation only. It does not change framework code, examples,
schemas, commits, tags, or releases.

## Current Architecture

```text
YAML + example-local Python campaign factory
  -> WorkflowRunner.run(candidate_records, metric_callables?)
  -> canonical Candidate/StagedPackage JSON
  -> AnalysisPipeline
      -> CandidateView
      -> structural_cost computed
      -> expressibility/trainability need state_callable
      -> skipped when no callable is supplied
  -> AnalysisResultCollection
  -> evolver selection/EvolutionRun export
  -> ranking JSON/CSV
  -> optional visualization API outside workflow
```

The public workflow runner currently coordinates module APIs without becoming
a scientific backend. That boundary is correct, but it leaves external users
without a YAML-only path for full scientific reproduction.

## Circuit Materialization Audit

Canonical Candidate JSON to circuit representation exists.

- `verfeinert.ansatz_generator.exporters.candidate_json.export_candidate_json()`
  converts generator records into canonical Candidate JSON with
  `circuit.n_qubits`, ordered `circuit.parameters`, and ordered
  `circuit.operations`.
- `verfeinert.ansatz_generator.exporters.staged_package_json.export_staged_package_json()`
  and `write_staged_package_json()` package those candidate documents for
  workflow/analyzer consumption.
- These APIs are public through `verfeinert.ansatz_generator`.

Analyzer-side Candidate JSON loading also exists.

- `verfeinert.ansatz_analyzer.io.load_candidate_views()` accepts a Candidate
  or StagedPackage source and builds `CandidateView` records.
- `CandidateView.from_document()` exposes the analyzer's internal view of
  canonical circuit fields.
- This is public/exported analyzer API, but it is an analysis data view, not
  executable circuit materialization.

PennyLane callable source generation exists, but it is not the needed runtime
bridge.

- `verfeinert.ansatz_generator.compilation.compile_candidate_callable_source()`,
  `build_callable_module_source()`, and `write_callable_module()` emit
  PennyLane-oriented Python source for metadata-style compiled records.
- This API is public through `verfeinert.ansatz_generator`.
- It intentionally writes source without importing it, creating QNodes, running
  metrics, or executing QNodes. Tests assert generated source does not include
  `@qml.qnode`.
- It targets compiled metadata records, not canonical Candidate JSON, and it
  requires a user to import/wrap generated source in campaign-specific Python.

QNode creation and state callable generation from canonical Candidate JSON are
missing.

The minimal missing abstraction is an analyzer-owned materialization boundary,
for example:

```text
Candidate JSON / CandidateView
  -> CircuitMaterializer
  -> PennyLane operation application
  -> QNode on configured device/backend
  -> differentiable state_callable(params)
```

The abstraction should live in `verfeinert.ansatz_analyzer`, because
scientific metric execution is analyzer responsibility. The generator should
remain backend-independent and should not import PennyLane.

## Analyzer Interface Audit

Complete path today:

```text
Candidate records or YAML-driven examples
  -> WorkflowRunner.run(candidate_records, metric_callables=None by default)
  -> write_staged_package_json()
  -> AnalyzerConfig from WorkflowRunner._analyzer_config()
  -> AnalysisPipeline.run_and_write(staged_package_path, metric_callables)
  -> load_candidate_views()
  -> _optional_metric_records()
  -> compute_expressibility_metric()/compute_trainability_metric()
```

Expressibility and trainability are requested in
`AnalyzerConfig.selected_metrics`. `AnalyzerConfig` supports the metric names
`structural_cost`, `expressibility`, and `trainability`; it rejects expensive
metrics unless `permissions.allow_expensive_metrics=True`.

`state_callable` is expected in `AnalysisPipeline._optional_metric_records()`.
The lookup accepts either:

- nested mapping: `metric_callables["expressibility"][candidate_id]`;
- flat mapping: `metric_callables[candidate_id]`.

If no callable is found, the analyzer writes a canonical skipped metric with
reason `"no state callable provided"`. This happens before the metric-specific
permission checks, because no metric execution is attempted.

The metric implementations are otherwise usable:

- `compute_expressibility_metric(candidate, state_callable, ...)` computes
  fidelity-sampling expressibility over explicit state callables.
- `compute_trainability_metric(candidate, state_callable, ...)` computes the
  Local-X trainability metric over explicit state callables.
- Both functions record expensive metric metadata and execution flags.

The callable is lost at workflow execution because `WorkflowRunner.run()`
forwards only caller-supplied `metric_callables`. YAML configuration cannot
declare a state callable provider or materializer, and `WorkflowRunner` does
not derive callables from the staged Candidate JSON it just wrote.

Current API judgment:

- Appropriate for advanced Python users who can build callables manually.
- Incomplete for public scientific reproduction, because external users must
  write campaign-specific Python to reproduce expressibility/trainability.
- The workflow runner should not become a QNode engine; it should pass
  analyzer configuration into an analyzer-owned materializer.

## Workflow Audit

The workflow modules currently support these stage names:

```text
generate
analyze
evolve
rank
```

There is no supported `visualize` stage.

Current runner behavior is more coupled than the stage list suggests:

- generation always runs;
- analysis always runs;
- evolver selection and `EvolutionRun` export always run;
- ranking is gated by `"rank" in config.stages`;
- visualization is outside the runner.

Recommended campaign stage semantics:

```text
Individual campaigns:
  CX01, CZ01, CRX01
  -> generate
  -> analyze
  -> rank
  -> visualize

Evolutionary campaigns:
  CX 4G, MIXT5G
  -> generate
  -> analyze
  -> evolve
  -> rank
  -> visualize
```

Individual campaigns should not require an evolution stage or `EvolutionRun`
export merely to rank/analyze candidate variants. Evolutionary campaigns need
generation-by-generation mutation, analysis, selection, archive, and lineage
state. Today, MIXT5G handles this through an example-local Python loop that
calls `WorkflowRunner` once per generation and writes a combined evolution
record afterward.

Current coupling:

- CX01 candidate construction lives in
  `examples/CX01_reproduction/scripts/run_cx01_reproduction.py`, including
  edge expansion, placement, and knock-in record construction.
- MIXT5G initial population, schedule iteration, parent annotation, child
  construction, per-generation runner calls, and combined evolution export
  live in `examples/MIXT5G_reproduction/scripts/run_mixt5g_reproduction.py`.
- Workflow source intentionally avoids campaign-specific branches, which is a
  good boundary, but there is not yet a declarative campaign/policy layer to
  replace the example-local Python.

## Configuration Audit

YAML can currently configure the following workflow-level fields:

- run identity, creation timestamp, and random seed;
- output root and input roots;
- generation family `sanz19` or `provided`;
- Sanz19 template IDs, layers, qubit count, candidate ID prefix, source label,
  and metadata;
- analyzer selected metrics;
- structural-cost reference bounds, component weights, and depth proxy policy;
- analyzer expensive metric permissions;
- analyzer metric-specific configs;
- ranking score components and ranking behavior;
- evolver selection mode, objectives, thresholds, keep count, direction, and
  max generations;
- execution mode, worker count, scope, and candidate parallelization.

YAML cannot currently declaratively configure:

- executable quantum backend/device for candidate materialization;
- Candidate JSON to PennyLane QNode/state-callable conversion;
- state callable provider selection;
- visualization outputs or a workflow `visualize` stage;
- mutation schedules as framework workflow behavior;
- campaign factories for CX01, CZ01, CRX01, CX 4G, or MIXT5G without
  example-specific Python;
- full multi-generation workflow execution with mutation/evaluation feedback
  inside the public `WorkflowRunner`.

Undocumented or surprising required fields and conventions:

- `AnalyzerConfig.from_mapping()` requires `run_id`, `input_roots`, and
  `output_root`, but workflow users do not provide these directly because
  `WorkflowRunner._analyzer_config()` synthesizes them.
- `WorkflowConfig.from_mapping()` reads top-level `stages`; it does not read
  nested `workflow.stages`. The CX01 example YAML contains `workflow.stages`,
  so that field is currently ignored.
- `generation.family: provided` requires Python-side `candidate_records`.
  YAML cannot point at a campaign policy that produces those records.
- Expensive metrics can be selected only when permissions allow them, but
  permissions alone do not provide the needed state callables.

## Visualization Audit

Visualization logic is public as importable analyzer API:

- `pareto_plot_data()` consumes `AnalysisResultCollection` or `ParetoResult`.
- `plot_pareto_front()` builds a Matplotlib figure lazily.
- `ranking_plot_data()` and `plot_ranking_scores()` consume `RankingResult`.
- `lineage_plot_data()` and `evolution_plot_data()` consume analyzer result
  collections.
- `save_figure()` writes to guarded caller-owned paths.

Plots are generated from public analyzer/derived outputs rather than notebooks
or private data folders. Matplotlib is optional and imported lazily.

Notebooks are not required by the package APIs. The example notebooks are
researcher-facing wrappers over scripts and public APIs, not framework
dependencies.

There is no public visualization command and no workflow-level visualization
stage. Users must write Python to load `AnalysisResultCollection`, run ranking
or Pareto transforms as needed, call visualization functions, and save figures.

## Missing Interfaces

Minimal interfaces required before public full scientific reproduction:

- `CircuitMaterializationConfig`: declarative backend/device settings, default
  device, interface/differentiation policy, execution flags, and optional
  work limits.
- `MaterializedCircuit`: candidate ID, backend label, QNode/callable metadata,
  parameter ordering, and `state_callable`.
- `make_state_callable(candidate, config)`: public analyzer API accepting
  canonical Candidate JSON or `CandidateView`.
- `StateCallableProvider`: optional batch/provider abstraction used by
  `AnalysisPipeline` to obtain callables per candidate when explicit
  `metric_callables` are absent.
- Workflow analyzer config passthrough for the materialization block.
- Declarative campaign/policy layer for mutation schedules and campaign
  factories that keeps campaign names out of framework internals.
- Public visualization runner/API that can write configured figures from
  analysis/ranking/Pareto outputs without notebooks.

## Recommended Phase 10.1 Implementation Plan

Implement the minimal bridge in the analyzer, not the generator or workflow.

1. Add analyzer-owned circuit materialization.
   - Add `verfeinert/ansatz_analyzer/circuits.py` or equivalent.
   - Define `CircuitMaterializationConfig`, `MaterializedCircuit`, and
     `make_state_callable(candidate, config)`.
   - Consume canonical Candidate JSON or `CandidateView`.
   - Map canonical gate records to PennyLane operations.
   - Bind trainable parameters in `circuit.parameters` order.
   - Preserve literal parameters.
   - Create a `default.qubit` state QNode and expose a differentiable
     `state_callable(params)`.

2. Extend analyzer configuration.
   - Add a disabled-by-default materialization/backend config block.
   - Keep current behavior when materialization is disabled: expensive metrics
     without explicit callables remain skipped.
   - Keep explicit permissions for expensive metric and QNode execution.

3. Update analyzer pipeline behavior.
   - Preserve explicit `metric_callables` as the highest-priority override.
   - If no explicit callable exists and materialization is enabled, create a
     candidate state callable through the analyzer materializer.
   - Record backend label, QNode execution expectations, and failure/skipped
     reasons truthfully in metric metadata.

4. Keep workflow as orchestration.
   - Pass analyzer materialization config through to `AnalyzerConfig`.
   - Do not import PennyLane or construct QNodes in `verfeinert.workflow`.
   - Decouple stage execution so `evolve` is optional, not implicit.

5. Add declarative reproduction support.
   - Promote mutation/campaign policies currently embedded in example scripts
     into campaign-neutral framework configuration.
   - Support individual campaign flows without evolution.
   - Support evolutionary campaign flows with generation-by-generation
     mutation, analysis, selection, and archive state.

6. Add visualization execution surface.
   - Either add a workflow `visualize` stage or document visualization as
     API-only until a later phase.
   - Prefer figure generation from `AnalysisResultCollection`,
     `RankingResult`, and `ParetoResult` artifacts.

## Files Expected To Change In Phase 10.1

- `verfeinert/ansatz_analyzer/circuits.py` or equivalent new materialization
  module.
- `verfeinert/ansatz_analyzer/config.py`
- `verfeinert/ansatz_analyzer/pipeline.py`
- `verfeinert/ansatz_analyzer/__init__.py`
- `verfeinert/workflow/config.py`
- `verfeinert/workflow/runner.py`
- `examples/CX01_reproduction/config/cx01_reproduction.yaml`
- `examples/MIXT5G_reproduction/config/mixt5g_reproduction.yaml`
- analyzer materialization tests;
- workflow expensive-metric reproduction tests;
- external validation tests for full-lite scientific reproduction;
- user and architecture documentation for declarative scientific reproduction.

Schema changes should be avoided in Phase 10.1 unless a public
experiment/workflow schema is intentionally promoted.

## Phase 10.1 Test Scenarios

- Candidate JSON to PennyLane state callable for static gates.
- Candidate JSON to PennyLane state callable for parameterized gates.
- Literal parameter preservation and trainable parameter ordering.
- Expressibility computed through auto-materialized state callable with tiny
  budgets.
- Trainability computed through auto-materialized state callable with tiny
  budgets.
- Explicit `metric_callables` override auto-materialization.
- Expensive metrics remain skipped when materialization is disabled.
- Permission denial still produces skipped metrics when permissions are false.
- Workflow YAML-selected expensive metrics plus permissions produce computed
  metrics, not `"no state callable provided"`.
- Individual campaign stages omit evolution and do not write an `EvolutionRun`
  unless requested.
- Evolutionary campaign stages run generation, analysis, evolution, ranking,
  and visualization in order.
- External installation validation includes at least one full-lite scientific
  reproduction path without campaign-specific Python.

## Assumptions And Defaults

- Generator remains backend-independent and does not import PennyLane.
- Analyzer owns scientific metric execution and QNode-backed materialization.
- Workflow remains an orchestrator, not a scientific execution backend.
- Public declarative reproduction should not require users to write
  campaign-specific Python.
- Existing smoke examples remain valid structural workflows until Phase 10.1
  adds the materialization bridge.
