# Ansatz Analyzer Audit

## Scope

This audit covers analyzer-related material in the current TFG repository as a
scientific reference for the future `verfeinert.ansatz_analyzer` package. It
does not define a compatibility layer for old Verfeinert workflows.

The future analyzer must consume canonical `verfeinert.candidate.v1` JSON and
produce canonical `verfeinert.analysis_result.v1` JSON. CSV, notebook tables,
figures, and thesis exports are derived artifacts only.

## Classification Key

- A: migrate directly
- B: refactor before migration
- C: keep only as thesis material
- D: discard

## Current Architecture Summary

The canonical Beta analyzer implementation lives under
`Verfeinert/src/ansatz_analyzer`. It is already separated from generator and
evolver packages at the source-tree level, but it still uses top-level imports,
pandas-first tables, generated callable loading, notebook-facing config names,
and several TFG-local output conventions.

The strongest reusable scientific behavior is:

- structural cost from parameter count, depth or operation-count proxy, and
  two-qubit gate count;
- expressibility as fidelity-distribution D_KL and `-log10(D_KL)`;
- trainability as the Holmes/Sanz-style active mean squared gradient proxy;
- two-objective Pareto analysis in the expressibility/trainability plane;
- cost thresholds treated as external constraints, not Pareto objectives;
- deterministic ranking by metric score with stable ID tie-breaks;
- conservative execution flags around QNode and expensive metric execution.

The main migration correction is directional: JSON must become the internal
exchange format. Current analyzer tables are useful views, but they must be
derived from canonical Candidate and AnalysisResult documents.

## Component Audit

