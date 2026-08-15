"""Public workflow runner composing generator, analyzer, and evolver APIs."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from verfeinert.ansatz_analyzer import (
    AnalysisPipeline,
    AnalysisResultCollection,
    AnalyzerConfig,
    ComparisonResult,
    ComparisonSource,
    ParetoConfig,
    RankingConfig,
    compare_analysis_collections,
    compute_pareto_classifications,
    rank_analysis_results,
    read_comparison_result_json,
    validate_analysis_result_document,
    validate_candidate_document,
    validate_comparison_result_document,
    validate_staged_package_document,
    write_analysis_result_json,
)
from verfeinert.ansatz_analyzer.tables import (
    write_analysis_results_csv,
    write_comparison_csv,
    write_comparison_json,
    write_pareto_csv,
    write_pareto_json,
    write_ranking_csv,
    write_ranking_json,
)
from verfeinert.ansatz_evolver import (
    AnalysisResultRef,
    CandidateRef,
    EvolutionEvent,
    EvolutionRunState,
    GenerationRecord,
    produce_candidate_from_request,
    read_evolution_run_json,
    write_evolution_run_json,
)
from verfeinert.ansatz_evolver.evaluation import ingest_analysis_results
from verfeinert.ansatz_evolver.mutation import (
    MutationPolicy,
    MutationRecipe,
    expand_mutation_requests,
)
from verfeinert.ansatz_evolver.population import deduplicate_candidate_refs
from verfeinert.ansatz_evolver.selection import (
    ObjectiveSpec,
    ThresholdRule,
    select_by_fitness,
    select_by_thresholds,
    select_pareto_front,
    select_strict_pareto,
    select_strict_pareto_feedback,
)
from verfeinert.ansatz_generator import (
    CandidateJsonExportConfig,
    StagedPackageJsonExportConfig,
    build_sanz19_candidate_records,
    write_canonical_staged_package_json,
    write_staged_package_json,
)
from verfeinert.core.hashing import hash_file, stable_hash
from verfeinert.core.io import ensure_output_root, read_json
from verfeinert.core.io.serialization import to_json_safe

from .config import WorkflowConfig, WorkflowConfigError
from .provenance import workflow_provenance


EVOLUTION_FINGERPRINT_VERSION = "verfeinert.workflow.evolution_fingerprint.v1"
ANALYSIS_REUSE_FINGERPRINT_VERSION = "verfeinert.workflow.analysis_reuse_fingerprint.v1"


@dataclass(frozen=True)
class WorkflowResult:
    """Artifact manifest returned by a workflow run."""

    run_id: str
    output_root: Path
    run_root: Path
    candidate_paths: tuple[Path, ...] = ()
    staged_package_path: Path | None = None
    analysis_result_paths: tuple[Path, ...] = ()
    evolution_run_path: Path | None = None
    ranking_json_path: Path | None = None
    ranking_csv_path: Path | None = None
    pareto_json_path: Path | None = None
    pareto_csv_path: Path | None = None
    analysis_csv_path: Path | None = None
    comparison_json_paths: tuple[Path, ...] = ()
    comparison_csv_paths: tuple[Path, ...] = ()
    visualization_paths: tuple[Path, ...] = ()
    candidate_ids: tuple[str, ...] = ()
    analysis_result_ids: tuple[str, ...] = ()
    survivor_candidate_ids: tuple[str, ...] = ()
    rejected_candidate_ids: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    provenance: dict[str, Any] = field(default_factory=dict)
    generation_record: GenerationRecord | None = None
    requested_operations: dict[str, tuple[str, ...]] = field(default_factory=dict)
    executed_operations: tuple[str, ...] = ()
    consumed_artifacts: tuple[dict[str, Any], ...] = ()
    produced_artifacts: tuple[dict[str, Any], ...] = ()
    reused_artifacts: tuple[dict[str, Any], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe manifest for examples and tests."""
        return to_json_safe(
            {
                "schema_version": "verfeinert.workflow_result.v1",
                "run_id": self.run_id,
                "output_root": str(self.output_root),
                "run_root": str(self.run_root),
                "candidate_paths": [str(path) for path in self.candidate_paths],
                "staged_package_path": (
                    str(self.staged_package_path)
                    if self.staged_package_path is not None
                    else None
                ),
                "analysis_result_paths": [str(path) for path in self.analysis_result_paths],
                "evolution_run_path": (
                    str(self.evolution_run_path)
                    if self.evolution_run_path is not None
                    else None
                ),
                "ranking_json_path": str(self.ranking_json_path) if self.ranking_json_path else None,
                "ranking_csv_path": str(self.ranking_csv_path) if self.ranking_csv_path else None,
                "pareto_json_path": str(self.pareto_json_path) if self.pareto_json_path else None,
                "pareto_csv_path": str(self.pareto_csv_path) if self.pareto_csv_path else None,
                "analysis_csv_path": str(self.analysis_csv_path) if self.analysis_csv_path else None,
                "comparison_json_paths": [str(path) for path in self.comparison_json_paths],
                "comparison_csv_paths": [str(path) for path in self.comparison_csv_paths],
                "visualization_paths": [str(path) for path in self.visualization_paths],
                "candidate_ids": list(self.candidate_ids),
                "analysis_result_ids": list(self.analysis_result_ids),
                "survivor_candidate_ids": list(self.survivor_candidate_ids),
                "rejected_candidate_ids": list(self.rejected_candidate_ids),
                "warnings": list(self.warnings),
                "provenance": self.provenance,
                "generation_record": (
                    self.generation_record.to_dict()
                    if self.generation_record is not None
                    else None
                ),
                "requested_operations": {
                    key: list(value) for key, value in self.requested_operations.items()
                },
                "executed_operations": list(self.executed_operations),
                "consumed_artifacts": list(self.consumed_artifacts),
                "produced_artifacts": list(self.produced_artifacts),
                "reused_artifacts": list(self.reused_artifacts),
            },
        )


@dataclass(frozen=True)
class _CandidateArtifact:
    document: dict[str, Any]
    uri: str | None = None


@dataclass(frozen=True)
class _AnalysisResultArtifact:
    document: dict[str, Any]
    uri: str | None = None


@dataclass(frozen=True)
class _AnalysisRunOutput:
    documents: tuple[dict[str, Any], ...]
    paths: tuple[Path, ...] = ()
    generated_paths: tuple[Path, ...] = ()


