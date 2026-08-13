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
    ParetoConfig,
    RankingConfig,
    compute_pareto_classifications,
    rank_analysis_results,
    validate_analysis_result_document,
    validate_candidate_document,
    validate_staged_package_document,
)
from verfeinert.ansatz_analyzer.tables import (
    write_analysis_results_csv,
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
    build_mutation_requests,
)
from verfeinert.ansatz_evolver.selection import (
    ObjectiveSpec,
    ThresholdRule,
    select_by_fitness,
    select_by_thresholds,
    select_pareto_front,
    select_strict_pareto,
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
            paths: list[Path] = []
            pipeline = AnalysisPipeline(analyzer_config)
            for source in analysis_sources_for_pipeline:
                paths.extend(
                    pipeline.run_and_write(
                        source,
                        metric_callables=metric_callables,
                    ),
                )
            analysis_result_paths = tuple(paths)
            analysis_collection = AnalysisResultCollection.from_sources(
                analysis_result_paths,
                collection_id=f"{config.run_id}:analysis",
            )
            executed.append("analyze")
            produced_artifacts.extend(_path_records("analysis_result", analysis_result_paths))
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
        if "ranking" in requested_postprocessing:
            collection = _require_collection(analysis_collection)
            ranking_config = config.analyzer.ranking or RankingConfig(
                score_components={"cost.structural_cost": 1.0},
                combination="weighted_sum",
                ascending=True,
            )
            ranking = rank_analysis_results(collection, config=ranking_config)
            if not ranking.ranked_candidate_ids and len(collection):
                raise WorkflowConfigError(
                    "requested ranking metric is missing or unavailable: "
                    + "; ".join(ranking.warnings),
                )
            ranking_json = write_ranking_json(
                ranking,
                output_root=derived_root,
                run_id=config.run_id,
                input_roots=_postprocessing_input_roots(config, analysis_result_paths, all_analysis_sources),
            )
            ranking_csv = write_ranking_csv(
                ranking,
                output_root=derived_root,
                run_id=config.run_id,
                input_roots=_postprocessing_input_roots(config, analysis_result_paths, all_analysis_sources),
            )
            ranking_json_path = ranking_json.path
            ranking_csv_path = ranking_csv.path
            warnings.extend(ranking.warnings)
            executed.append("ranking")
            produced_artifacts.extend([ranking_json.to_dict(), ranking_csv.to_dict()])
        if "pareto" in requested_postprocessing:
            collection = _require_collection(analysis_collection)
            pareto_config = config.analyzer.pareto or ParetoConfig()
            pareto = compute_pareto_classifications(collection, config=pareto_config)
            if not pareto.frontier_candidate_ids and len(collection) and pareto.warnings:
                raise WorkflowConfigError(
                    "requested Pareto objective is missing or unavailable: "
                    + "; ".join(pareto.warnings),
                )
            pareto_json = write_pareto_json(
                pareto,
                output_root=derived_root,
                run_id=config.run_id,
                input_roots=_postprocessing_input_roots(config, analysis_result_paths, all_analysis_sources),
            )
            pareto_json_path = pareto_json.path
            produced_artifacts.append(pareto_json.to_dict())
            warnings.extend(pareto.warnings)
            executed.append("pareto")
            if "export_csv" in requested_postprocessing:
                pareto_csv = write_pareto_csv(
                    pareto,
                    output_root=derived_root,
                    run_id=config.run_id,
                    input_roots=_postprocessing_input_roots(config, analysis_result_paths, all_analysis_sources),
                )
                pareto_csv_path = pareto_csv.path
                produced_artifacts.append(pareto_csv.to_dict())
        if "export_csv" in requested_postprocessing:
            if "ranking" not in requested_postprocessing and "pareto" not in requested_postprocessing:
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
                "csv_exported": any(
                    path is not None
                    for path in (ranking_csv_path, pareto_csv_path, analysis_csv_path)
                ),
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

    def _run_evolution(
        self,
        *,
        analysis_collection: AnalysisResultCollection | None,
        candidate_artifacts: Sequence[_CandidateArtifact],
        evolution_source: str | Path | Mapping[str, Any] | None,
        candidate_factory: Any | None,
        reference_analysis_results: Sequence[Mapping[str, Any]],
        analysis_result_paths: Sequence[Path],
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

        if evolution_source is not None:
            document, source_path = _evolution_document_with_path(evolution_source)
            consumed_artifacts.append(_artifact_record("evolution_run", _source_uri(evolution_source)))
            reused_artifacts.append(_artifact_record("evolution_run", _source_uri(evolution_source)))
            state = _state_from_evolution_document(document)
            candidate_lookup.update(_candidate_documents_from_state(state, source_path=source_path))
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
            parent_refs = (
                state.generations[-1].survivor_refs
                or state.generations[-1].archive_refs
                or state.generations[-1].candidate_refs
            )
            if not parent_refs:
                raise WorkflowConfigError("invalid resume state: latest generation has no parent candidates.")
            policy = _mutation_policy_for_generation(config, next_generation)
            requests = build_mutation_requests(
                parent_refs,
                generation_index=next_generation,
                policy=policy,
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
                candidate_lookup[child["candidate_id"]] = child
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
            analysis_paths = tuple(AnalysisPipeline(analyzer_config).run_and_write(package.staged_package_path))
            produced_artifacts.extend(_path_records("analysis_result", analysis_paths))
            if "analyze" not in executed:
                executed.append("analyze")
            child_collection = AnalysisResultCollection.from_sources(
                analysis_paths,
                collection_id=f"{config.run_id}:g{next_generation:03d}:analysis",
            )
            selection = self._select(child_collection, reference_analysis_results)
            child_refs = tuple(
                CandidateRef.from_candidate_document(candidate, candidate_uri=candidate_uri_lookup.get(candidate["candidate_id"]))
                for candidate in package.candidates
            )
            generation = _generation_record(
                generation_index=next_generation,
                candidate_refs=child_refs,
                collection=child_collection,
                selection=selection,
                analysis_uris=_analysis_uri_map(analysis_paths),
                parent_refs=tuple(parent_refs),
                run_id=config.run_id,
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


def _needs_analysis_collection(postprocessing: Sequence[str]) -> bool:
    return any(operation in {"ranking", "pareto", "export_csv"} for operation in postprocessing)


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
        archive_refs=selection.survivor_refs,
        analysis_result_refs=ingestion.analysis_result_refs,
        configuration={
            "workflow_run_id": run_id,
            "selection": selection.configuration,
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
    evolution_run: bool,
) -> str:
    if generated:
        return "generation"
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