| Class | Component | Current location | Scientific purpose | Future destination | Required changes |
| --- | --- | --- | --- | --- | --- |
| A | Structural cost formula and reference bounds | `Verfeinert/src/ansatz_analyzer/metrics/structural_cost.py` | Computes normalized structural cost from parameter count, depth, and two-qubit count; reports reference-range status. | `verfeinert.ansatz_analyzer.metrics.structural_cost` | Preserve formula and warning semantics. Replace pandas table contract with record-first Candidate JSON input and AnalysisResult cost output. |
| A | Expressibility definition | `Verfeinert/src/ansatz_analyzer/metrics/expressibility.py` | Samples state fidelities, compares to Haar distribution, reports D_KL and log expressibility score. | `verfeinert.ansatz_analyzer.metrics.expressibility` | Preserve metric definition, RNG policies, and budget accounting. Refactor callable execution behind explicit backend/execution boundary. |
| A | Trainability definition | `Verfeinert/src/ansatz_analyzer/metrics/trainability.py` | Samples gradients of a Local-X Hamiltonian expectation and reports active mean squared gradient. | `verfeinert.ansatz_analyzer.metrics.trainability` | Preserve metric definition, Hamiltonian helper, active-gradient handling, and deterministic seeds. Move PennyLane dependence behind explicit metric execution. |
| A | Generic Pareto dominance concept | `python/analysis/campaigns/pareto_helpers.py` and pure parts of `Verfeinert/src/ansatz_analyzer/reporting/pareto_reporting.py` | Computes nondominated rows with objective directions and stable tie behavior. | `verfeinert.ansatz_analyzer.classification.pareto` | Keep objective-direction abstraction. Rebuild around AnalysisResult collections and classification records. |
| A | Score transforms | `Verfeinert/src/ansatz_analyzer/reporting/metric_scores.py`, `analysis_export.py` | Normalizes expressibility from D_KL, copies trainability score, derives combined score. | `verfeinert.ansatz_analyzer.tables.scoring` or `ranking` helpers | Preserve formulas. Make them derived-table transforms, not canonical metric mutation. |
| B | Public analyzer export surface | `Verfeinert/src/ansatz_analyzer/__init__.py` | Re-exports configs, metrics, staging, writer, pipeline, reporting, and bootstrap helpers. | `verfeinert.ansatz_analyzer.__init__` | Rebuild from future public contracts only. Do not expose notebook bootstrap or legacy table helpers as core analyzer API. |
| B | Analyzer config models | `Verfeinert/src/ansatz_analyzer/config.py` | Captures analysis identity, layers, metrics, output options, notebook controls, and safety flags. | `verfeinert.ansatz_analyzer.config` | Replace `campaign_slug` and notebook fields with Experiment/Candidate/AnalysisResult contracts. Keep explicit safety flags and caller-owned roots. |
| B | Metric workspace and result shell | `Verfeinert/src/ansatz_analyzer/schemas.py` | Tracks planned metric status, empty metric records, QNode flags, and completion state. | `verfeinert.ansatz_analyzer.models` and `validation` | Convert to canonical AnalysisResult metric statuses: `computed`, `skipped`, `failed`. Remove notebook compatibility payload shape. |
| B | Final payload builder | `Verfeinert/src/ansatz_analyzer/payload.py` | Builds `verfeinert.analysis_result.v1`-named Beta payloads from metric result dictionaries and optional tables. | `verfeinert.ansatz_analyzer.results` | Replace with schema-conformant per-candidate AnalysisResult documents. Use `verfeinert.core` JSON-safe serialization. |
| B | Staged campaign reader | `Verfeinert/src/ansatz_analyzer/staging.py` | Loads staged metadata, selects candidate IDs, hashes metadata/module files, and can load generated callables without invoking them. | `verfeinert.ansatz_analyzer.io` and `inputs` | Read canonical StagedPackage/Candidate JSON. Keep deterministic selection concepts. Generated callable loading must be optional and execution-gated. |
| B | I/O helpers | `Verfeinert/src/ansatz_analyzer/io.py` | Reads/writes JSON and creates directories for analysis. | `verfeinert.ansatz_analyzer.io` | Replace local helpers with `verfeinert.core.io`; validate output roots away from source and inputs. |
| B | Analysis result writer | `Verfeinert/src/ansatz_analyzer/writer.py` | Writes payload JSON, metric table JSON, summary markdown, and manifest into explicit result roots. | `verfeinert.ansatz_analyzer.io` and `tables.exports` | Keep manifest and reload idea. Write canonical AnalysisResult JSON first; write summaries/tables as derived artifacts. |
| B | Minimal analysis pipeline | `Verfeinert/src/ansatz_analyzer/pipeline.py` | Composes structural cost and Pareto on pandas tables. | `verfeinert.ansatz_analyzer.pipeline` | Rebuild as Candidate JSON -> AnalysisResult JSON orchestration. No table-first inputs. |
| B | Campaign analysis runner | `Verfeinert/src/ansatz_analyzer/campaign_runner.py` | Orchestrates staged packages, selected candidate metrics, structural cost recovery, export package writing, and budget manifests. | `verfeinert.ansatz_analyzer.pipeline` plus metric execution helpers | Keep guarded execution and budget ideas. Remove campaign defaults, Beta output columns, generated-module assumptions, and pandas-first run storage. |
| B | Analysis export pipeline | `Verfeinert/src/ansatz_analyzer/analysis_export.py` | Merges candidate/metric/metadata tables; builds scores, rankings, Pareto tables, generation summaries, and manifests. | `verfeinert.ansatz_analyzer.tables` and `ranking` | Make this a derived-output layer from AnalysisResult JSON. Do not let export tables be canonical storage. |
| B | Pareto metric module | `Verfeinert/src/ansatz_analyzer/metrics/pareto.py` | Builds current/imported global and cost-constrained Pareto fronts with categories. | `verfeinert.ansatz_analyzer.classification.pareto` | Separate classification policy from metric computation and reporting. Keep cost as constraint. Replace imported campaign tables with explicit reference result sets. |
| B | Ranking helpers | `Verfeinert/src/ansatz_analyzer/reporting/rankings.py` | Builds deterministic top-N score rankings. | `verfeinert.ansatz_analyzer.ranking` | Rank AnalysisResult collections. Parameterize score key and tie-break policy. |
| B | Generation summaries | `Verfeinert/src/ansatz_analyzer/reporting/generation_summary.py` | Summarizes metric trajectories by generation and includes plotting helpers. | `verfeinert.ansatz_analyzer.tables.summaries`; plotting later in `visualization` | Split table summary from plotting. Use EvolutionRun/AnalysisResult references rather than generation columns as primary data. |
| B | Baseline/Pareto reporting plots | `Verfeinert/src/ansatz_analyzer/reporting/pareto_reporting.py` | Computes baseline comparisons and plots baseline vs candidate fronts. | `classification.pareto`, `tables.pareto`, and deferred `visualization.objective_space` | Move pure classification separately from Matplotlib functions. Centralize style and axis conventions. |
| B | Design-space plotting | `Verfeinert/src/ansatz_analyzer/reporting/design_space.py` | Plots objective-space design points filtered by structural cost. | Deferred `verfeinert.ansatz_analyzer.visualization.design_space` | Keep as visualization reference only until style and data contracts are stable. |
| B | Sanz-style metric matrices | `Verfeinert/src/ansatz_analyzer/reporting/sanz_tables.py` | Builds family-by-layer metric matrices and notebook stylers. | `verfeinert.ansatz_analyzer.tables.matrices`; style part deferred | Keep matrix transform. Drop hard-coded L1/L2/L3 assumptions or make them explicit configuration. |
| C | CX-01 legacy loader | `Verfeinert/src/ansatz_analyzer/reporting/cx01_loader.py` | Maps historical CX-01 CSVs and staged metadata into reporting tables. | Example or thesis appendix only | Do not migrate as package API because it is campaign-specific and path-specific. Extract only generic alias-mapping lessons if needed. |
| B | Notebook bootstrap | `Verfeinert/src/ansatz_analyzer/bootstrap.py`, `python/analysis/lib/paths.py` | Finds project roots and mutates `sys.path` for notebooks. | Examples/notebook endpoint guidance | Avoid package APIs that depend on repository layout. Future examples should import installed package or editable checkout normally. |
| B | Clean analyzer notebooks | `Verfeinert/notebooks/*_clean_interface.ipynb` | Thin, unexecuted endpoints using analyzer/generator APIs and safety flags. | `Verfeinertv2/notebooks` or `examples` after analyzer migration | Keep as endpoint reference. Rebuild against canonical JSON and final namespace. Do not copy notebook structure into package modules. |
| C | Plot example notebook | `Verfeinert/notebooks/plot_example.ipynb` | Demonstrates reporting tables and plotting using CX-01 legacy data. | Example material after visualization design | Keep as a reference for expected plots and smoke coverage. Do not migrate historical data loader into package internals. |
| D | Backup notebook | `Verfeinert/notebooks/legacy/ansatz_interface_clean_backup_*.ipynb` | Historical duplicate. | None | Remove from migration consideration. |
| C | Individual thesis plotting notebooks | `Thesis_Data_Processing/cx01_individual_plots.ipynb`, `cz01_individual_plots.ipynb`, `swap01_individual_plots.ipynb`, `crx01_individual_plots.ipynb`, `cry01_individual_plots.ipynb`, `crz01_individual_plots.ipynb`, `subs01_individual_plots.ipynb`, `end01_individual_plots.ipynb` | Final campaign-specific plots, baseline classification, annotation placement, cost reconstruction, figure/table exports. | Thesis material; selected logic can inform `visualization` and `classification` tests | Do not migrate notebooks or paths. Extract reusable formulas only after analyzer contracts are implemented. |
| C | Global and evolution thesis plotting notebooks | `Thesis_Data_Processing/global_analysis_plots.ipynb`, `evolutive_comparison_plot.ipynb`, `cx_4g_true_multithreshold_evolution_plots_definitive.ipynb`, `mixt_5g_plots.ipynb` | Final global comparison, frontier evolution, lineage plots, publication styling, plot-data exports. | Thesis material; future examples may reproduce with public APIs | Keep as scientific reference. Do not make campaign names or final thesis labels code branches. |
| C | Alpha analysis notebooks and outputs | `python/analysis/*.ipynb`, `python/analysis/campaigns/*.ipynb`, `python/analysis/Alpha v2 validation/results.csv`, `python/analysis/outputs_alpha/*`, `python/analysis/analysis_results/*` | Historical manual analysis, Pareto templates, validation CSVs, staged outputs, and external result writing. | Thesis/history docs or examples only | Use as evidence for provenance and safety needs. Do not migrate old import paths or result schemas. |
| B | Alpha analysis I/O concepts | `python/ansatz_generator/analysis_io/*` | Input references, safety flags, staged loading, traceable result writing. | `verfeinert.ansatz_analyzer.io`, `models`, and `config` | Move concepts only. Replace generator package location, old schema names, and generated-module import model. |
| C | Top-level historical analysis exports | `analysis_exports/*` | Reference CSV/JSON exports for Sanz19, CX-01, CZ-01, and Pareto comparisons. | External example data or thesis archive | Keep outside package source. Future examples should declare data download or fixture policy. |
| C | LaTeX/report material | `latex/*`, `report4memory/*`, root `docs/alpha_*` analysis docs | Thesis narrative and historical design record. | Thesis archive and migration background | Cite as background only. Do not copy narrative constraints into API design unless still scientifically justified. |
| B | Analyzer unit and integration tests | `Verfeinert/tests/analyzer/*`, relevant `Verfeinert/tests/integration/run_*analyzer*`, plot/reporting smokes | Validate structural cost, Pareto, expressibility, trainability, staging, writer, pipeline, reporting, and safety behavior. | `Verfeinertv2/tests` | Port as schema-first tests with tiny deterministic fixtures. Keep QNode tests explicit and opt-in where heavy dependencies are required. |
| C | Legacy Behave features | `Verfeinert/tests/legacy_imported/features/*analysis*`, root `tests/features/*analysis*` | Historical Alpha/Beta acceptance behavior. | Migration reference only | Translate selected behavior into focused unittest/pytest tests. Do not preserve Behave structure by default. |
| D | Cache/build artifacts | `__pycache__`, `.pyc`, egg-info/build/cache artifacts, temporary smoke outputs | Interpreter/build/test output. | None | Exclude from migration and repository extraction. |
| D | Generated result/callable packages as source | `Verfeinert/tmp/*`, `python/analysis/outputs_alpha/*/*_ansatzes.py`, generated `analysis_results` packages | Run artifacts and generated Python. | External data/output roots only | Never treat generated outputs as framework source. |
| D | Non-Verfeinert exploratory notebooks | `python/molecularproblem.ipynb`, `python/training-001.ipynb`, `python/analysis/vqe_analysis.ipynb`, unrelated VQE/molecular scratch material | Exploratory work outside the ansatz analyzer framework scope. | None | Exclude from Verfeinertv2 migration. |