class WorkflowRunner:
    """Coordinate JSON-first Verfeinert workflows through public APIs."""

    def __init__(self, config: WorkflowConfig | Mapping[str, Any]):
        self.config = (
            config
            if isinstance(config, WorkflowConfig)
            else WorkflowConfig.from_mapping(config)
        )

    def run(
        self,
        *,
        candidate_records: Sequence[Mapping[str, Any] | Any] | None = None,
        metric_callables: Mapping[str, Any] | None = None,
        reference_analysis_results: Sequence[Mapping[str, Any]] = (),
        candidate_sources: Sequence[str | Path | Mapping[str, Any]] = (),
        staged_package_sources: Sequence[str | Path | Mapping[str, Any]] = (),
        analysis_result_sources: Sequence[str | Path | Mapping[str, Any]] = (),
        evolution_run_source: str | Path | Mapping[str, Any] | None = None,
        candidate_factory: Any | None = None,
    ) -> WorkflowResult:
        """Run only the requested workflow operations over compatible artifacts."""
        config = self.config
        output_root = ensure_output_root(config.output_root, input_roots=config.input_roots)
        run_root = output_root / config.run_id
        package_output_root = run_root / "candidates"
        analysis_root = run_root / "analysis"
        evolution_root = run_root / "evolution"
        derived_root = run_root / "derived_outputs"

        requested_scientific = config.scientific_execution
        requested_postprocessing = config.postprocessing
        executed: list[str] = []
        warnings: list[str] = []
        produced_artifacts: list[dict[str, Any]] = []
        consumed_artifacts: list[dict[str, Any]] = []
        reused_artifacts: list[dict[str, Any]] = []

        configured = config.artifacts
        all_candidate_sources = (*configured.candidates, *tuple(candidate_sources))
        all_staged_sources = (*configured.staged_packages, *tuple(staged_package_sources))
        all_analysis_sources = (*configured.analysis_results, *tuple(analysis_result_sources))
        all_comparison_result_sources = configured.comparison_results
        resolved_evolution_source = (
            evolution_run_source
            if evolution_run_source is not None
            else configured.evolution_run
        )

        candidate_artifacts = _load_candidate_artifacts(all_candidate_sources)
        staged_artifacts = _load_staged_package_artifacts(all_staged_sources)
        candidate_artifacts.extend(_candidate_artifacts_from_staged_packages(staged_artifacts))
        for artifact in candidate_artifacts:
            consumed_artifacts.append(_artifact_record("candidate", artifact.uri))
        for package in staged_artifacts:
            consumed_artifacts.append(_artifact_record("staged_package", package["uri"]))
        loaded_comparison_results = _load_comparison_results(all_comparison_result_sources)
        for source, result in zip(
            all_comparison_result_sources,
            loaded_comparison_results,
            strict=True,
        ):
            record = _artifact_record(
                "comparison_result",
                _source_uri(source),
                document_id=result.comparison_id,
            )
            consumed_artifacts.append(record)
            reused_artifacts.append(record)

        generated_package = None
        if "generate" in requested_scientific:
            records = tuple(candidate_records) if candidate_records is not None else tuple(self._generate_records())
            if not records:
                raise WorkflowConfigError("Workflow generation produced no candidate records.")
            generated_package = write_staged_package_json(
                records,
                config=self._staged_package_config(package_output_root),
            )
            if generated_package.package_root is None or generated_package.staged_package_path is None:
                raise RuntimeError("Staged package exporter did not return paths.")
            executed.append("generate")
            produced_artifacts.extend(
                _staged_package_records(
                    generated_package.staged_package_path,
                    generated_package.candidate_paths,
                ),
            )
            candidate_artifacts = [
                _CandidateArtifact(document, str(path))
                for document, path in zip(
                    generated_package.candidates,
                    generated_package.candidate_paths,
                    strict=True,
                )
            ]
            staged_artifacts = [
                {
                    "document": generated_package.package,
                    "uri": str(generated_package.staged_package_path),
                }
            ]
        elif candidate_records is not None:
            raise WorkflowConfigError("candidate_records require the generate operation.")

        analysis_result_paths: tuple[Path, ...] = ()
        analysis_collection: AnalysisResultCollection | None = None
        if "analyze" in requested_scientific:
            analysis_sources_for_pipeline = _analysis_input_sources(
                generated_package=generated_package,
                candidate_sources=all_candidate_sources,
                staged_package_sources=all_staged_sources,
            )
            if not analysis_sources_for_pipeline:
                raise WorkflowConfigError("requested analysis has no Candidate/StagedPackage input.")
            analyzer_config = self._analyzer_config(
                _input_roots_for_sources(analysis_sources_for_pipeline, fallback=config.input_roots),
                analysis_root,
            )
            analysis_run = self._run_analysis(
                candidates=tuple(artifact.document for artifact in candidate_artifacts),
                input_sources=analysis_sources_for_pipeline,
                analyzer_config=analyzer_config,
                metric_callables=metric_callables,
                package_output_root=package_output_root,
                package_id=f"{config.run_id}-analysis-reuse-miss-package",
                reuse_artifacts=(
                    _load_analysis_result_artifacts(all_analysis_sources)
                    if _analysis_result_reuse_enabled(config)
                    else ()
                ),
                consumed_artifacts=consumed_artifacts,
                reused_artifacts=reused_artifacts,
                produced_artifacts=produced_artifacts,
            )
            analysis_result_paths = analysis_run.paths
            analysis_collection = AnalysisResultCollection.from_records(
                analysis_run.documents,
                collection_id=f"{config.run_id}:analysis",
            )
            executed.append("analyze")
        elif all_analysis_sources:
            analysis_collection = AnalysisResultCollection.from_sources(
                all_analysis_sources,
                collection_id=f"{config.run_id}:analysis",
            )
            consumed = _analysis_source_records(all_analysis_sources)
            consumed_artifacts.extend(consumed)
            reused_artifacts.extend(consumed)

        evolution_path: Path | None = None
        generation_record: GenerationRecord | None = None
        survivor_candidate_ids: tuple[str, ...] = ()
        rejected_candidate_ids: tuple[str, ...] = ()
        if "evolve" in requested_scientific:
            if config.campaign_type == "individual":
                raise WorkflowConfigError("individual campaigns must not execute evolution.")
            state, generated_during_evolution = self._run_evolution(
                analysis_collection=analysis_collection,
                candidate_artifacts=candidate_artifacts,
                evolution_source=resolved_evolution_source,
                candidate_factory=candidate_factory,
                reference_analysis_results=reference_analysis_results,
                analysis_result_paths=analysis_result_paths,
                analysis_reuse_artifacts=(
                    _load_analysis_result_artifacts(all_analysis_sources)
                    if _analysis_result_reuse_enabled(config)
                    else ()
                ),
                analysis_root=analysis_root,
                package_output_root=package_output_root,
                consumed_artifacts=consumed_artifacts,
                reused_artifacts=reused_artifacts,
                executed=executed,
                produced_artifacts=produced_artifacts,
            )
            evolution_path = write_evolution_run_json(
                state,
                output_root=evolution_root,
                input_roots=_evolution_input_roots(config, generated_during_evolution, analysis_root),
            )
            produced_artifacts.append(_artifact_record("evolution_run", str(evolution_path)))
            generation_record = state.generations[-1] if state.generations else None
            survivor_candidate_ids = (
                tuple(ref.candidate_id for ref in generation_record.survivor_refs)
                if generation_record is not None
                else ()
            )
            rejected_candidate_ids = (
                tuple(ref.candidate_id for ref in generation_record.rejected_refs)
                if generation_record is not None
                else ()
            )
            if "evolve" not in executed:
                executed.append("evolve")
        elif resolved_evolution_source is not None:
            consumed_artifacts.append(_artifact_record("evolution_run", _source_uri(resolved_evolution_source)))
            reused_artifacts.append(_artifact_record("evolution_run", _source_uri(resolved_evolution_source)))

        if _needs_analysis_collection(requested_postprocessing) and analysis_collection is None:
            if all_analysis_sources:
                analysis_collection = AnalysisResultCollection.from_sources(
                    all_analysis_sources,
                    collection_id=f"{config.run_id}:analysis",
                )
            else:
                raise WorkflowConfigError("requested postprocessing has no AnalysisResult input.")

        ranking_json_path: Path | None = None
        ranking_csv_path: Path | None = None
        pareto_json_path: Path | None = None
        pareto_csv_path: Path | None = None
        analysis_csv_path: Path | None = None
        comparison_json_paths: list[Path] = []
        comparison_csv_paths: list[Path] = []
        visualization_paths: list[Path] = []
        ranking_result = None
        pareto_result = None
        computed_comparison_results: list[ComparisonResult] = []
        if "ranking" in requested_postprocessing:
            collection = _require_collection(analysis_collection)
            ranking_config = config.analyzer.ranking or RankingConfig(
                score_components={"cost.structural_cost": 1.0},
                combination="weighted_sum",
                ascending=True,
            )
            ranking_result = rank_analysis_results(collection, config=ranking_config)
            if not ranking_result.ranked_candidate_ids and len(collection):
                raise WorkflowConfigError(
                    "requested ranking metric is missing or unavailable: "
                    + "; ".join(ranking_result.warnings),
                )
            ranking_json = write_ranking_json(
                ranking_result,
                output_root=derived_root,
                run_id=config.run_id,
                input_roots=_postprocessing_input_roots(config, analysis_result_paths, all_analysis_sources),
            )
            ranking_csv = write_ranking_csv(
                ranking_result,
                output_root=derived_root,
                run_id=config.run_id,
                input_roots=_postprocessing_input_roots(config, analysis_result_paths, all_analysis_sources),
            )
            ranking_json_path = ranking_json.path
            ranking_csv_path = ranking_csv.path
            warnings.extend(ranking_result.warnings)
            executed.append("ranking")
            produced_artifacts.extend([ranking_json.to_dict(), ranking_csv.to_dict()])
        if "pareto" in requested_postprocessing:
            collection = _require_collection(analysis_collection)
            pareto_config = config.analyzer.pareto or ParetoConfig()
            pareto_result = compute_pareto_classifications(collection, config=pareto_config)
            if not pareto_result.frontier_candidate_ids and len(collection) and pareto_result.warnings:
                raise WorkflowConfigError(
                    "requested Pareto objective is missing or unavailable: "
                    + "; ".join(pareto_result.warnings),
                )
            pareto_json = write_pareto_json(
                pareto_result,
                output_root=derived_root,
                run_id=config.run_id,
                input_roots=_postprocessing_input_roots(config, analysis_result_paths, all_analysis_sources),
            )
            pareto_json_path = pareto_json.path
            produced_artifacts.append(pareto_json.to_dict())
            warnings.extend(pareto_result.warnings)
            executed.append("pareto")
            if "export_csv" in requested_postprocessing:
                pareto_csv = write_pareto_csv(
                    pareto_result,
                    output_root=derived_root,
                    run_id=config.run_id,
                    input_roots=_postprocessing_input_roots(config, analysis_result_paths, all_analysis_sources),
                )
                pareto_csv_path = pareto_csv.path
                produced_artifacts.append(pareto_csv.to_dict())
        if "comparison" in requested_postprocessing:
            if not config.comparisons:
                raise WorkflowConfigError("requested comparison requires explicit comparison sources.")
            for comparison_config in config.comparisons:
                sources = tuple(
                    ComparisonSource.from_sources(
                        source.source_id,
                        source.analysis_results,
                        role=source.role,
                        label=source.label,
                        metadata=source.metadata,
                    )
                    for source in comparison_config.sources
                )
                comparison = compare_analysis_collections(
                    sources,
                    config=comparison_config.config,
                )
                computed_comparison_results.append(comparison)
                comparison_json = write_comparison_json(
                    comparison,
                    output_root=derived_root,
                    run_id=config.run_id,
                    input_roots=_comparison_input_roots(config, comparison_config),
                )
                comparison_json_paths.append(comparison_json.path)
                produced_artifacts.append(comparison_json.to_dict())
                if "export_csv" in requested_postprocessing:
                    comparison_csv = write_comparison_csv(
                        comparison,
                        output_root=derived_root,
                        run_id=config.run_id,
                        input_roots=_comparison_input_roots(config, comparison_config),
                    )
                    comparison_csv_paths.append(comparison_csv.path)
                    produced_artifacts.append(comparison_csv.to_dict())
            executed.append("comparison")
        if "export_csv" in requested_postprocessing:
            if loaded_comparison_results and "comparison" not in requested_postprocessing:
                for comparison in loaded_comparison_results:
                    comparison_csv = write_comparison_csv(
                        comparison,
                        output_root=derived_root,
                        run_id=config.run_id,
                        input_roots=_comparison_result_input_roots(config, all_comparison_result_sources),
                    )
                    comparison_csv_paths.append(comparison_csv.path)
                    produced_artifacts.append(comparison_csv.to_dict())
            elif (
                "ranking" not in requested_postprocessing
                and "pareto" not in requested_postprocessing
                and "comparison" not in requested_postprocessing
            ):
                collection = _require_collection(analysis_collection)
                analysis_csv = write_analysis_results_csv(
                    collection,
                    output_root=derived_root,
                    run_id=config.run_id,
                    input_roots=_postprocessing_input_roots(config, analysis_result_paths, all_analysis_sources),
                )
                analysis_csv_path = analysis_csv.path
                produced_artifacts.append(analysis_csv.to_dict())
            executed.append("export_csv")
        if "visualization" in requested_postprocessing:
            visualization_paths.extend(
                _write_requested_visualizations(
                    config=config,
                    derived_root=derived_root,
                    analysis_collection=analysis_collection,
                    ranking_result=ranking_result,
                    pareto_result=pareto_result,
                    comparison_results=(
                        tuple(computed_comparison_results)
                        or tuple(loaded_comparison_results)
                    ),
                    evolution_source=evolution_path or resolved_evolution_source,
                    input_roots=_postprocessing_input_roots(config, analysis_result_paths, all_analysis_sources),
                ),
            )
            produced_artifacts.extend(_path_records("figure", visualization_paths))
            executed.append("visualization")

        candidate_ids = tuple(
            dict.fromkeys(
                [artifact.document["candidate_id"] for artifact in candidate_artifacts]
                + [candidate["candidate_id"] for package in staged_artifacts for candidate in package["document"]["candidates"]]
            ),
        )
        if analysis_collection is not None:
            analysis_result_ids = analysis_collection.analysis_result_ids
            if not candidate_ids:
                candidate_ids = analysis_collection.candidate_ids
        else:
            analysis_result_ids = ()

        provenance = workflow_provenance(
            run_id=config.run_id,
            config_snapshot=config.to_dict(),
            created_at=config.created_at,
            git_commit=None,
            execution_flags={
                "workflow_entry_point": _entry_point(
                    generated="generate" in executed,
                    candidates=bool(all_candidate_sources),
                    staged_packages=bool(all_staged_sources),
                    analysis_results=bool(all_analysis_sources),
                    comparison_results=bool(all_comparison_result_sources),
                    evolution_run=resolved_evolution_source is not None,
                ),
                "campaign_type": config.campaign_type,
                "requested_scientific_execution": list(requested_scientific),
                "requested_postprocessing": list(requested_postprocessing),
                "executed_operations": list(dict.fromkeys(executed)),
                "reused_artifact_count": len(reused_artifacts),
                "candidate_generation_executed": "generate" in executed,
                "analysis_executed": "analyze" in executed,
                "evolution_exported": evolution_path is not None,
                "ranking_executed": ranking_json_path is not None,
                "pareto_executed": pareto_json_path is not None,
                "comparison_executed": bool(comparison_json_paths),
                "visualization_executed": bool(visualization_paths),
                "csv_exported": any(
                    path is not None
                    for path in (ranking_csv_path, pareto_csv_path, analysis_csv_path)
                ) or bool(comparison_csv_paths),
                "figure_exported": bool(visualization_paths),
                "qnodes_executed_by_runner": False,
            },
        )
        provenance["artifacts"] = {
            "consumed": list(consumed_artifacts),
            "produced": list(produced_artifacts),
            "reused": list(reused_artifacts),
        }
        return WorkflowResult(
            run_id=config.run_id,
            output_root=output_root,
            run_root=run_root,
            candidate_paths=(
                tuple(generated_package.candidate_paths)
                if generated_package is not None
                else ()
            ),
            staged_package_path=(
                generated_package.staged_package_path
                if generated_package is not None
                else None
            ),
            analysis_result_paths=analysis_result_paths,
            evolution_run_path=evolution_path,
            ranking_json_path=ranking_json_path,
            ranking_csv_path=ranking_csv_path,
            pareto_json_path=pareto_json_path,
            pareto_csv_path=pareto_csv_path,
            analysis_csv_path=analysis_csv_path,
            comparison_json_paths=tuple(comparison_json_paths),
            comparison_csv_paths=tuple(comparison_csv_paths),
            visualization_paths=tuple(visualization_paths),
            candidate_ids=candidate_ids,
            analysis_result_ids=analysis_result_ids,
            survivor_candidate_ids=survivor_candidate_ids,
            rejected_candidate_ids=rejected_candidate_ids,
            warnings=tuple(dict.fromkeys(warnings)),
            provenance=provenance,
            generation_record=generation_record,
            requested_operations={
                "scientific_execution": requested_scientific,
                "postprocessing": requested_postprocessing,
            },
            executed_operations=tuple(dict.fromkeys(executed)),
            consumed_artifacts=tuple(consumed_artifacts),
            produced_artifacts=tuple(produced_artifacts),
            reused_artifacts=tuple(reused_artifacts),
        )

    def _generate_records(self) -> list[dict[str, Any]]:
        generation = self.config.generation
        if generation.family == "provided":
            raise WorkflowConfigError("provided generation requires candidate_records.")
        return build_sanz19_candidate_records(
            generation.template_ids,
            generation.layers,
            n_qubits=generation.n_qubits,
        )

    def _staged_package_config(self, output_root: Path) -> StagedPackageJsonExportConfig:
        config = self.config
        generation = config.generation
        package_id = generation.package_id or f"{config.run_id}-candidate-package"
        candidate_export = CandidateJsonExportConfig(
            candidate_id_prefix=generation.candidate_id_prefix,
            n_qubits=generation.n_qubits,
            created_at=generation.created_at or config.created_at,
            source_label=generation.source_label,
            git_commit=None,
            discover_git_commit=False,
            metadata={
                "workflow_run_id": config.run_id,
                **dict(generation.metadata),
            },
        )
        return StagedPackageJsonExportConfig(
            package_id=package_id,
            output_root=output_root,
            candidate_export=candidate_export,
            created_at=generation.created_at or config.created_at,
            producer="verfeinert.workflow",
            git_commit=None,
            discover_git_commit=False,
            input_roots=config.input_roots,
            metadata={
                "workflow_run_id": config.run_id,
                **dict(generation.metadata),
            },
        )

    def _canonical_staged_package_config(
        self,
        output_root: Path,
        *,
        package_id: str,
    ) -> StagedPackageJsonExportConfig:
        config = self.config
        return StagedPackageJsonExportConfig(
            package_id=package_id,
            output_root=output_root,
            candidate_export=CandidateJsonExportConfig(
                created_at=config.created_at,
                source_label="verfeinert.workflow",
                git_commit=None,
                discover_git_commit=False,
            ),
            created_at=config.created_at,
            producer="verfeinert.workflow",
            git_commit=None,
            discover_git_commit=False,
            input_roots=config.input_roots,
            metadata={"workflow_run_id": config.run_id},
        )

    def _analyzer_config(
        self,
        input_roots: Sequence[str | Path],
        analysis_root: Path,
    ) -> AnalyzerConfig:
        config = self.config
        return AnalyzerConfig(
            run_id=config.run_id,
            input_roots=tuple(input_roots),
            output_root=analysis_root,
            selected_metrics=config.analyzer.selected_metrics,
            execution=config.execution,
            permissions=config.analyzer.permissions,
            random_seed=config.analyzer.random_seed if config.analyzer.random_seed is not None else config.random_seed,
            structural_cost=config.analyzer.structural_cost,
            metric_configs=config.analyzer.metric_configs,
            materialization=config.analyzer.materialization,
        )

    def _run_analysis(
        self,
        *,
        candidates: Sequence[Mapping[str, Any]],
        input_sources: Sequence[str | Path | Mapping[str, Any]],
        analyzer_config: AnalyzerConfig,
        metric_callables: Mapping[str, Any] | None,
        package_output_root: Path,
        package_id: str,
        reuse_artifacts: Sequence[_AnalysisResultArtifact],
        consumed_artifacts: list[dict[str, Any]],
        reused_artifacts: list[dict[str, Any]],
        produced_artifacts: list[dict[str, Any]],
    ) -> _AnalysisRunOutput:
        if not _analysis_result_reuse_enabled(self.config):
            paths: list[Path] = []
            pipeline = AnalysisPipeline(analyzer_config)
            for source in input_sources:
                paths.extend(
                    pipeline.run_and_write(
                        source,
                        metric_callables=metric_callables,
                    ),
                )
            produced_artifacts.extend(_path_records("analysis_result", paths))
            return _AnalysisRunOutput(
                documents=tuple(validate_analysis_result_document(read_json(path)) for path in paths),
                paths=tuple(paths),
            )

        fingerprint = _analysis_config_fingerprint(analyzer_config)
        ordered_candidates = tuple(validate_candidate_document(candidate) for candidate in candidates)
        result_by_candidate_id: dict[str, dict[str, Any]] = {}
        paths_by_analysis_result_id: dict[str, Path] = {}
        misses: list[dict[str, Any]] = []
        for candidate in ordered_candidates:
            artifact = _matching_analysis_artifact(candidate, reuse_artifacts, fingerprint)
            if artifact is None:
                misses.append(candidate)
                continue
            document = artifact.document
            result_by_candidate_id[candidate["candidate_id"]] = document
            if artifact.uri is not None:
                paths_by_analysis_result_id[document["analysis_result_id"]] = Path(artifact.uri).expanduser()
            record = _artifact_record("analysis_result", artifact.uri, document_id=document["analysis_result_id"])
            consumed_artifacts.append(record)
            reused_artifacts.append(record)

        generated_paths: list[Path] = []
        if misses:
            package = write_canonical_staged_package_json(
                misses,
                config=self._canonical_staged_package_config(
                    package_output_root,
                    package_id=package_id,
                ),
            )
            if package.package_root is None or package.staged_package_path is None:
                raise RuntimeError("Canonical staged package exporter did not return paths.")
            generated_paths.extend((package.package_root, package.staged_package_path, *package.candidate_paths))
            produced_artifacts.extend(
                _staged_package_records(package.staged_package_path, package.candidate_paths),
            )
            miss_config = _analyzer_config_for_input_root(analyzer_config, package.package_root)
            pipeline = AnalysisPipeline(miss_config)
            for record in pipeline.run(package.staged_package_path, metric_callables=metric_callables):
                document = _analysis_document_with_fingerprint(record.to_dict(), fingerprint)
                path = write_analysis_result_json(document, miss_config)
                produced_artifacts.append(_artifact_record("analysis_result", str(path)))
                result_by_candidate_id[document["candidate_ref"]["candidate_id"]] = document
                paths_by_analysis_result_id[document["analysis_result_id"]] = path

        documents = tuple(result_by_candidate_id[candidate["candidate_id"]] for candidate in ordered_candidates)
        paths = tuple(
            paths_by_analysis_result_id[document["analysis_result_id"]]
            for document in documents
            if document["analysis_result_id"] in paths_by_analysis_result_id
        )
        return _AnalysisRunOutput(
            documents=documents,
            paths=paths,
            generated_paths=tuple(generated_paths),
        )

    def _run_evolution(
        self,
        *,
        analysis_collection: AnalysisResultCollection | None,
        candidate_artifacts: Sequence[_CandidateArtifact],
        evolution_source: str | Path | Mapping[str, Any] | None,
        candidate_factory: Any | None,
        reference_analysis_results: Sequence[Mapping[str, Any]],
        analysis_result_paths: Sequence[Path],
        analysis_reuse_artifacts: Sequence[_AnalysisResultArtifact],
        analysis_root: Path,
        package_output_root: Path,
        consumed_artifacts: list[dict[str, Any]],
        reused_artifacts: list[dict[str, Any]],
        executed: list[str],
        produced_artifacts: list[dict[str, Any]],
    ) -> tuple[EvolutionRunState, tuple[Path, ...]]:
        config = self.config
        generated_paths: list[Path] = []
        candidate_lookup = {
            artifact.document["candidate_id"]: artifact.document
            for artifact in candidate_artifacts
        }
        candidate_uri_lookup = {
            artifact.document["candidate_id"]: artifact.uri
            for artifact in candidate_artifacts
            if artifact.uri is not None
        }
        analysis_by_candidate_id: dict[str, dict[str, Any]] = {}
        if analysis_collection is not None:
            analysis_by_candidate_id.update(
                {
                    document["candidate_ref"]["candidate_id"]: document
                    for document in analysis_collection.documents
                },
            )

        if evolution_source is not None:
            document, source_path = _evolution_document_with_path(evolution_source)
            consumed_artifacts.append(_artifact_record("evolution_run", _source_uri(evolution_source)))
            reused_artifacts.append(_artifact_record("evolution_run", _source_uri(evolution_source)))
            state = _state_from_evolution_document(document)
            candidate_lookup.update(_candidate_documents_from_state(state, source_path=source_path))
            analysis_by_candidate_id.update(
                _analysis_result_documents_from_state(state, source_path=source_path),
            )
            state = _state_for_resume_or_branch(
                state,
                document=document,
                source_path=source_path,
                config=config,
            )
        else:
            collection = _require_collection(analysis_collection)
            candidate_refs = _candidate_refs_for_collection(
                collection,
                candidate_artifacts=candidate_artifacts,
                uri_by_candidate_id=candidate_uri_lookup,
            )
            selection = self._select(collection, reference_analysis_results)
            analysis_by_candidate_id.update(
                {
                    document["candidate_ref"]["candidate_id"]: document
                    for document in collection.documents
                },
            )
            generation = _generation_record(
                generation_index=0,
                candidate_refs=candidate_refs,
                collection=collection,
                selection=selection,
                analysis_uris=(
                    _analysis_uri_map(analysis_result_paths)
                    if analysis_result_paths
                    else _analysis_uri_map_from_collection(collection)
                ),
                parent_refs=(),
                run_id=config.run_id,
            )
            state = _new_evolution_state(
                config=config,
                evolution_run_id=f"{config.run_id}-evolution",
                generations=(generation,),
                relationship={"type": "origin"},
            )

        while _should_extend_evolution(config, state, candidate_factory):
            next_generation = state.generations[-1].generation_index + 1
            parent_refs = _parent_refs_for_next_generation(config, state, next_generation)
            if not parent_refs:
                raise WorkflowConfigError("invalid resume state: latest generation has no parent candidates.")
            policy = _mutation_policy_for_generation(config, next_generation)
            requests = expand_mutation_requests(
                parent_refs,
                generation_index=next_generation,
                policy=policy,
                parent_candidates=candidate_lookup,
            )
            children = []
            for request in requests:
                parent = candidate_lookup.get(request.parent_candidate_id)
                if parent is None:
                    raise WorkflowConfigError(
                        "unresolved artifact reference for evolution parent: "
                        f"{request.parent_candidate_id}",
                    )
                child = produce_candidate_from_request(request, parent, candidate_factory)
                children.append(child)
            children, dedup_report = _deduplicate_offspring(children, config.evolver.offspring_deduplication)
            package = write_canonical_staged_package_json(
                children,
                config=self._canonical_staged_package_config(
                    package_output_root,
                    package_id=f"{config.run_id}-g{next_generation:03d}-candidate-package",
                ),
            )
            if package.package_root is None or package.staged_package_path is None:
                raise RuntimeError("Canonical staged package exporter did not return paths.")
            generated_paths.extend((package.package_root, package.staged_package_path, *package.candidate_paths))
            produced_artifacts.extend(
                _staged_package_records(package.staged_package_path, package.candidate_paths),
            )
            for candidate, path in zip(package.candidates, package.candidate_paths, strict=True):
                candidate_uri_lookup[candidate["candidate_id"]] = str(path)
                candidate_lookup[candidate["candidate_id"]] = candidate

            analyzer_config = self._analyzer_config((package.package_root,), analysis_root)
            analysis_run = self._run_analysis(
                candidates=tuple(package.candidates),
                input_sources=(package.staged_package_path,),
                analyzer_config=analyzer_config,
                metric_callables=None,
                package_output_root=package_output_root,
                package_id=f"{config.run_id}-g{next_generation:03d}-analysis-reuse-miss-package",
                reuse_artifacts=(
                    *tuple(analysis_reuse_artifacts),
                    *tuple(_AnalysisResultArtifact(document) for document in analysis_by_candidate_id.values()),
                ),
                consumed_artifacts=consumed_artifacts,
                reused_artifacts=reused_artifacts,
                produced_artifacts=produced_artifacts,
            )
            analysis_paths = analysis_run.paths
            generated_paths.extend(analysis_run.generated_paths)
            if "analyze" not in executed:
                executed.append("analyze")
            child_collection = AnalysisResultCollection.from_records(
                analysis_run.documents,
                collection_id=f"{config.run_id}:g{next_generation:03d}:analysis",
            )
            selection = self._select(
                child_collection,
                _selection_reference_results(
                    config,
                    state,
                    analysis_by_candidate_id,
                    reference_analysis_results,
                ),
            )
            analysis_by_candidate_id.update(
                {
                    document["candidate_ref"]["candidate_id"]: document
                    for document in child_collection.documents
                },
            )
            child_refs = tuple(
                CandidateRef.from_candidate_document(candidate, candidate_uri=candidate_uri_lookup.get(candidate["candidate_id"]))
                for candidate in package.candidates
            )
            generation = _generation_record(
                generation_index=next_generation,
                candidate_refs=child_refs,
                collection=child_collection,
                selection=selection,
                analysis_uris=_analysis_uri_map_from_documents(analysis_run.documents, analysis_paths),
                parent_refs=tuple(parent_refs),
                run_id=config.run_id,
                extra_configuration=(
                    {"offspring_deduplication": dedup_report.to_dict()}
                    if dedup_report is not None
                    else None
                ),
                extra_events=(
                    (
                        EvolutionEvent(
                            event_type="workflow_offspring_deduplicated",
                            status="completed",
                            metadata=dedup_report.to_dict(),
                        ),
                    )
                    if dedup_report is not None
                    else ()
                ),
            )
            state = _state_with_generation(config, state, generation)

        return _state_completed(config, state), tuple(generated_paths)

    def _select(
        self,
        collection: AnalysisResultCollection,
        reference_analysis_results: Sequence[Mapping[str, Any]],
    ):
        config = self.config.evolver
        if config.selection_mode == "fitness":
            return select_by_fitness(
                collection.documents,
                metric_name=config.metric_name,
                keep=config.keep,
                direction=config.direction,  # type: ignore[arg-type]
                policy_id=config.policy_id,
            )
        if config.selection_mode == "thresholds":
            rules = tuple(
                ThresholdRule(name=name, threshold=value, direction=config.threshold_direction)  # type: ignore[arg-type]
                for name, value in sorted(config.thresholds.items())
            )
            return select_by_thresholds(collection.documents, rules=rules, policy_id=config.policy_id)
        objectives = tuple(
            ObjectiveSpec(item["name"], item["direction"])  # type: ignore[arg-type]
            for item in config.objectives
        )
        if config.selection_mode == "pareto":
            return select_pareto_front(
                collection.documents,
                objectives=objectives,
                policy_id=config.policy_id,
            )
        if config.selection_mode == "strict_pareto_feedback":
            return select_strict_pareto_feedback(
                collection.documents,
                objectives=objectives,
                reference_results=reference_analysis_results,
                thresholds=config.thresholds,
                threshold_direction=config.threshold_direction,
                strict_ties=config.strict_ties,
                policy_id=config.policy_id,
            )
        return select_strict_pareto(
            collection.documents,
            objectives=objectives,
            reference_results=reference_analysis_results,
            policy_id=config.policy_id,
        )


