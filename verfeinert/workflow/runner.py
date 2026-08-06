"""Public workflow runner composing generator, analyzer, and evolver APIs."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from verfeinert.ansatz_analyzer import (
    AnalysisPipeline,
    AnalysisResultCollection,
    AnalyzerConfig,
    RankingConfig,
    rank_analysis_results,
)
from verfeinert.ansatz_analyzer.tables import DerivedArtifact, write_ranking_csv, write_ranking_json
from verfeinert.ansatz_evolver import (
    AnalysisResultRef,
    CandidateRef,
    EvolutionEvent,
    EvolutionRunState,
    GenerationRecord,
    write_evolution_run_json,
)
from verfeinert.ansatz_evolver.evaluation import ingest_analysis_results
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
    write_staged_package_json,
)
from verfeinert.core.io import ensure_output_root
from verfeinert.core.io.serialization import to_json_safe
from verfeinert.core.validation import require_identifier

from .config import WorkflowConfig, WorkflowConfigError
from .provenance import workflow_provenance


@dataclass(frozen=True)
class WorkflowResult:
    """Artifact manifest returned by a workflow run."""

    run_id: str
    output_root: Path
    run_root: Path
    candidate_paths: tuple[Path, ...]
    staged_package_path: Path
    analysis_result_paths: tuple[Path, ...]
    evolution_run_path: Path
    ranking_json_path: Path | None = None
    ranking_csv_path: Path | None = None
    candidate_ids: tuple[str, ...] = ()
    analysis_result_ids: tuple[str, ...] = ()
    survivor_candidate_ids: tuple[str, ...] = ()
    rejected_candidate_ids: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    provenance: dict[str, Any] = field(default_factory=dict)
    generation_record: GenerationRecord | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe manifest for examples and tests."""
        return to_json_safe(
            {
                "schema_version": "verfeinert.workflow_result.v1",
                "run_id": self.run_id,
                "output_root": str(self.output_root),
                "run_root": str(self.run_root),
                "candidate_paths": [str(path) for path in self.candidate_paths],
                "staged_package_path": str(self.staged_package_path),
                "analysis_result_paths": [str(path) for path in self.analysis_result_paths],
                "evolution_run_path": str(self.evolution_run_path),
                "ranking_json_path": str(self.ranking_json_path) if self.ranking_json_path else None,
                "ranking_csv_path": str(self.ranking_csv_path) if self.ranking_csv_path else None,
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
            },
        )