## Workflow Findings

### Input Handling

Current analyzer inputs are mostly staged metadata tables, generated callable
modules, imported metric CSVs, and campaign-specific result tables. Future
input must be canonical Candidate JSON or canonical StagedPackage JSON. Loading
generated callables must remain optional and must not happen during structural
or classification analysis.

### Output Handling

Current outputs are spread across `tmp/`, `outputs`, `analysis_exports`,
`analysis_results`, `python/analysis/analysis_results`, and
`Thesis_Data_Processing/*_outputs`. Future analyzer output roots must be
caller-provided, validated through `verfeinert.core`, and separated from
package source and input roots. The primary output is AnalysisResult JSON;
CSV, Markdown, figures, and manifests are derived artifacts.

### Plotting And Visualization

Plotting is mixed into reporting helpers and thesis notebooks. The scientific
computation should be extracted first. Visualization should be deferred to a
dedicated `verfeinert.ansatz_analyzer.visualization` layer with centralized
style, objective-axis conventions, annotation policies, and export formats.
No metric implementation should import Matplotlib.

### Tests And Validation

The current analyzer tests are valuable as behavior references. The future
test suite should start with schema validation, structural cost fixtures,
Pareto/ranking fixtures, and no-QNode boundary tests. Full expressibility and
trainability tests should use tiny deterministic callables and explicit opt-in
execution flags.

## First Migration Signal

Implement first:

- canonical Candidate JSON ingestion;
- internal AnalysisResult model;
- structural cost on canonical operations;
- AnalysisResult JSON writing and schema validation;
- pure Pareto classification and ranking over AnalysisResult collections.

Defer:

- full expensive metric execution;
- visualization APIs;
- Parquet export;
- notebook conversion;
- thesis figure reproduction.

Open decisions:

- final metric identifier naming;
- uncertainty/error payload shape for metric records;
- visualization style API;
- ranking policy configuration shape;
- whether heavy analyzer dependencies are core runtime dependencies or
  optional extras.