def _load_candidate_artifacts(
    sources: Sequence[str | Path | Mapping[str, Any]],
) -> list[_CandidateArtifact]:
    artifacts: list[_CandidateArtifact] = []
    for source in sources:
        document, path = _document_with_path(source)
        artifacts.append(
            _CandidateArtifact(
                validate_candidate_document(document),
                str(path) if path is not None else None,
            ),
        )
    return artifacts


def _load_staged_package_artifacts(
    sources: Sequence[str | Path | Mapping[str, Any]],
) -> list[dict[str, Any]]:
    packages: list[dict[str, Any]] = []
    for source in sources:
        document, path = _document_with_path(source)
        package = validate_staged_package_document(document)
        packages.append({"document": package, "uri": str(path) if path is not None else None})
    return packages


def _load_analysis_result_artifacts(
    sources: Sequence[str | Path | Mapping[str, Any]],
) -> tuple[_AnalysisResultArtifact, ...]:
    artifacts: list[_AnalysisResultArtifact] = []
    for source in sources:
        if isinstance(source, Mapping):
            artifacts.append(_AnalysisResultArtifact(validate_analysis_result_document(source)))
            continue
        path = Path(source).expanduser()
        if path.is_dir():
            for child in sorted(path.glob("*.json")):
                artifacts.append(
                    _AnalysisResultArtifact(
                        validate_analysis_result_document(read_json(child)),
                        str(child),
                    ),
                )
            continue
        artifacts.append(
            _AnalysisResultArtifact(
                validate_analysis_result_document(read_json(path)),
                str(path),
            ),
        )
    return tuple(artifacts)