class WorkflowRunner:
    """Coordinate one JSON-first Verfeinert workflow through public APIs."""

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
    ) -> WorkflowResult:
        """Run generation, analysis, selection, and EvolutionRun export."""
        config = self.config
        output_root = ensure_output_root(config.output_root, input_roots=config.input_roots)
        run_root = output_root / config.run_id
        package_output_root = run_root / "candidates"
        analysis_root = run_root / "analysis"
        evolution_root = run_root / "evolution"
        derived_root = run_root / "derived_outputs"

        records = tuple(candidate_records) if candidate_records is not None else tuple(self._generate_records())
        if not records:
            raise WorkflowConfigError("Workflow generation produced no candidate records.")

        staged = write_staged_package_json(
            records,
            config=self._staged_package_config(package_output_root),
        )
        if staged.package_root is None or staged.staged_package_path is None:
            raise RuntimeError("Staged package exporter did not return paths.")

        analyzer_config = self._analyzer_config(staged.package_root, analysis_root)
        analysis_result_paths = tuple(
            AnalysisPipeline(analyzer_config).run_and_write(
                staged.staged_package_path,
                metric_callables=metric_callables,
            ),
        )
        collection = AnalysisResultCollection.from_sources(
            (analysis_root / config.run_id,),
            collection_id=f"{config.run_id}:analysis",
        )
        selection = self._select(collection, reference_analysis_results)
        ingestion = ingest_analysis_results(
            (
                CandidateRef.from_candidate_document(candidate)
                for candidate in staged.candidates
            ),
            collection.documents,
        )
        candidate_refs = tuple(
            CandidateRef.from_candidate_document(candidate)
            for candidate in staged.candidates
        )
        generation_record = GenerationRecord(
            generation_index=0,
            candidate_refs=candidate_refs,
            survivor_refs=selection.survivor_refs,
            rejected_refs=selection.rejected_refs,
            archive_refs=selection.survivor_refs,
            analysis_result_refs=ingestion.analysis_result_refs,
            configuration={
                "workflow_run_id": config.run_id,
                "selection": selection.configuration,
            },
            events=(
                EvolutionEvent(
                    event_type="workflow_generation_analyzed",
                    status="completed",
                    metadata={
                        "candidate_count": len(candidate_refs),
                        "analysis_result_count": len(collection.documents),
                    },
                ),
                EvolutionEvent(
                    event_type="workflow_selection_completed",
                    policy_id=config.evolver.policy_id,
                    status="completed",
                ),
            ),
        )
        state = EvolutionRunState(
            evolution_run_id=f"{config.run_id}-evolution",
            status="completed",
            configuration={
                "random_seed": config.random_seed,
                "execution": config.execution.to_dict(),
                "mutation_policy": {
                    "mode": "workflow_external_or_none",
                    "generation": config.generation.to_dict(),
                },
                "selection_policy": config.evolver.to_dict(),
                "stopping_policy": {
                    "max_generations": config.evolver.max_generations,
                },
            },
            generations=(generation_record,),
            provenance={
                "created_at": config.created_at or staged.package["provenance"]["created_at"],
                "source": "verfeinert.workflow",
                "input_hashes": {},
            },
            metadata={
                "workflow_config": config.to_dict(),
                **dict(config.metadata),
            },
            created_at=config.created_at or staged.package["provenance"]["created_at"],
            git_commit=None,
            execution_metadata={
                "analysis_requested": True,
                "analysis_results_ingested": True,
                "selection_executed": True,
            },
        )
        evolution_path = write_evolution_run_json(
            state,
            output_root=evolution_root,
            input_roots=(staged.package_root, analysis_root),
        )

        ranking_json_path: Path | None = None
        ranking_csv_path: Path | None = None
        warnings: list[str] = []
        if "rank" in config.stages and config.analyzer.write_ranking:
            ranking_config = config.analyzer.ranking or RankingConfig(
                score_components={"cost.structural_cost": 1.0},
                combination="weighted_sum",
                ascending=True,
            )
            ranking = rank_analysis_results(collection, config=ranking_config)
            ranking_json = write_ranking_json(
                ranking,
                output_root=derived_root,
                run_id=config.run_id,
                input_roots=(staged.package_root, analysis_root),
            )
            ranking_csv = write_ranking_csv(
                ranking,
                output_root=derived_root,
                run_id=config.run_id,
                input_roots=(staged.package_root, analysis_root),
            )
            ranking_json_path = ranking_json.path
            ranking_csv_path = ranking_csv.path
            warnings.extend(ranking.warnings)

        provenance = workflow_provenance(
            run_id=config.run_id,
            config_snapshot=config.to_dict(),
            created_at=config.created_at,
            git_commit=None,
            execution_flags={
                "candidate_generation_executed": True,
                "analysis_executed": True,
                "evolution_exported": True,
                "qnodes_executed_by_runner": False,
            },
        )
        return WorkflowResult(
            run_id=config.run_id,
            output_root=output_root,
            run_root=run_root,
            candidate_paths=staged.candidate_paths,
            staged_package_path=staged.staged_package_path,
            analysis_result_paths=analysis_result_paths,
            evolution_run_path=evolution_path,
            ranking_json_path=ranking_json_path,
            ranking_csv_path=ranking_csv_path,
            candidate_ids=tuple(candidate["candidate_id"] for candidate in staged.candidates),
            analysis_result_ids=collection.analysis_result_ids,
            survivor_candidate_ids=tuple(ref.candidate_id for ref in selection.survivor_refs),
            rejected_candidate_ids=tuple(ref.candidate_id for ref in selection.rejected_refs),
            warnings=tuple(dict.fromkeys(warnings)),
            provenance=provenance,
            generation_record=generation_record,
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

    def _analyzer_config(self, candidate_root: Path, analysis_root: Path) -> AnalyzerConfig:
        config = self.config
        return AnalyzerConfig(
            run_id=config.run_id,
            input_roots=(candidate_root,),
            output_root=analysis_root,
            selected_metrics=config.analyzer.selected_metrics,
            execution=config.execution,
            permissions=config.analyzer.permissions,
            random_seed=config.analyzer.random_seed if config.analyzer.random_seed is not None else config.random_seed,
            structural_cost=config.analyzer.structural_cost,
            metric_configs=config.analyzer.metric_configs,
        )

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


def run_workflow(
    config: WorkflowConfig | Mapping[str, Any],
    *,
    candidate_records: Sequence[Mapping[str, Any] | Any] | None = None,
    metric_callables: Mapping[str, Any] | None = None,
    reference_analysis_results: Sequence[Mapping[str, Any]] = (),
) -> WorkflowResult:
    """Run a workflow through the public orchestration entry point."""
    return WorkflowRunner(config).run(
        candidate_records=candidate_records,
        metric_callables=metric_callables,
        reference_analysis_results=reference_analysis_results,
    )


__all__ = [
    "WorkflowResult",
    "WorkflowRunner",
    "run_workflow",
]