def _candidate_artifacts_from_staged_packages(
    packages: Sequence[Mapping[str, Any]],
) -> list[_CandidateArtifact]:
    artifacts: list[_CandidateArtifact] = []
    for package in packages:
        document = package["document"]
        uri = package.get("uri")
        candidate_uris = _candidate_uris_from_package(
            document,
            Path(uri) if isinstance(uri, str) else None,
        )
        for candidate in document.get("candidates", []):
            validated = validate_candidate_document(candidate)
            artifacts.append(
                _CandidateArtifact(
                    validated,
                    candidate_uris.get(validated["candidate_id"]),
                ),
            )
    return artifacts


def _candidate_uris_from_package(
    package: Mapping[str, Any],
    package_path: Path | None,
) -> dict[str, str]:
    if package_path is None:
        return {}
    package_root = package_path.parent
    uris: dict[str, str] = {}
    candidate_ids = {candidate["candidate_id"] for candidate in package.get("candidates", [])}
    for artifact in package.get("artifacts", []):
        artifact_id = str(artifact.get("artifact_id", ""))
        if not artifact_id.startswith("candidate-"):
            continue
        candidate_id = artifact_id.removeprefix("candidate-")
        if candidate_id not in candidate_ids:
            continue
        path = package_root / str(artifact.get("uri", ""))
        uris[candidate_id] = str(path)
    return uris


def _analysis_input_sources(
    *,
    generated_package,
    candidate_sources: Sequence[str | Path | Mapping[str, Any]],
    staged_package_sources: Sequence[str | Path | Mapping[str, Any]],
) -> tuple[str | Path | Mapping[str, Any], ...]:
    if generated_package is not None:
        return (generated_package.staged_package_path,)
    if staged_package_sources:
        return tuple(staged_package_sources)
    if candidate_sources:
        return tuple(candidate_sources)
    return ()


def _input_roots_for_sources(
    sources: Sequence[str | Path | Mapping[str, Any]],
    *,
    fallback: Sequence[str | Path],
) -> tuple[Path, ...]:
    roots: list[Path] = [Path(root).expanduser() for root in fallback]
    for source in sources:
        if isinstance(source, (str, Path)):
            path = Path(source).expanduser()
            roots.append(path if path.is_dir() else path.parent)
    if not roots:
        roots.append(Path.cwd())
    return tuple(dict.fromkeys(roots))


def _postprocessing_input_roots(
    config: WorkflowConfig,
    analysis_result_paths: Sequence[Path],
    analysis_sources: Sequence[str | Path | Mapping[str, Any]],
) -> tuple[Path, ...]:
    if analysis_result_paths:
        return tuple(dict.fromkeys(path.parent for path in analysis_result_paths))
    return _input_roots_for_sources(analysis_sources, fallback=config.input_roots)


def _evolution_input_roots(
    config: WorkflowConfig,
    generated_paths: Sequence[Path],
    analysis_root: Path,
) -> tuple[Path, ...]:
    roots = [Path(root).expanduser() for root in config.input_roots]
    roots.extend(path if path.is_dir() else path.parent for path in generated_paths)
    if analysis_root.exists():
        roots.append(analysis_root)
    if not roots:
        roots.append(Path.cwd())
    return tuple(dict.fromkeys(roots))


def _document_with_path(source: str | Path | Mapping[str, Any]) -> tuple[dict[str, Any], Path | None]:
    if isinstance(source, Mapping):
        return dict(source), None
    path = Path(source).expanduser()
    payload = read_json(path)
    if not isinstance(payload, Mapping):
        raise WorkflowConfigError(f"artifact source must contain a JSON object: {path}")
    return dict(payload), path


def _evolution_document_with_path(
    source: str | Path | Mapping[str, Any],
) -> tuple[dict[str, Any], Path | None]:
    if isinstance(source, Mapping):
        return dict(source), None
    path = Path(source).expanduser()
    return read_evolution_run_json(path), path


def _source_uri(source: str | Path | Mapping[str, Any] | None) -> str | None:
    if source is None or isinstance(source, Mapping):
        return None
    return str(Path(source).expanduser())


def _analysis_source_records(
    sources: Sequence[str | Path | Mapping[str, Any]],
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for source in sources:
        if isinstance(source, Mapping):
            document = validate_analysis_result_document(source)
            records.append(_artifact_record("analysis_result", None, document_id=document["analysis_result_id"]))
            continue
        path = Path(source).expanduser()
        if path.is_dir():
            records.extend(_path_records("analysis_result", sorted(path.glob("*.json"))))
        else:
            document = validate_analysis_result_document(read_json(path))
            records.append(_artifact_record("analysis_result", str(path), document_id=document["analysis_result_id"]))
    return records


def _load_comparison_results(
    sources: Sequence[str | Path | Mapping[str, Any]],
) -> tuple[ComparisonResult, ...]:
    results: list[ComparisonResult] = []
    for source in sources:
        if isinstance(source, Mapping):
            results.append(ComparisonResult.from_dict(source))
        else:
            results.append(read_comparison_result_json(source))
    return tuple(results)


def _comparison_input_roots(
    config: WorkflowConfig,
    comparison,
) -> tuple[Path, ...]:
    roots: list[Path] = [Path(root).expanduser() for root in config.input_roots]
    for source in comparison.sources:
        roots.extend(
            _input_roots_for_sources(
                source.analysis_results,
                fallback=(),
            ),
        )
    if not roots:
        roots.append(Path.cwd())
    return tuple(dict.fromkeys(roots))


def _comparison_result_input_roots(
    config: WorkflowConfig,
    sources: Sequence[str | Path | Mapping[str, Any]],
) -> tuple[Path, ...]:
    return _input_roots_for_sources(sources, fallback=config.input_roots)


def _analysis_uri_map(paths: Sequence[Path]) -> dict[str, str]:
    uris: dict[str, str] = {}
    for path in paths:
        document = validate_analysis_result_document(read_json(path))
        uris[document["analysis_result_id"]] = str(path)
    return uris


def _analysis_uri_map_from_collection(
    collection: AnalysisResultCollection,
) -> dict[str, str]:
    uris: dict[str, str] = {}
    for document in collection:
        source_path = document.get("metadata", {}).get("source_path")
        if isinstance(source_path, str) and source_path:
            uris[document["analysis_result_id"]] = source_path
    return uris


def _analysis_uri_map_from_documents(
    documents: Sequence[Mapping[str, Any]],
    paths: Sequence[Path],
) -> dict[str, str]:
    uris: dict[str, str] = {}
    for path in paths:
        document = validate_analysis_result_document(read_json(path))
        uris[document["analysis_result_id"]] = str(path)
    return {
        document["analysis_result_id"]: uris[document["analysis_result_id"]]
        for document in documents
        if document["analysis_result_id"] in uris
    }


def _analysis_result_reuse_enabled(config: WorkflowConfig) -> bool:
    reuse = dict(config.analysis_result_reuse)
    return bool(reuse.get("enabled", False))


def _matching_analysis_artifact(
    candidate: Mapping[str, Any],
    artifacts: Sequence[_AnalysisResultArtifact],
    fingerprint: str,
) -> _AnalysisResultArtifact | None:
    candidate_id = str(candidate["candidate_id"])
    structural_hash = str(dict(candidate["identity"]).get("structural_hash") or "")
    if not structural_hash:
        return None
    for artifact in artifacts:
        document = artifact.document
        candidate_ref = dict(document["candidate_ref"])
        if candidate_ref.get("candidate_id") != candidate_id:
            continue
        if candidate_ref.get("structural_hash") != structural_hash:
            continue
        if _analysis_result_fingerprint(document) != fingerprint:
            continue
        return artifact
    return None


def _analysis_config_fingerprint(config: AnalyzerConfig) -> str:
    return _analysis_config_fingerprint_from_dict(config.to_dict())


def _analysis_config_fingerprint_from_dict(config: Mapping[str, Any]) -> str:
    data = to_json_safe(dict(config))
    for volatile in ("run_id", "input_roots", "output_root"):
        data.pop(volatile, None)
    return stable_hash(
        {
            "fingerprint_version": ANALYSIS_REUSE_FINGERPRINT_VERSION,
            "analyzer": data,
        },
    )


def _analysis_result_fingerprint(document: Mapping[str, Any]) -> str | None:
    metadata = dict(document.get("metadata", {}))
    fingerprint = metadata.get("analysis_compatibility_fingerprint")
    if isinstance(fingerprint, str) and fingerprint:
        return fingerprint
    provenance = dict(document.get("provenance", {}))
    execution = dict(provenance.get("execution", {}))
    config = execution.get("config")
    if isinstance(config, Mapping):
        return _analysis_config_fingerprint_from_dict(config)
    return None


def _analysis_document_with_fingerprint(
    document: Mapping[str, Any],
    fingerprint: str,
) -> dict[str, Any]:
    payload = dict(document)
    metadata = dict(payload.get("metadata", {}))
    metadata["analysis_compatibility_fingerprint"] = fingerprint
    metadata["analysis_compatibility_fingerprint_version"] = ANALYSIS_REUSE_FINGERPRINT_VERSION
    payload["metadata"] = metadata
    return validate_analysis_result_document(payload)


def _analyzer_config_for_input_root(
    config: AnalyzerConfig,
    input_root: Path,
) -> AnalyzerConfig:
    return AnalyzerConfig(
        run_id=config.run_id,
        input_roots=(input_root,),
        output_root=config.output_root,
        selected_metrics=config.selected_metrics,
        execution=config.execution,
        permissions=config.permissions,
        random_seed=config.random_seed,
        structural_cost=config.structural_cost,
        metric_configs=config.metric_configs,
        materialization=config.materialization,
    )


def _staged_package_records(
    staged_package_path: Path,
    candidate_paths: Sequence[Path],
) -> list[dict[str, Any]]:
    return [
        _artifact_record("staged_package", str(staged_package_path)),
        *_path_records("candidate", candidate_paths),
    ]


def _path_records(kind: str, paths: Sequence[Path]) -> list[dict[str, Any]]:
    return [_artifact_record(kind, str(path)) for path in paths]


def _artifact_record(
    kind: str,
    uri: str | None,
    *,
    document_id: str | None = None,
) -> dict[str, Any]:
    record: dict[str, Any] = {"kind": kind}
    if uri is not None:
        record["uri"] = uri
        path = Path(uri).expanduser()
        if path.is_file():
            record["sha256"] = hash_file(path)
    if document_id is not None:
        record["document_id"] = document_id
    return record


def _write_requested_visualizations(
    *,
    config: WorkflowConfig,
    derived_root: Path,
    analysis_collection: AnalysisResultCollection | None,
    ranking_result,
    pareto_result,
    comparison_results: Sequence[ComparisonResult],
    evolution_source: str | Path | Mapping[str, Any] | None,
    input_roots: Sequence[str | Path],
) -> tuple[Path, ...]:
    from verfeinert.ansatz_analyzer.visualization import (
        DEFAULT_STYLE,
        plot_comparison_objective_space,
        plot_lineage_summary,
        plot_pareto_front,
        plot_ranking_scores,
        save_figure,
    )

    paths: list[Path] = []
    for comparison in comparison_results:
        figure = plot_comparison_objective_space(comparison, style=DEFAULT_STYLE)
        paths.append(
            save_figure(
                figure,
                _figure_path(derived_root, config.run_id, f"{comparison.comparison_id}.comparison.png"),
                input_roots=input_roots,
            ),
        )
    if pareto_result is not None:
        figure = plot_pareto_front(pareto_result, style=DEFAULT_STYLE)
        paths.append(
            save_figure(
                figure,
                _figure_path(derived_root, config.run_id, "pareto.png"),
                input_roots=input_roots,
            ),
        )
    elif analysis_collection is not None:
        figure = plot_pareto_front(analysis_collection, style=DEFAULT_STYLE)
        paths.append(
            save_figure(
                figure,
                _figure_path(derived_root, config.run_id, "analysis_objective_space.png"),
                input_roots=input_roots,
            ),
        )
    if ranking_result is not None:
        figure = plot_ranking_scores(ranking_result, style=DEFAULT_STYLE)
        paths.append(
            save_figure(
                figure,
                _figure_path(derived_root, config.run_id, "ranking.png"),
                input_roots=input_roots,
            ),
        )
    evolution_document = _evolution_document_for_visualization(evolution_source)
    if evolution_document is not None:
        figure = plot_lineage_summary(evolution_document, style=DEFAULT_STYLE)
        paths.append(
            save_figure(
                figure,
                _figure_path(derived_root, config.run_id, "evolution_lineage.png"),
                input_roots=input_roots,
            ),
        )
    if not paths:
        raise WorkflowConfigError("requested visualization has no supported input artifact.")
    return tuple(paths)


def _figure_path(derived_root: Path, run_id: str, filename: str) -> Path:
    target = derived_root / run_id / "figures" / filename
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def _evolution_document_for_visualization(
    source: str | Path | Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    if source is None:
        return None
    if isinstance(source, Mapping):
        document = dict(source)
    else:
        document = read_evolution_run_json(source)
    if document.get("schema_version") != "verfeinert.evolution_run.v1":
        raise WorkflowConfigError("visualization evolution input is not an EvolutionRun artifact.")
    return document


def _needs_analysis_collection(postprocessing: Sequence[str]) -> bool:
    return any(operation in {"ranking", "pareto"} for operation in postprocessing)


def _require_collection(collection: AnalysisResultCollection | None) -> AnalysisResultCollection:
    if collection is None:
        raise WorkflowConfigError("AnalysisResult artifacts are required for this operation.")
    return collection


def _candidate_refs_for_collection(
    collection: AnalysisResultCollection,
    *,
    candidate_artifacts: Sequence[_CandidateArtifact],
    uri_by_candidate_id: Mapping[str, str | None],
) -> tuple[CandidateRef, ...]:
    candidates = {artifact.document["candidate_id"]: artifact for artifact in candidate_artifacts}
    refs: list[CandidateRef] = []
    for document in collection:
        candidate_id = document["candidate_ref"]["candidate_id"]
        artifact = candidates.get(candidate_id)
        if artifact is not None:
            refs.append(
                CandidateRef.from_candidate_document(
                    artifact.document,
                    candidate_uri=artifact.uri,
                ),
            )
            continue
        candidate_ref = document["candidate_ref"]
        refs.append(
            CandidateRef(
                candidate_id=candidate_id,
                candidate_uri=uri_by_candidate_id.get(candidate_id),
                structural_hash=candidate_ref.get("structural_hash"),
            ),
        )
    return tuple(refs)


def _generation_record(
    *,
    generation_index: int,
    candidate_refs: Sequence[CandidateRef],
    collection: AnalysisResultCollection,
    selection,
    analysis_uris: Mapping[str, str],
    parent_refs: Sequence[CandidateRef],
    run_id: str,
    extra_configuration: Mapping[str, Any] | None = None,
    extra_events: Sequence[EvolutionEvent] = (),
) -> GenerationRecord:
    ingestion = ingest_analysis_results(
        candidate_refs,
        collection.documents,
        uri_by_analysis_result_id=analysis_uris,
    )
    if ingestion.missing_candidate_ids or ingestion.unexpected_candidate_ids:
        raise WorkflowConfigError(
            "analysis results do not match evolution candidates: "
            f"missing={list(ingestion.missing_candidate_ids)}, "
            f"unexpected={list(ingestion.unexpected_candidate_ids)}",
        )
    return GenerationRecord(
        generation_index=generation_index,
        candidate_refs=tuple(candidate_refs),
        parent_refs=tuple(parent_refs),
        survivor_refs=selection.survivor_refs,
        rejected_refs=selection.rejected_refs,
        archive_refs=selection.archive_refs,
        analysis_result_refs=ingestion.analysis_result_refs,
        configuration={
            "workflow_run_id": run_id,
            "selection": selection.configuration,
            **dict(extra_configuration or {}),
        },
        events=(
            EvolutionEvent(
                event_type="workflow_generation_analyzed",
                status="completed",
                metadata={
                    "candidate_count": len(tuple(candidate_refs)),
                    "analysis_result_count": len(collection.documents),
                },
            ),
            EvolutionEvent(
                event_type="workflow_selection_completed",
                policy_id=selection.policy_id,
                status="completed",
            ),
            *tuple(extra_events),
        ),
    )


def _new_evolution_state(
    *,
    config: WorkflowConfig,
    evolution_run_id: str,
    generations: Sequence[GenerationRecord],
    relationship: Mapping[str, Any],
) -> EvolutionRunState:
    fingerprint = _evolution_fingerprint(config)
    metadata = {
        "workflow": {
            "campaign_type": config.campaign_type,
            "evolution_fingerprint": fingerprint,
            "evolution_fingerprint_version": EVOLUTION_FINGERPRINT_VERSION,
            "relationship": dict(relationship),
        },
        **dict(config.metadata),
    }
    return EvolutionRunState(
        evolution_run_id=evolution_run_id,
        status="running",
        configuration=_evolution_configuration(config),
        generations=tuple(generations),
        provenance={
            "created_at": config.created_at or _created_at_from_generations(generations),
            "source": "verfeinert.workflow",
            "input_hashes": {},
        },
        metadata=metadata,
        created_at=config.created_at or _created_at_from_generations(generations),
        git_commit=None,
        execution_metadata=_evolution_execution_metadata(generations),
    )


def _state_with_generation(
    config: WorkflowConfig,
    state: EvolutionRunState,
    generation: GenerationRecord,
) -> EvolutionRunState:
    return EvolutionRunState(
        evolution_run_id=state.evolution_run_id,
        status="running",
        configuration=_evolution_configuration(config),
        generations=(*state.generations, generation),
        provenance=state.provenance,
        metadata=state.metadata,
        created_at=state.created_at,
        git_commit=state.git_commit,
        execution_metadata=_evolution_execution_metadata((*state.generations, generation)),
    )


def _state_completed(config: WorkflowConfig, state: EvolutionRunState) -> EvolutionRunState:
    return EvolutionRunState(
        evolution_run_id=state.evolution_run_id,
        status="completed",
        configuration=_evolution_configuration(config),
        generations=state.generations,
        provenance=state.provenance,
        metadata=state.metadata,
        created_at=state.created_at,
        git_commit=state.git_commit,
        execution_metadata=_evolution_execution_metadata(state.generations),
    )


def _state_for_resume_or_branch(
    state: EvolutionRunState,
    *,
    document: Mapping[str, Any],
    source_path: Path | None,
    config: WorkflowConfig,
) -> EvolutionRunState:
    current_fingerprint = _evolution_fingerprint(config)
    source_fingerprint = _source_evolution_fingerprint(document)
    expected_run_id = f"{config.run_id}-evolution"
    identity_matches = state.evolution_run_id == expected_run_id
    fingerprint_matches = source_fingerprint == current_fingerprint
    latest_generation = _latest_generation_index(state.generations)

    if config.resume.mode == "continue":
        if not identity_matches or not fingerprint_matches:
            raise WorkflowConfigError(
                "branch required: persisted evolution state is not a compatible continuation.",
            )
        relationship = {
            "type": "continuation",
            "source_evolution_run_id": state.evolution_run_id,
            "source_generation": latest_generation,
            "source_artifact": str(source_path) if source_path is not None else None,
            "configuration_fingerprint": current_fingerprint,
        }
        return _new_evolution_state(
            config=config,
            evolution_run_id=state.evolution_run_id,
            generations=state.generations,
            relationship=relationship,
        )

    if state.evolution_run_id == expected_run_id:
        raise WorkflowConfigError("explicit branch mode requires a new workflow run_id.")
    relationship = {
        "type": "branch",
        "source_evolution_run_id": state.evolution_run_id,
        "source_generation": latest_generation,
        "source_artifact": str(source_path) if source_path is not None else None,
        "source_configuration_fingerprint": source_fingerprint,
        "derived_configuration_fingerprint": current_fingerprint,
        "derived_run_id": expected_run_id,
    }
    return _new_evolution_state(
        config=config,
        evolution_run_id=expected_run_id,
        generations=state.generations,
        relationship=relationship,
    )


def _state_from_evolution_document(document: Mapping[str, Any]) -> EvolutionRunState:
    generations = tuple(_generation_from_document(item) for item in document.get("generations", []))
    return EvolutionRunState(
        evolution_run_id=document["evolution_run_id"],
        status=document["run_metadata"]["status"],
        configuration=dict(document["configuration"]),
        generations=generations,
        provenance=dict(document["provenance"]),
        metadata=dict(document.get("metadata", {})),
        created_at=document["run_metadata"]["created_at"],
        software_version=document["run_metadata"].get("software_version", ""),
        git_commit=document["run_metadata"].get("git_commit"),
        execution_metadata=dict(document["run_metadata"].get("execution", {})),
    )


def _generation_from_document(document: Mapping[str, Any]) -> GenerationRecord:
    return GenerationRecord(
        generation_index=document["generation_index"],
        candidate_refs=tuple(
            CandidateRef.from_ref_document(item)
            for item in document.get("candidate_refs", [])
        ),
        parent_refs=tuple(
            CandidateRef.from_ref_document(item)
            for item in document.get("parent_refs", [])
        ),
        survivor_refs=tuple(
            CandidateRef.from_ref_document(item)
            for item in document.get("survivor_refs", [])
        ),
        rejected_refs=tuple(
            CandidateRef.from_ref_document(item)
            for item in document.get("rejected_refs", [])
        ),
        archive_refs=tuple(
            CandidateRef.from_ref_document(item)
            for item in document.get("archive_refs", [])
        ),
        analysis_result_refs=tuple(
            AnalysisResultRef(
                analysis_result_id=item["analysis_result_id"],
                candidate_id=item["candidate_id"],
                analysis_result_uri=item.get("analysis_result_uri"),
                schema_version=item.get("schema_version", "verfeinert.analysis_result.v1"),
                hash=item.get("hash"),
                metadata=dict(item.get("metadata", {})),
            )
            for item in document.get("analysis_result_refs", [])
        ),
        configuration=dict(document.get("configuration", {})),
        events=tuple(
            EvolutionEvent(
                event_type=item["event_type"],
                created_at=item.get("created_at"),
                candidate_id=item.get("candidate_id"),
                analysis_result_id=item.get("analysis_result_id"),
                policy_id=item.get("policy_id"),
                status=item.get("status"),
                reason=item.get("reason"),
                metadata=dict(item.get("metadata", {})),
            )
            for item in document.get("events", [])
        ),
    )


def _candidate_documents_from_state(
    state: EvolutionRunState,
    *,
    source_path: Path | None,
) -> dict[str, dict[str, Any]]:
    documents: dict[str, dict[str, Any]] = {}
    base = source_path.parent if source_path is not None else None
    for generation in state.generations:
        for ref in generation.candidate_refs:
            if ref.candidate_uri is None:
                continue
            path = Path(ref.candidate_uri).expanduser()
            if not path.is_absolute() and base is not None:
                path = base / path
            if not path.is_file():
                continue
            documents[ref.candidate_id] = validate_candidate_document(read_json(path))
    return documents


def _analysis_result_documents_from_state(
    state: EvolutionRunState,
    *,
    source_path: Path | None,
) -> dict[str, dict[str, Any]]:
    documents: dict[str, dict[str, Any]] = {}
    base = source_path.parent if source_path is not None else None
    for generation in state.generations:
        for ref in generation.analysis_result_refs:
            if ref.analysis_result_uri is None:
                continue
            path = Path(ref.analysis_result_uri).expanduser()
            if not path.is_absolute() and base is not None:
                path = base / path
            if not path.is_file():
                continue
            document = validate_analysis_result_document(read_json(path))
            analysis_result_id = document["analysis_result_id"]
            candidate_id = document["candidate_ref"]["candidate_id"]
            if analysis_result_id != ref.analysis_result_id:
                raise WorkflowConfigError(
                    "invalid resume state: analysis_result_uri for candidate "
                    f"{ref.candidate_id!r} resolved to AnalysisResult {analysis_result_id!r}, "
                    f"expected {ref.analysis_result_id!r}.",
                )
            if candidate_id != ref.candidate_id:
                raise WorkflowConfigError(
                    "invalid resume state: analysis_result_uri for AnalysisResult "
                    f"{ref.analysis_result_id!r} resolved to candidate {candidate_id!r}, "
                    f"expected {ref.candidate_id!r}.",
                )
            existing = documents.get(ref.candidate_id)
            if existing is not None and existing["analysis_result_id"] != analysis_result_id:
                raise WorkflowConfigError(
                    "invalid resume state: conflicting AnalysisResult identities for "
                    f"candidate {ref.candidate_id!r}: {existing['analysis_result_id']!r} and "
                    f"{analysis_result_id!r}.",
                )
            documents[ref.candidate_id] = document
    return documents


def _parent_refs_for_next_generation(
    config: WorkflowConfig,
    state: EvolutionRunState,
    next_generation: int,
) -> tuple[CandidateRef, ...]:
    generations = tuple(state.generations)
    if not generations:
        return ()
    if config.evolver.initial_parent_policy == "all_generation_zero_candidates" and next_generation == 1:
        return tuple(generations[0].candidate_refs)
    latest = generations[-1]
    if config.evolver.selection_mode == "strict_pareto_feedback" and next_generation > 1:
        return tuple(latest.survivor_refs)
    return tuple(latest.survivor_refs or latest.archive_refs or latest.candidate_refs)


def _selection_reference_results(
    config: WorkflowConfig,
    state: EvolutionRunState,
    analysis_by_candidate_id: Mapping[str, Mapping[str, Any]],
    fallback_reference_results: Sequence[Mapping[str, Any]],
) -> tuple[Mapping[str, Any], ...]:
    if config.evolver.selection_mode != "strict_pareto_feedback":
        return tuple(fallback_reference_results)
    if not state.generations:
        return tuple(fallback_reference_results)
    references: list[Mapping[str, Any]] = list(fallback_reference_results)
    missing: list[str] = []
    for ref in state.generations[-1].archive_refs:
        document = analysis_by_candidate_id.get(ref.candidate_id)
        if document is None:
            missing.append(ref.candidate_id)
        else:
            references.append(document)
    if missing:
        raise WorkflowConfigError(
            "cannot continue strict_pareto_feedback: unresolved AnalysisResult(s) "
            f"for accumulated archive: {missing}",
        )
    return tuple(references)


def _deduplicate_offspring(
    candidates: Sequence[Mapping[str, Any]],
    config: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], Any | None]:
    dedup_config = dict(config or {})
    if not bool(dedup_config.get("enabled", False)):
        return [validate_candidate_document(candidate) for candidate in candidates], None
    refs = tuple(CandidateRef.from_candidate_document(candidate) for candidate in candidates)
    kept_refs, report = deduplicate_candidate_refs(
        refs,
        key=str(dedup_config.get("key", "structural_hash")),  # type: ignore[arg-type]
        keep=str(dedup_config.get("keep", "first")),  # type: ignore[arg-type]
    )
    kept_ids = {ref.candidate_id for ref in kept_refs}
    return [
        validate_candidate_document(candidate)
        for candidate in candidates
        if candidate["candidate_id"] in kept_ids
    ], report


def _should_extend_evolution(
    config: WorkflowConfig,
    state: EvolutionRunState,
    candidate_factory: Any | None,
) -> bool:
    if len(state.generations) >= config.evolver.max_generations:
        return False
    if not config.evolver.mutation_policy and candidate_factory is None:
        return False
    if not config.evolver.mutation_policy:
        raise WorkflowConfigError(
            "evolution continuation requires evolver.mutation_policy.",
        )
    if candidate_factory is None:
        raise WorkflowConfigError(
            "evolution continuation requires a candidate_factory for new generations.",
        )
    return True


def _mutation_policy_for_generation(
    config: WorkflowConfig,
    generation_index: int,
) -> MutationPolicy:
    data = dict(config.evolver.mutation_policy)
    if not data:
        raise WorkflowConfigError(
            "evolution continuation requires evolver.mutation_policy.",
        )
    recipes_payload = data.get("recipes", ())
    recipes = tuple(
        recipe
        if isinstance(recipe, MutationRecipe)
        else MutationRecipe(**dict(recipe))
        for recipe in recipes_payload
    )
    policy = MutationPolicy(
        policy_id=data.get("policy_id", "workflow-mutation-policy"),
        recipes=recipes,
        variants_per_parent=data.get("variants_per_parent", 1),
        metadata=dict(data.get("metadata", {})),
    )
    overrides = data.get("generation_overrides", {})
    if isinstance(overrides, Mapping) and str(generation_index) in overrides:
        override = dict(overrides[str(generation_index)])
        override_recipes = tuple(
            recipe
            if isinstance(recipe, MutationRecipe)
            else MutationRecipe(**dict(recipe))
            for recipe in override.get("recipes", ())
        )
        return MutationPolicy(
            policy_id=override.get("policy_id", policy.policy_id),
            recipes=override_recipes,
            variants_per_parent=override.get("variants_per_parent", policy.variants_per_parent),
            metadata=dict(override.get("metadata", {})),
        )
    return policy


def _evolution_configuration(config: WorkflowConfig) -> dict[str, Any]:
    selection_policy = config.evolver.to_dict()
    mutation_policy = dict(selection_policy.pop("mutation_policy", {}))
    max_generations = selection_policy.pop("max_generations")
    selection_policy.pop("metadata", None)
    return {
        "random_seed": config.random_seed,
        "execution": config.execution.to_dict(),
        "mutation_policy": {
            "policy": mutation_policy,
            "requested_metrics": list(config.analyzer.selected_metrics),
        },
        "selection_policy": selection_policy,
        "stopping_policy": {"max_generations": max_generations},
    }


def _evolution_fingerprint(config: WorkflowConfig) -> str:
    selection_policy = config.evolver.to_dict()
    selection_policy.pop("max_generations", None)
    selection_policy.pop("metadata", None)
    return stable_hash(
        {
            "fingerprint_version": EVOLUTION_FINGERPRINT_VERSION,
            "campaign_type": config.campaign_type,
            "random_seed": config.random_seed,
            "execution": config.execution.to_dict(),
            "mutation_policy": selection_policy.pop("mutation_policy", {}),
            "selection_policy": selection_policy,
            "analyzer": {
                "selected_metrics": list(config.analyzer.selected_metrics),
                "structural_cost": config.analyzer.structural_cost.to_dict(),
                "metric_configs": config.analyzer.metric_configs,
            },
        },
    )


def _source_evolution_fingerprint(document: Mapping[str, Any]) -> str:
    workflow = dict(document.get("metadata", {}).get("workflow", {}))
    fingerprint = workflow.get("evolution_fingerprint")
    if isinstance(fingerprint, str) and fingerprint:
        return fingerprint
    configuration = dict(document.get("configuration", {}))
    stopping = dict(configuration.get("stopping_policy", {}))
    stopping.pop("max_generations", None)
    configuration["stopping_policy"] = stopping
    return stable_hash(
        {
            "fingerprint_version": EVOLUTION_FINGERPRINT_VERSION,
            "configuration": configuration,
        },
    )


def _evolution_execution_metadata(
    generations: Sequence[GenerationRecord],
) -> dict[str, Any]:
    return {
        "analysis_requested": any(generation.analysis_result_refs for generation in generations),
        "analysis_results_ingested": any(generation.analysis_result_refs for generation in generations),
        "selection_executed": any(
            generation.survivor_refs or generation.rejected_refs
            for generation in generations
        ),
        "generation_count": len(generations),
    }


def _created_at_from_generations(generations: Sequence[GenerationRecord]) -> str:
    for generation in generations:
        for event in generation.events:
            if event.created_at is not None:
                return event.created_at
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _latest_generation_index(generations: Sequence[GenerationRecord]) -> int | None:
    if not generations:
        return None
    return max(generation.generation_index for generation in generations)


def _entry_point(
    *,
    generated: bool,
    candidates: bool,
    staged_packages: bool,
    analysis_results: bool,
    comparison_results: bool,
    evolution_run: bool,
) -> str:
    if generated:
        return "generation"
    if comparison_results:
        return "comparison_result"
    if evolution_run:
        return "evolution_run"
    if analysis_results:
        return "analysis_result"
    if staged_packages:
        return "staged_package"
    if candidates:
        return "candidate"
    return "configuration"


def run_workflow(
    config: WorkflowConfig | Mapping[str, Any],
    *,
    candidate_records: Sequence[Mapping[str, Any] | Any] | None = None,
    metric_callables: Mapping[str, Any] | None = None,
    reference_analysis_results: Sequence[Mapping[str, Any]] = (),
    candidate_sources: Sequence[str | Path | Mapping[str, Any]] = (),
    staged_package_sources: Sequence[str | Path | Mapping[str, Any]] = (),
    analysis_result_sources: Sequence[str | Path | Mapping[str, Any]] = (),
    evolution_run_source: str | Path | Mapping[str, Any] | None = None,
    candidate_factory: Any | None = None,
) -> WorkflowResult:
    """Run a workflow through the public orchestration entry point."""
    return WorkflowRunner(config).run(
        candidate_records=candidate_records,
        metric_callables=metric_callables,
        reference_analysis_results=reference_analysis_results,
        candidate_sources=candidate_sources,
        staged_package_sources=staged_package_sources,
        analysis_result_sources=analysis_result_sources,
        evolution_run_source=evolution_run_source,
        candidate_factory=candidate_factory,
    )


__all__ = [
    "WorkflowResult",
    "WorkflowRunner",
    "run_workflow",
]
